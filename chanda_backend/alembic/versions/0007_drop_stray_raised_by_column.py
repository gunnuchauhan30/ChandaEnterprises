"""drop stray leftover 'raised_by' column from employee_requests

This column is NOT part of this application's design -- it's leftover
residue from an earlier, unrelated migration.sql (from a rejected
third-party patch package) that was apparently run directly against this
database at some point outside of Alembic. It has a NOT NULL constraint
with no usable default, so every new request insert has been failing with:

    psycopg2.errors.NotNullViolation: null value in column "raised_by"
    of relation "employee_requests" violates not-null constraint

Our actual model already has two columns that cover what this was for:
- requested_by (who was logged in when they raised it)
- raised_by_name (the name they typed in, added in migration 0005)

So `raised_by` is redundant and unused -- safe to drop.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-05
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE employee_requests DROP COLUMN IF EXISTS raised_by")


def downgrade() -> None:
    # Deliberately a no-op: this column was never part of the application's
    # design, so there is nothing meaningful to restore it to.
    pass
