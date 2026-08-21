"""baseline: schema as created by schema.sql

This is a NO-OP migration. The actual tables/triggers/views/indexes were
created by running schema.sql (+ data_import.sql) directly against a fresh
database, as documented in README.md. This revision exists only so Alembic
has a starting point to track from.

On a database that was set up via schema.sql, run:
    alembic stamp 0001
to tell Alembic "the DB is already at this revision" without re-running
anything. From then on, use `alembic revision --autogenerate -m "..."` for
every future schema change instead of hand-editing schema.sql.

On a brand-new empty database (no schema.sql run yet), you can instead do:
    alembic upgrade head
but note this revision itself creates nothing -- you still need to load
schema.sql once, or replace this file's upgrade() with the real DDL if you
want a from-scratch Alembic-only setup going forward.

Revision ID: 0001
Revises:
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op: schema already created by schema.sql. See module docstring.
    pass


def downgrade() -> None:
    # No-op: destroying the whole schema from here would be unsafe to do
    # blindly. If you truly need to tear it down, drop the database instead.
    pass
