"""Issues: Accounts-approval gate + full FIFO batch allocation tracking

- Adds issue_batch_allocations table: exact per-batch FIFO breakdown for
  each issue, written by the trigger at the moment stock actually moves.
  This is what lets 'Update Consumption' show the FULL FIFO split instead
  of just the first/oldest batch.
- Adds accounts_approval_status / accounts_approved_by / accounts_approved_at
  to `issues`.
- Rewrites the stock trigger: it used to fire AFTER INSERT ON issues and
  deduct stock immediately. It now fires BEFORE UPDATE ON issues, and only
  deducts stock once accounts_approval_status flips to 'approved'. Creating
  an Issue row (Store's step) no longer moves stock by itself.

SAFE FOR HISTORICAL DATA: issues created before this migration already had
their stock deducted under the OLD AFTER-INSERT trigger. We mark those as
accounts_approval_status='approved' BEFORE swapping in the new trigger, so
that backfill UPDATE never touches the new stock-moving logic at all (the
old trigger only ever listened for INSERT, never UPDATE).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS issue_batch_allocations (
            id SERIAL PRIMARY KEY,
            issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
            stock_batch_id INTEGER REFERENCES stock_batches(id),
            batch_no VARCHAR(50),
            qty_taken NUMERIC(12,2) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_issue_batch_allocations_issue_id ON issue_batch_allocations (issue_id)")

    op.execute("ALTER TABLE issues ADD COLUMN IF NOT EXISTS accounts_approval_status VARCHAR(20) NOT NULL DEFAULT 'pending'")
    op.execute("ALTER TABLE issues ADD COLUMN IF NOT EXISTS accounts_approved_by INTEGER REFERENCES users(id)")
    op.execute("ALTER TABLE issues ADD COLUMN IF NOT EXISTS accounts_approved_at TIMESTAMP")

    # Historical issues already had stock deducted under the OLD (AFTER
    # INSERT) trigger -- mark them approved. Safe: the old trigger has no
    # UPDATE listener, so this UPDATE cannot re-trigger anything.
    op.execute("""
        UPDATE issues
           SET accounts_approval_status = 'approved',
               accounts_approved_at = created_at
    """)

    # Now swap the trigger: drop the old AFTER INSERT one, install the new
    # BEFORE UPDATE one that only moves stock on accounts approval and
    # records the full per-batch split.
    op.execute("DROP TRIGGER IF EXISTS trg_issue_stock ON issues")
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_trg_issue_stock() RETURNS TRIGGER AS $$
        DECLARE
            v_remaining NUMERIC;
            v_batch RECORD;
            v_take NUMERIC;
            v_first_lot VARCHAR;
        BEGIN
            IF TG_OP = 'UPDATE'
               AND OLD.accounts_approval_status IS DISTINCT FROM 'approved'
               AND NEW.accounts_approval_status = 'approved' THEN

                v_remaining := NEW.issue_qty;

                PERFORM fn_post_stock_ledger(NEW.material_code, 'ISSUE', -NEW.issue_qty,
                                              'issues', NEW.id, NULL,
                                              'Issue ' || NEW.issue_no || ' (Accounts approved)',
                                              NEW.accounts_approved_by);

                FOR v_batch IN
                    SELECT id, batch_no, remaining_qty FROM stock_batches
                    WHERE material_code = NEW.material_code AND remaining_qty > 0
                    ORDER BY received_date ASC, id ASC
                    FOR UPDATE
                LOOP
                    EXIT WHEN v_remaining <= 0;
                    v_take := LEAST(v_batch.remaining_qty, v_remaining);
                    UPDATE stock_batches SET remaining_qty = remaining_qty - v_take WHERE id = v_batch.id;

                    INSERT INTO issue_batch_allocations (issue_id, stock_batch_id, batch_no, qty_taken)
                    VALUES (NEW.id, v_batch.id, v_batch.batch_no, v_take);

                    IF v_first_lot IS NULL THEN
                        v_first_lot := v_batch.batch_no;
                    END IF;

                    v_remaining := v_remaining - v_take;
                END LOOP;

                -- BEFORE trigger: set it on NEW directly, no recursive
                -- UPDATE on the same row (that would be unsafe here).
                IF v_first_lot IS NOT NULL THEN
                    NEW.lot_no := v_first_lot;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_issue_stock
        BEFORE UPDATE ON issues
        FOR EACH ROW EXECUTE FUNCTION fn_trg_issue_stock();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_issue_stock ON issues")
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_trg_issue_stock() RETURNS TRIGGER AS $$
        DECLARE
            v_remaining NUMERIC := NEW.issue_qty;
            v_batch RECORD;
            v_take NUMERIC;
        BEGIN
            PERFORM fn_post_stock_ledger(NEW.material_code, 'ISSUE', -NEW.issue_qty,
                                          'issues', NEW.id, NULL,
                                          'Issue ' || NEW.issue_no, NEW.issued_by);
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
    """)
    op.execute("""
        CREATE TRIGGER trg_issue_stock
        AFTER INSERT ON issues
        FOR EACH ROW EXECUTE FUNCTION fn_trg_issue_stock();
    """)
    op.drop_column("issues", "accounts_approved_at")
    op.drop_column("issues", "accounts_approved_by")
    op.drop_column("issues", "accounts_approval_status")
    op.drop_index("ix_issue_batch_allocations_issue_id", table_name="issue_batch_allocations")
    op.drop_table("issue_batch_allocations")
