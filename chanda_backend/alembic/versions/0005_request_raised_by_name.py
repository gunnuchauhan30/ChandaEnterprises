"""employee_requests: mandatory raised_by_name column

Adds raised_by_name to employee_requests. For any requests that already
exist before this migration, we backfill it from the requester's own user
record (users.full_name, falling back to username) so the column can be
made NOT NULL without breaking existing rows. Every request raised from
here on requires the frontend to submit this field explicitly.

Note: this migration does NOT change any trigger or touch stock -- it is
purely additive on employee_requests.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: safe to re-run regardless of any partially-applied
    # earlier attempt.
    op.execute("ALTER TABLE employee_requests ADD COLUMN IF NOT EXISTS raised_by_name VARCHAR(120)")

    # ...backfill every existing row from the requester's own user record...
    op.execute("""
        UPDATE employee_requests er
           SET raised_by_name = COALESCE(u.full_name, u.username, 'Not recorded')
          FROM users u
         WHERE er.requested_by = u.id
           AND er.raised_by_name IS NULL
    """)
    # ...and catch any leftover row with no matching user at all.
    op.execute("""
        UPDATE employee_requests
           SET raised_by_name = 'Not recorded'
         WHERE raised_by_name IS NULL
    """)

    # ...now it's safe to enforce NOT NULL for every future row.
    op.execute("ALTER TABLE employee_requests ALTER COLUMN raised_by_name SET NOT NULL")


def downgrade() -> None:
    op.drop_column("employee_requests", "raised_by_name")
