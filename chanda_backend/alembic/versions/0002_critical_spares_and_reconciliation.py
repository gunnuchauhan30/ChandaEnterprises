"""critical spares list + physical stock reconciliation

Adds two new tables, matching the DDL already present in schema.sql:
  - critical_spares          (Critical Spares List page)
  - stock_reconciliations    (Inventory > Physical Stock Reconciliation tab)

On a database that was bootstrapped straight from schema.sql (e.g. via the
docker-compose Postgres init scripts), schema.sql already contains this DDL
and you just need to stamp this revision:
    alembic stamp 0002

On a database that was previously stamped at 0001 and has NOT had the
updated schema.sql re-run, apply this migration for real:
    alembic upgrade head

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    spare_priority = sa.Enum("critical", "high", "medium", name="spare_priority")
    reconciliation_status = sa.Enum("pending", "approved", "rejected", name="reconciliation_status")
    bind = op.get_bind()
    spare_priority.create(bind, checkfirst=True)
    reconciliation_status.create(bind, checkfirst=True)

    op.create_table(
        "critical_spares",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_code", sa.String(30),
                  sa.ForeignKey("materials.material_code", ondelete="CASCADE"), nullable=False),
        sa.Column("machine_name", sa.String(150)),
        sa.Column("priority", spare_priority, nullable=False, server_default="critical"),
        sa.Column("threshold_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("remarks", sa.Text),
        sa.Column("added_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("material_code", "machine_name"),
    )
    op.create_index("idx_critical_spares_material", "critical_spares", ["material_code"])
    op.execute("""
        CREATE TRIGGER trg_critical_spares_updated_at
        BEFORE UPDATE ON critical_spares
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    op.create_table(
        "stock_reconciliations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("material_code", sa.String(30), sa.ForeignKey("materials.material_code"), nullable=False),
        sa.Column("system_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("physical_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("difference_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("remarks", sa.Text),
        sa.Column("status", reconciliation_status, nullable=False, server_default="pending"),
        sa.Column("counted_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("reviewed_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("review_remarks", sa.Text),
        sa.Column("return_id", sa.Integer, sa.ForeignKey("returns.id")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime),
    )
    op.create_index("idx_stock_reconciliations_status", "stock_reconciliations", ["status"])
    op.create_index("idx_stock_reconciliations_material", "stock_reconciliations", ["material_code"])


def downgrade() -> None:
    op.drop_index("idx_stock_reconciliations_material", table_name="stock_reconciliations")
    op.drop_index("idx_stock_reconciliations_status", table_name="stock_reconciliations")
    op.drop_table("stock_reconciliations")

    op.execute("DROP TRIGGER IF EXISTS trg_critical_spares_updated_at ON critical_spares")
    op.drop_index("idx_critical_spares_material", table_name="critical_spares")
    op.drop_table("critical_spares")

    sa.Enum(name="reconciliation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="spare_priority").drop(op.get_bind(), checkfirst=True)
