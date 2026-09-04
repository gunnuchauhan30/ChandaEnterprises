"""GRN accounts-approval step -- stock only moves after Accounts approves

Adds accounts_approval_status / accounts_approved_by / accounts_approved_at
to `purchases`, and changes the stock trigger so current_qty only increases
once accounts_approval_status flips to 'approved' -- QC passing alone no
longer moves stock (it only unlocks the Accounts step).

SAFE FOR HISTORICAL DATA: purchases that already passed QC before this
migration already had their stock counted under the OLD trigger logic. We
mark those as accounts_approval_status='approved' so the UI/API is
consistent, but we do this with the stock trigger explicitly DISABLED for
that one backfill statement -- otherwise the new trigger would fire on
that UPDATE and add the same stock a second time. This is the standard,
safe way to do this kind of backfill in Postgres.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: makes this safe to re-run no matter what partial state
    # an earlier interrupted deploy left behind.
    op.execute("ALTER TABLE purchases ADD COLUMN IF NOT EXISTS accounts_approval_status VARCHAR(20) NOT NULL DEFAULT 'pending'")
    op.execute("ALTER TABLE purchases ADD COLUMN IF NOT EXISTS accounts_approved_by INTEGER REFERENCES users(id)")
    op.execute("ALTER TABLE purchases ADD COLUMN IF NOT EXISTS accounts_approved_at TIMESTAMP")

    # Backfill historical QC-passed GRNs as accounts-approved, WITHOUT
    # letting the (still old-logic at this point) trigger fire again.
    op.execute("ALTER TABLE purchases DISABLE TRIGGER trg_purchase_stock")
    op.execute("""
        UPDATE purchases
           SET accounts_approval_status = 'approved',
               accounts_approved_at = created_at
         WHERE qc_status = 'passed'
    """)
    op.execute("ALTER TABLE purchases ENABLE TRIGGER trg_purchase_stock")

    # Now redefine the trigger function for all FUTURE purchases: stock
    # moves only on accounts approval, never on QC pass alone.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_trg_purchase_stock() RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               AND OLD.accounts_approval_status IS DISTINCT FROM 'approved'
               AND NEW.accounts_approval_status = 'approved' THEN
                PERFORM fn_post_stock_ledger(NEW.material_code, 'PURCHASE', NEW.qty,
                                              'purchases', NEW.id, NEW.batch_no,
                                              'GRN ' || NEW.grn_no || ' (Accounts approved)',
                                              NEW.accounts_approved_by);
                INSERT INTO stock_batches (material_code, batch_no, purchase_id, received_qty,
                                            remaining_qty, unit_cost, received_date)
                VALUES (NEW.material_code, COALESCE(NEW.batch_no, NEW.grn_no), NEW.id, NEW.qty,
                        NEW.qty, NEW.unit_cost, COALESCE(NEW.invoice_date, CURRENT_DATE));
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Revert trigger to the old QC-pass-triggers-stock logic.
    op.execute("""
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
    """)
    op.drop_column("purchases", "accounts_approved_at")
    op.drop_column("purchases", "accounts_approved_by")
    op.drop_column("purchases", "accounts_approval_status")
