-- ============================================================
-- Chanda Enterprises - Migration for the 13-point upgrade
-- Run this ONCE against your Railway Postgres database before
-- (or right after) deploying the updated backend/frontend code.
--
-- HOW TO RUN ON RAILWAY:
--   1. Railway dashboard -> Postgres service -> "Data" (or "Query") tab
--   2. Paste this whole file and execute it
--   (Or: railway connect Postgres  →  paste into psql)
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- Point 5: Returns -- track who physically returned the material
-- ------------------------------------------------------------
ALTER TABLE returns ADD COLUMN IF NOT EXISTS returned_by_name VARCHAR(120);

-- ------------------------------------------------------------
-- Point 7: Purchase/GRN -- put-away location for this specific batch
-- ------------------------------------------------------------
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS warehouse VARCHAR(50);
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS rack VARCHAR(50);
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS bin VARCHAR(50);

-- ------------------------------------------------------------
-- Point 12: FIFO backorders -- partial fulfillment tracking
-- ------------------------------------------------------------
-- 1) New status value so a request can sit "partially fulfilled / queued"
ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'partial';

-- 2) Running total of how much has actually been issued against a request
ALTER TABLE employee_requests ADD COLUMN IF NOT EXISTS fulfilled_qty NUMERIC(12,2) NOT NULL DEFAULT 0;

-- 3) Stop the old DB trigger from creating a second/duplicate Issue.
--    Approvals are now handled entirely in application code (app/api/v1/issues.py),
--    which supports partial (FIFO backorder) fulfillment; the trigger's
--    all-or-nothing behaviour is no longer used and would double-issue stock
--    if it ever fired.
DROP TRIGGER IF EXISTS trg_request_approved ON employee_requests;

COMMIT;

-- ------------------------------------------------------------
-- Sanity checks (optional -- run these after COMMIT to confirm)
-- ------------------------------------------------------------
-- SELECT column_name FROM information_schema.columns WHERE table_name='returns' AND column_name='returned_by_name';
-- SELECT column_name FROM information_schema.columns WHERE table_name='purchases' AND column_name IN ('warehouse','rack','bin');
-- SELECT column_name FROM information_schema.columns WHERE table_name='employee_requests' AND column_name='fulfilled_qty';
-- SELECT enum_range(NULL::request_status);
-- SELECT tgname FROM pg_trigger WHERE tgname = 'trg_request_approved';   -- should return 0 rows
