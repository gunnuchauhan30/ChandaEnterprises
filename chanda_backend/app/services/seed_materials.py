"""
Auto-seeds the real ROHAN_STOCK material master data on backend startup.

Design goals:
- Idempotent: safe to run on every container start / every gunicorn worker.
  Uses "ON CONFLICT ... DO NOTHING" at the DB level so concurrent workers
  racing to insert the same row never error out or duplicate data.
- Non-fatal: any problem here is logged and swallowed so a bad seed file
  never prevents the API from starting.
- One-way: only fills the material master when it's empty. If materials
  already exist (e.g. someone has been using the app), this does nothing --
  it will not overwrite anything a user has typed in by hand.
"""
import json
import logging
import os
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("chanda")

_SEED_FILE = os.path.join(os.path.dirname(__file__), "..", "seed_data", "materials_seed.json")


def seed_materials_if_empty(engine: Engine) -> None:
    try:
        with engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM materials")).scalar()
            if count and count > 0:
                logger.info("Material master already has %s rows -- skipping auto-seed.", count)
                return

            if not os.path.exists(_SEED_FILE):
                logger.warning("Seed file not found at %s -- skipping auto-seed.", _SEED_FILE)
                return

            with open(_SEED_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)

            # 1) Suppliers first (materials reference them by id).
            supplier_names = sorted({i["supplier"] for i in items if i.get("supplier")})
            for name in supplier_names:
                conn.execute(
                    text("INSERT INTO suppliers (supplier_name) VALUES (:name) "
                         "ON CONFLICT (supplier_name) DO NOTHING"),
                    {"name": name},
                )

            supplier_ids = {}
            if supplier_names:
                rows = conn.execute(
                    text("SELECT id, supplier_name FROM suppliers WHERE supplier_name = ANY(:names)"),
                    {"names": supplier_names},
                ).fetchall()
                supplier_ids = {r[1]: r[0] for r in rows}

            # 2) Materials -- same defaulting rule as the manual Excel import:
            # PRODUCTION items need both min_qty and max_qty (DB constraint),
            # so missing values get a flagged placeholder instead of failing.
            created = 0
            for it in items:
                min_qty = it.get("min_qty")
                max_qty = it.get("max_qty")
                mtype = it.get("mtype") or "PRODUCTION"
                if mtype == "PRODUCTION" and (min_qty is None or max_qty is None):
                    min_qty = min_qty if min_qty is not None else 0
                    max_qty = max_qty if max_qty is not None else max((min_qty or 0) * 10, 1000)

                current_qty = Decimal(str(it.get("current_qty") or 0))
                supplier_id = supplier_ids.get(it.get("supplier"))

                result = conn.execute(
                    text("""
                        INSERT INTO materials
                            (material_code, material_name, material_type, grade, uom,
                             min_qty, max_qty, opening_qty, current_qty, rack,
                             per_day_req, supplier_id)
                        VALUES
                            (:code, :name, :mtype, :grade, :uom,
                             :min_qty, :max_qty, :opening_qty, :current_qty, :rack,
                             :per_day, :supplier_id)
                        ON CONFLICT (material_code) DO NOTHING
                    """),
                    {
                        "code": it["code"], "name": it["name"], "mtype": mtype,
                        "grade": it.get("grade"), "uom": it.get("uom") or "NOS",
                        "min_qty": min_qty, "max_qty": max_qty,
                        "opening_qty": current_qty, "current_qty": current_qty,
                        "rack": it.get("rack"), "per_day": it.get("per_day"),
                        "supplier_id": supplier_id,
                    },
                )
                created += result.rowcount

            logger.info(
                "Auto-seed complete: %s suppliers ensured, %s materials inserted.",
                len(supplier_names), created,
            )
    except Exception:
        logger.exception("Material auto-seed failed -- app will continue without it.")
