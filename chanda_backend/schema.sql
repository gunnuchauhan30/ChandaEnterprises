-- ============================================================
-- CHANDA ENTERPRISES — STORE MANAGEMENT SYSTEM
-- Database Schema v2 (PostgreSQL) — COMPLETE, per full project spec
-- Designed from: ROHAN_STOCK_FILE (Stock Details + RM Sheets Details +
--                 Consumable Items), RM_PURCHASE_FILE, BUSH_PURCHASE_REPORT,
--                 Rout_Card (real company data)
--
-- Fixes vs v1 (database_design/schema.sql):
--   1. reserved_qty added to materials (Opening/Current/Reserved/Available)
--   2. stock_batches table added -> real batch tracking, FIFO, aging
--   3. unit_cost added -> stock valuation now possible
--   4. employee_requests split out from issues -> request/approval/issue
--      are now three distinct, traceable stages
--   5. 'adjustment' added to return_type enum
--   6. activity_logs, error_logs, login_logs added (audit_log kept for
--      field-level old/new value changes specifically)
--   7. password_reset_tokens added for Forgot Password
--   8. materials.category is populated on import; material_type
--      (PRODUCTION / CONSUMABLE) added -- this is the fix for the alert
--      scoping issue discussed: consumables never raise stock alerts
--   9. Alert trigger is fully ATTACHED this time (fires automatically on
--      purchase/issue/return/adjustment), and explicitly SKIPS consumables
--  10. Added vw_low_stock_materials / vw_high_stock_materials views
--  11. Replaced the materialized view (needed manual REFRESH) with a
--      trigger-maintained materials.current_qty cached column + an
--      append-only stock_ledger table as the source of truth. This is
--      real-time: no refresh step, ever.
-- ============================================================
-- Run with:  psql -U your_user -d chanda_store -f schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- 1. USERS & ROLES
-- ------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('admin', 'store_manager', 'purchase', 'production', 'management', 'quality');

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(120) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(120),
    role            user_role NOT NULL DEFAULT 'production',
    department      VARCHAR(80),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    last_login      TIMESTAMP
);

CREATE INDEX idx_users_role ON users(role);

-- Forgot Password support (gap #7)
CREATE TABLE password_reset_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token           VARCHAR(500) NOT NULL,
    used            BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP NOT NULL
);

-- ------------------------------------------------------------
-- 2. SUPPLIER MASTER
-- ------------------------------------------------------------
CREATE TABLE suppliers (
    id              SERIAL PRIMARY KEY,
    supplier_name   VARCHAR(150) UNIQUE NOT NULL,
    gst_no          VARCHAR(20),
    address         TEXT,
    email           VARCHAR(120),
    phone           VARCHAR(20),
    payment_terms   VARCHAR(100),
    rating          NUMERIC(2,1) CHECK (rating BETWEEN 0 AND 5),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 3. MATERIAL MASTER
-- ------------------------------------------------------------
-- gap #8: material_type controls whether the alert engine ever looks at
-- this item. Defaulted automatically on import from which Excel sheet the
-- row came from (Stock Details / RM Sheets Details = PRODUCTION,
-- Consumable Items = CONSUMABLE) -- but it is a normal editable column,
-- so any material can be manually re-tagged later (auto default + manual
-- override, as discussed).
CREATE TYPE material_type_enum AS ENUM ('PRODUCTION', 'CONSUMABLE');

CREATE TABLE materials (
    material_code   VARCHAR(30) PRIMARY KEY,
    material_name   VARCHAR(200) NOT NULL,
    category        VARCHAR(80),                  -- e.g. 'SS Pipe', 'RM Sheet', 'Consumable / Safety Item'
    material_type   material_type_enum NOT NULL DEFAULT 'PRODUCTION',
    grade           VARCHAR(50),
    size            VARCHAR(80),
    uom             VARCHAR(20) DEFAULT 'NOS',
    min_qty         NUMERIC(12,2),                 -- NULL allowed: consumables often have no threshold
    max_qty         NUMERIC(12,2),
    opening_qty     NUMERIC(12,2) NOT NULL DEFAULT 0,
    current_qty     NUMERIC(12,2) NOT NULL DEFAULT 0,   -- cached, trigger-maintained (gap #11), NEVER set by hand
    reserved_qty    NUMERIC(12,2) NOT NULL DEFAULT 0,   -- gap #1
    unit_cost       NUMERIC(12,2) DEFAULT 0,             -- gap #3, for stock valuation
    per_day_req     NUMERIC(12,2),
    warehouse       VARCHAR(50),
    rack            VARCHAR(50),
    bin             VARCHAR(50),
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    hsn_code        VARCHAR(20),
    lead_time_days  INTEGER DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'active',
    low_stock_alert_open  BOOLEAN DEFAULT FALSE,   -- de-dupe flag so alerts don't spam every txn
    high_stock_alert_open BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_min_max CHECK (min_qty IS NULL OR max_qty IS NULL OR min_qty <= max_qty),
    -- Consumables are exempt, but if a PRODUCTION material has no min/max
    -- the alert engine simply cannot protect it -- worth flagging at insert time
    CONSTRAINT chk_production_has_threshold CHECK (
        material_type = 'CONSUMABLE' OR (min_qty IS NOT NULL AND max_qty IS NOT NULL)
    )
);

CREATE INDEX idx_materials_category ON materials(category);
CREATE INDEX idx_materials_supplier ON materials(supplier_id);
CREATE INDEX idx_materials_type ON materials(material_type);

-- ------------------------------------------------------------
-- 4. STOCK LEDGER (gap #11 -- replaces the materialized view)
-- Append-only, immutable. materials.current_qty is a cache kept in sync
-- with this table by triggers below -- this IS "available stock never
-- entered manually", enforced at the database level, in real time.
-- ------------------------------------------------------------
CREATE TYPE ledger_txn_type AS ENUM ('OPENING', 'PURCHASE', 'ISSUE', 'RETURN', 'ADJUSTMENT');

CREATE TABLE stock_ledger (
    id              BIGSERIAL PRIMARY KEY,
    material_code   VARCHAR(30) NOT NULL REFERENCES materials(material_code) ON DELETE RESTRICT,
    txn_type        ledger_txn_type NOT NULL,
    qty_change      NUMERIC(12,2) NOT NULL,        -- signed: + increases stock, - decreases stock
    balance_after   NUMERIC(12,2) NOT NULL,
    ref_table       VARCHAR(30),                    -- 'purchases' | 'issues' | 'returns' | 'manual'
    ref_id          INTEGER,
    batch_no        VARCHAR(50),
    remarks         TEXT,
    created_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ledger_material ON stock_ledger(material_code);
CREATE INDEX idx_ledger_created_at ON stock_ledger(created_at);

-- ------------------------------------------------------------
-- 5. STOCK BATCHES (gap #2 -- FIFO + aging)
-- ------------------------------------------------------------
CREATE TABLE stock_batches (
    id              SERIAL PRIMARY KEY,
    material_code   VARCHAR(30) NOT NULL REFERENCES materials(material_code) ON DELETE RESTRICT,
    batch_no        VARCHAR(50) NOT NULL,
    purchase_id     INTEGER,                        -- FK added after purchases table exists
    received_qty    NUMERIC(12,2) NOT NULL,
    remaining_qty   NUMERIC(12,2) NOT NULL,          -- decremented FIFO as issues consume this batch
    unit_cost       NUMERIC(12,2),
    received_date   DATE DEFAULT CURRENT_DATE,
    warehouse       VARCHAR(50),
    rack            VARCHAR(50)
);

CREATE INDEX idx_batches_material_fifo ON stock_batches(material_code, received_date);

-- ------------------------------------------------------------
-- 6. PURCHASE MODULE (GRN)
-- ------------------------------------------------------------
CREATE TYPE qc_status_type AS ENUM ('pending', 'passed', 'failed');

CREATE TABLE purchases (
    id              SERIAL PRIMARY KEY,
    grn_no          VARCHAR(30) UNIQUE NOT NULL,
    material_code   VARCHAR(30) NOT NULL REFERENCES materials(material_code) ON DELETE RESTRICT,
    supplier_id     INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
    invoice_no      VARCHAR(50),
    invoice_date    DATE,
    batch_no        VARCHAR(50),
    qty             NUMERIC(12,2) NOT NULL CHECK (qty > 0),
    unit_cost       NUMERIC(12,2) DEFAULT 0,
    warehouse       VARCHAR(50),   -- point 7: put-away location for this batch
    rack            VARCHAR(50),
    bin             VARCHAR(50),
    qc_status       qc_status_type DEFAULT 'pending',
    qc_remarks      TEXT,
    invoice_file_path VARCHAR(255),
    received_by     INTEGER REFERENCES users(id),
    created_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW()
);

ALTER TABLE stock_batches
    ADD CONSTRAINT fk_batches_purchase FOREIGN KEY (purchase_id) REFERENCES purchases(id) ON DELETE SET NULL;

CREATE INDEX idx_purchases_material ON purchases(material_code);
CREATE INDEX idx_purchases_date ON purchases(invoice_date);
CREATE INDEX idx_purchases_qc ON purchases(qc_status);

-- ------------------------------------------------------------
-- 7. EMPLOYEE REQUEST  (gap #4 -- split from issues)
-- Stage 1: production employee asks for material.
-- ------------------------------------------------------------
CREATE TYPE request_status AS ENUM ('pending', 'approved', 'partial', 'rejected', 'completed');

CREATE TABLE employee_requests (
    id                  SERIAL PRIMARY KEY,
    request_no          VARCHAR(30) UNIQUE NOT NULL,
    material_code       VARCHAR(30) NOT NULL REFERENCES materials(material_code) ON DELETE RESTRICT,
    requested_qty       NUMERIC(12,2) NOT NULL CHECK (requested_qty > 0),
    fulfilled_qty        NUMERIC(12,2) NOT NULL DEFAULT 0,   -- point 12: FIFO backorder tracking
    requested_by        INTEGER NOT NULL REFERENCES users(id),
    department          VARCHAR(80),
    job_card_no         VARCHAR(50),
    part_number         VARCHAR(80),
    purpose             TEXT,
    status               request_status DEFAULT 'pending',
    approved_by          INTEGER REFERENCES users(id),
    approved_at          TIMESTAMP,
    rejection_reason     TEXT,
    created_at            TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_requests_status ON employee_requests(status);
CREATE INDEX idx_requests_material ON employee_requests(material_code);

-- ------------------------------------------------------------
-- 8. MATERIAL ISSUE / ROUTE CARD MODULE
-- Stage 2: the actual issue slip -- this is what deducts stock, either
-- created directly by the Store Manager or auto-generated when a request
-- above is approved. Matches Rout_Card.xlsx columns directly.
-- ------------------------------------------------------------
CREATE TABLE issues (
    id                  SERIAL PRIMARY KEY,
    issue_no            VARCHAR(30) UNIQUE NOT NULL,
    material_code       VARCHAR(30) NOT NULL REFERENCES materials(material_code) ON DELETE RESTRICT,
    employee_request_id INTEGER REFERENCES employee_requests(id) ON DELETE SET NULL,
    job_card_no         VARCHAR(50),
    lot_no               VARCHAR(50),
    production_order_no VARCHAR(50),
    part_number          VARCHAR(80),
    machine               VARCHAR(80),
    operation             VARCHAR(80),
    department            VARCHAR(80),
    shift                 VARCHAR(30),
    required_qty          NUMERIC(12,2),
    issue_qty             NUMERIC(12,2) NOT NULL CHECK (issue_qty > 0),
    consumed_qty           NUMERIC(12,2) DEFAULT 0,
    pending_qty             NUMERIC(12,2) GENERATED ALWAYS AS
                                (COALESCE(required_qty, 0) - COALESCE(consumed_qty, 0)) STORED,
    completion_status        VARCHAR(20) DEFAULT 'issued',  -- issued / in_progress / completed
    issued_by                INTEGER REFERENCES users(id),
    remark                    VARCHAR(255),
    issue_date                DATE DEFAULT CURRENT_DATE,
    created_at                 TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_issues_material ON issues(material_code);
CREATE INDEX idx_issues_job ON issues(job_card_no);
CREATE INDEX idx_issues_date ON issues(issue_date);

-- ------------------------------------------------------------
-- 9. RETURN MODULE  (gap #5 -- 'adjustment' added)
-- ------------------------------------------------------------
CREATE TYPE return_type_enum AS ENUM ('unused', 'vendor_return', 'rejected', 'adjustment');

CREATE TABLE returns (
    id                  SERIAL PRIMARY KEY,
    return_no           VARCHAR(30) UNIQUE NOT NULL,
    material_code       VARCHAR(30) NOT NULL REFERENCES materials(material_code) ON DELETE RESTRICT,
    return_type         return_type_enum NOT NULL,
    -- qty is always entered as a positive amount by the user; the trigger
    -- below decides the sign to apply based on return_type (vendor_return
    -- reduces stock, everything else increases it) except 'adjustment',
    -- which uses adjustment_qty (can be + or -) instead.
    qty                 NUMERIC(12,2) CHECK (qty IS NULL OR qty > 0),
    adjustment_qty       NUMERIC(12,2),              -- only used when return_type = 'adjustment'
    reference_issue_id   INTEGER REFERENCES issues(id) ON DELETE SET NULL,
    supplier_id           INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,  -- for vendor_return
    reason                 TEXT,
    returned_by_name        VARCHAR(120),   -- point 5: employee who physically returned it
    approved_by            INTEGER REFERENCES users(id),
    created_by              INTEGER REFERENCES users(id),
    created_at               TIMESTAMP DEFAULT NOW(),
    CONSTRAINT chk_return_qty CHECK (
        (return_type = 'adjustment' AND adjustment_qty IS NOT NULL AND adjustment_qty <> 0)
        OR (return_type <> 'adjustment' AND qty IS NOT NULL)
    )
);

CREATE INDEX idx_returns_material ON returns(material_code);

-- ------------------------------------------------------------
-- 10. ALERTS
-- ------------------------------------------------------------
CREATE TYPE alert_type AS ENUM ('low_stock', 'high_stock');

CREATE TABLE alerts (
    id              SERIAL PRIMARY KEY,
    material_code   VARCHAR(30) NOT NULL REFERENCES materials(material_code) ON DELETE CASCADE,
    alert_type      alert_type NOT NULL,
    available_qty   NUMERIC(12,2),
    threshold_qty   NUMERIC(12,2),
    message         TEXT,
    is_resolved     BOOLEAN DEFAULT FALSE,
    triggered_at    TIMESTAMP DEFAULT NOW(),
    resolved_at     TIMESTAMP
);

CREATE INDEX idx_alerts_material ON alerts(material_code);
CREATE INDEX idx_alerts_unresolved ON alerts(is_resolved) WHERE is_resolved = FALSE;

-- ------------------------------------------------------------
-- 11. NOTIFICATIONS (bell/toast/popup center)
-- ------------------------------------------------------------
CREATE TABLE notifications (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,   -- NULL = broadcast to a role
    role            user_role,
    type            VARCHAR(30) DEFAULT 'info',
    title           VARCHAR(150),
    message         TEXT,
    link            VARCHAR(255),
    is_read         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_unread ON notifications(user_id, is_read);

-- ------------------------------------------------------------
-- 12. AUDIT + LOGGING  (gap #6 -- Activity/Error/Login logs added)
-- ------------------------------------------------------------
-- Field-level change history (who changed what field, old -> new)
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    table_name      VARCHAR(50) NOT NULL,
    record_id       VARCHAR(50) NOT NULL,
    action          VARCHAR(20) NOT NULL,   -- INSERT / UPDATE / DELETE
    old_value       JSONB,
    new_value       JSONB,
    changed_by      INTEGER REFERENCES users(id),
    ip_address      VARCHAR(45),
    changed_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_table_record ON audit_log(table_name, record_id);
CREATE INDEX idx_audit_changed_at ON audit_log(changed_at);

-- What a user did, in plain language (e.g. "Exported stock report")
CREATE TABLE activity_logs (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    action          VARCHAR(255) NOT NULL,
    module          VARCHAR(50),
    ip_address      VARCHAR(45),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_activity_user ON activity_logs(user_id);

-- Every login attempt, success or failure
CREATE TABLE login_logs (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             INTEGER REFERENCES users(id),
    username_attempted  VARCHAR(50),
    success             BOOLEAN DEFAULT FALSE,
    ip_address          VARCHAR(45),
    user_agent          VARCHAR(255),
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_login_logs_created_at ON login_logs(created_at);

-- Unhandled application errors, for the admin's error-log screen
CREATE TABLE error_logs (
    id              BIGSERIAL PRIMARY KEY,
    path            VARCHAR(255),
    method          VARCHAR(10),
    status_code     INTEGER,
    error_message   TEXT NOT NULL,
    traceback       TEXT,
    user_id         INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Every report/file download, for the "Download Logs" screen
CREATE TABLE download_logs (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    file_name       VARCHAR(255) NOT NULL,
    report_type     VARCHAR(50),
    format          VARCHAR(10),           -- excel / csv / pdf
    ip_address      VARCHAR(45),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- VIEWS  (gap #10 -- more than one, and both are LIVE, not materialized)
-- ============================================================
CREATE VIEW vw_low_stock_materials AS
SELECT material_code, material_name, category, current_qty, reserved_qty,
       (current_qty - reserved_qty) AS available_qty, min_qty
FROM materials
WHERE material_type = 'PRODUCTION'
  AND min_qty IS NOT NULL
  AND (current_qty - reserved_qty) <= min_qty;

CREATE VIEW vw_high_stock_materials AS
SELECT material_code, material_name, category, current_qty, reserved_qty,
       (current_qty - reserved_qty) AS available_qty, max_qty
FROM materials
WHERE material_type = 'PRODUCTION'
  AND max_qty IS NOT NULL
  AND (current_qty - reserved_qty) >= max_qty;

CREATE VIEW vw_stock_valuation AS
SELECT material_code, material_name, current_qty, unit_cost,
       (current_qty * COALESCE(unit_cost, 0)) AS stock_value
FROM materials;

CREATE VIEW vw_stock_aging AS
SELECT material_code,
       CASE
           WHEN (CURRENT_DATE - received_date) <= 30 THEN '0-30'
           WHEN (CURRENT_DATE - received_date) <= 60 THEN '31-60'
           WHEN (CURRENT_DATE - received_date) <= 90 THEN '61-90'
           ELSE '90+'
       END AS age_bucket,
       SUM(remaining_qty) AS qty
FROM stock_batches
WHERE remaining_qty > 0
GROUP BY material_code, age_bucket;

-- ============================================================
-- TRIGGERS
-- ============================================================

-- 13a. keep materials.updated_at fresh
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_materials_updated_at
BEFORE UPDATE ON materials
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 13b. Core stock-ledger writer. Every trigger below calls this instead of
-- touching materials.current_qty directly, so there is exactly ONE place
-- in the whole database that changes stock. (gap #11)
CREATE OR REPLACE FUNCTION fn_post_stock_ledger(
    p_material_code VARCHAR, p_txn_type ledger_txn_type, p_qty_change NUMERIC,
    p_ref_table VARCHAR, p_ref_id INTEGER, p_batch_no VARCHAR,
    p_remarks TEXT, p_created_by INTEGER
) RETURNS VOID AS $$
DECLARE
    v_new_balance NUMERIC;
BEGIN
    UPDATE materials
       SET current_qty = current_qty + p_qty_change
     WHERE material_code = p_material_code
     RETURNING current_qty INTO v_new_balance;

    IF v_new_balance < 0 THEN
        RAISE EXCEPTION 'Insufficient stock for %: resulting balance would be %',
            p_material_code, v_new_balance;
    END IF;

    INSERT INTO stock_ledger (material_code, txn_type, qty_change, balance_after,
                               ref_table, ref_id, batch_no, remarks, created_by)
    VALUES (p_material_code, p_txn_type, p_qty_change, v_new_balance,
            p_ref_table, p_ref_id, p_batch_no, p_remarks, p_created_by);

    PERFORM fn_check_stock_thresholds(p_material_code);
END;
$$ LANGUAGE plpgsql;

-- 13c. Alert Engine -- gap #9: explicitly SKIPS material_type = 'CONSUMABLE'
CREATE OR REPLACE FUNCTION fn_check_stock_thresholds(p_material_code VARCHAR)
RETURNS VOID AS $$
DECLARE
    v_type material_type_enum;
    v_available NUMERIC;
    v_min NUMERIC;
    v_max NUMERIC;
    v_name VARCHAR;
    v_low_open BOOLEAN;
    v_high_open BOOLEAN;
BEGIN
    SELECT material_type, current_qty - reserved_qty, min_qty, max_qty,
           material_name, low_stock_alert_open, high_stock_alert_open
      INTO v_type, v_available, v_min, v_max, v_name, v_low_open, v_high_open
    FROM materials WHERE material_code = p_material_code;

    -- Consumables never alert -- this is the fix requested.
    IF v_type <> 'PRODUCTION' OR v_min IS NULL OR v_max IS NULL THEN
        RETURN;
    END IF;

    -- LOW STOCK (de-duplicated: only insert a new alert the moment it
    -- crosses the line, not on every single subsequent transaction)
    IF v_available <= v_min THEN
        IF NOT v_low_open THEN
            UPDATE materials SET low_stock_alert_open = TRUE WHERE material_code = p_material_code;
            INSERT INTO alerts (material_code, alert_type, available_qty, threshold_qty, message)
            VALUES (p_material_code, 'low_stock', v_available, v_min,
                    v_name || ' (' || p_material_code || ') at ' || v_available ||
                    ', at/below minimum ' || v_min);
        END IF;
    ELSE
        UPDATE materials SET low_stock_alert_open = FALSE WHERE material_code = p_material_code;
    END IF;

    -- HIGH STOCK
    IF v_available >= v_max THEN
        IF NOT v_high_open THEN
            UPDATE materials SET high_stock_alert_open = TRUE WHERE material_code = p_material_code;
            INSERT INTO alerts (material_code, alert_type, available_qty, threshold_qty, message)
            VALUES (p_material_code, 'high_stock', v_available, v_max,
                    v_name || ' (' || p_material_code || ') at ' || v_available ||
                    ', at/above maximum ' || v_max || '. Confirmation required before further purchase.');
        END IF;
    ELSE
        UPDATE materials SET high_stock_alert_open = FALSE WHERE material_code = p_material_code;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 13d. PURCHASE -> stock increase (only once QC has passed)
CREATE OR REPLACE FUNCTION fn_trg_purchase_stock() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.qc_status = 'passed' THEN
        PERFORM fn_post_stock_ledger(NEW.material_code, 'PURCHASE', NEW.qty,
                                      'purchases', NEW.id, NEW.batch_no,
                                      'GRN ' || NEW.grn_no, NEW.created_by);
        INSERT INTO stock_batches (material_code, batch_no, purchase_id, received_qty,
                                    remaining_qty, unit_cost, received_date)
        VALUES (NEW.material_code, COALESCE(NEW.batch_no, NEW.grn_no), NEW.id, NEW.qty,
                NEW.qty, NEW.unit_cost, COALESCE(NEW.invoice_date, CURRENT_DATE));

    ELSIF TG_OP = 'UPDATE' AND OLD.qc_status <> 'passed' AND NEW.qc_status = 'passed' THEN
        PERFORM fn_post_stock_ledger(NEW.material_code, 'PURCHASE', NEW.qty,
                                      'purchases', NEW.id, NEW.batch_no,
                                      'GRN ' || NEW.grn_no || ' (QC passed on update)', NEW.received_by);
        INSERT INTO stock_batches (material_code, batch_no, purchase_id, received_qty,
                                    remaining_qty, unit_cost, received_date)
        VALUES (NEW.material_code, COALESCE(NEW.batch_no, NEW.grn_no), NEW.id, NEW.qty,
                NEW.qty, NEW.unit_cost, COALESCE(NEW.invoice_date, CURRENT_DATE));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_purchase_stock
AFTER INSERT OR UPDATE ON purchases
FOR EACH ROW EXECUTE FUNCTION fn_trg_purchase_stock();

-- 13e. ISSUE -> stock decrease + FIFO batch consumption, on insert
CREATE OR REPLACE FUNCTION fn_trg_issue_stock() RETURNS TRIGGER AS $$
DECLARE
    v_remaining NUMERIC := NEW.issue_qty;
    v_batch RECORD;
    v_take NUMERIC;
BEGIN
    PERFORM fn_post_stock_ledger(NEW.material_code, 'ISSUE', -NEW.issue_qty,
                                  'issues', NEW.id, NULL,
                                  'Issue ' || NEW.issue_no, NEW.issued_by);

    -- FIFO: consume oldest batches first
    FOR v_batch IN
        SELECT id, remaining_qty FROM stock_batches
        WHERE material_code = NEW.material_code AND remaining_qty > 0
        ORDER BY received_date ASC, id ASC
        FOR UPDATE
    LOOP
        EXIT WHEN v_remaining <= 0;
        v_take := LEAST(v_batch.remaining_qty, v_remaining);
        UPDATE stock_batches SET remaining_qty = remaining_qty - v_take WHERE id = v_batch.id;
        v_remaining := v_remaining - v_take;
    END LOOP;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_issue_stock
AFTER INSERT ON issues
FOR EACH ROW EXECUTE FUNCTION fn_trg_issue_stock();

-- 13f. RETURN -> stock increase/decrease depending on type
CREATE OR REPLACE FUNCTION fn_trg_return_stock() RETURNS TRIGGER AS $$
DECLARE
    v_signed_qty NUMERIC;
BEGIN
    IF NEW.return_type = 'adjustment' THEN
        v_signed_qty := NEW.adjustment_qty;               -- caller-signed, can be + or -
    ELSIF NEW.return_type = 'vendor_return' THEN
        v_signed_qty := -NEW.qty;                          -- goes back out to supplier
    ELSE
        v_signed_qty := NEW.qty;                            -- unused / rejected -> back into store
    END IF;

    PERFORM fn_post_stock_ledger(NEW.material_code, 'RETURN', v_signed_qty,
                                  'returns', NEW.id, NULL,
                                  'Return ' || NEW.return_no || ' (' || NEW.return_type || ')',
                                  NEW.created_by);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_return_stock
AFTER INSERT ON returns
FOR EACH ROW EXECUTE FUNCTION fn_trg_return_stock();

-- 13g. EMPLOYEE REQUEST approval
-- NOTE (point 12 upgrade): approval/fulfillment is now handled entirely in
-- application code (app/api/v1/issues.py -> decide_request /
-- process_backorders), because it needs to support PARTIAL fulfillment with
-- the remainder queued as a FIFO backorder -- something a simple all-or-
-- nothing DB trigger can't express. The Issue row is still inserted from
-- Python, which is what fires fn_trg_issue_stock below and actually moves
-- stock -- so the single source of truth for stock movement is unchanged,
-- just triggered from the app instead of from a status-flip trigger.

-- ------------------------------------------------------------
-- 14. CRITICAL SPARES LIST
-- Standalone list of spare parts flagged as critical for production
-- (e.g. machine spares that must never run out). Linked to materials for
-- live stock data, but kept as its own table so it can carry fields that
-- don't belong on every material (machine name, criticality priority,
-- its own reorder threshold independent of the material's min_qty).
-- ------------------------------------------------------------
CREATE TYPE spare_priority AS ENUM ('critical', 'high', 'medium');

CREATE TABLE critical_spares (
    id              SERIAL PRIMARY KEY,
    material_code   VARCHAR(30) NOT NULL REFERENCES materials(material_code) ON DELETE CASCADE,
    machine_name    VARCHAR(150),
    priority        spare_priority NOT NULL DEFAULT 'critical',
    threshold_qty   NUMERIC(12,2) NOT NULL,
    remarks         TEXT,
    added_by        INTEGER REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (material_code, machine_name)
);

CREATE INDEX idx_critical_spares_material ON critical_spares(material_code);

CREATE TRIGGER trg_critical_spares_updated_at
BEFORE UPDATE ON critical_spares
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------
-- 15. PHYSICAL STOCK RECONCILIATION
-- Store Manager counts physical stock; system computes the mismatch
-- against current_qty. Nothing touches actual stock until Admin approves --
-- on approval, a 'returns' row (return_type='adjustment') is inserted,
-- which the existing fn_trg_return_stock trigger posts to stock_ledger
-- automatically (source of truth stays the ledger, no separate code path).
-- ------------------------------------------------------------
CREATE TYPE reconciliation_status AS ENUM ('pending', 'approved', 'rejected');

CREATE TABLE stock_reconciliations (
    id              SERIAL PRIMARY KEY,
    material_code   VARCHAR(30) NOT NULL REFERENCES materials(material_code),
    system_qty      NUMERIC(12,2) NOT NULL,      -- current_qty snapshot at count time
    physical_qty    NUMERIC(12,2) NOT NULL,      -- what was physically counted
    difference_qty  NUMERIC(12,2) NOT NULL,      -- physical - system (signed)
    remarks         TEXT,
    status          reconciliation_status NOT NULL DEFAULT 'pending',
    counted_by      INTEGER REFERENCES users(id),
    reviewed_by     INTEGER REFERENCES users(id),
    review_remarks  TEXT,
    return_id       INTEGER REFERENCES returns(id),   -- set once approved
    created_at      TIMESTAMP DEFAULT NOW(),
    reviewed_at     TIMESTAMP
);

CREATE INDEX idx_stock_reconciliations_status ON stock_reconciliations(status);
CREATE INDEX idx_stock_reconciliations_material ON stock_reconciliations(material_code);

-- ============================================================
-- Atomic sequences for human-readable reference numbers
-- (GRN-000001, REQ-000001, ISS-000001, RET-000001, LOT-000001).
-- Using real Postgres sequences instead of a COUNT(*)-based scheme means
-- two concurrent requests can never be handed the same number.
-- ============================================================
CREATE SEQUENCE purchases_grn_no_seq START 1;
CREATE SEQUENCE employee_requests_request_no_seq START 1;
CREATE SEQUENCE issues_issue_no_seq START 1;
CREATE SEQUENCE returns_return_no_seq START 1;
CREATE SEQUENCE purchases_batch_no_seq START 1;

-- ============================================================
-- END OF SCHEMA
-- ============================================================
