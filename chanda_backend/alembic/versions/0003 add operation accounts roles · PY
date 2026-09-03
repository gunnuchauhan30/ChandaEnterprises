"""add operation and accounts roles

Adds two new values to the existing Postgres `user_role` enum:
  - operation   (approves employee material requests)
  - accounts    (final approval step on GRN + Issues -- only step that moves stock)

This is purely ADDITIVE: no existing rows, roles, or permissions change.
Every user currently in the `users` table keeps their existing role exactly
as-is. Nobody gets locked out. This migration only makes the two new role
values *available* to be assigned (via Admin > Manage Users) going forward.

IMPORTANT (Postgres-specific): `ALTER TYPE ... ADD VALUE` cannot run inside
the same transaction as other statements before Postgres 12, and even on 12+
the new value can't be *used* in the same transaction it was added in. Since
Alembic wraps each migration in a transaction by default, we issue an
explicit COMMIT first so each ALTER TYPE runs in its own auto-committed
statement. This is the standard, safe pattern for this kind of change and is
non-locking/non-destructive on a live database.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # End the transaction Alembic opened, so each ALTER TYPE below runs in
    # its own auto-committed statement (required for ADD VALUE on Postgres).
    op.execute("COMMIT")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'operation'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'accounts'")


def downgrade() -> None:
    # Postgres does not support removing a value from an existing enum type
    # directly. Downgrading safely would require creating a new enum without
    # these values, moving every column over, and dropping the old type --
    # only worth doing if you're certain no user has been assigned either
    # role yet. Left as a manual/no-op here rather than risking data loss.
    pass
