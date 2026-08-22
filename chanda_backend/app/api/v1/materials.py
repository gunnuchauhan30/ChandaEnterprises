from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from decimal import Decimal, InvalidOperation

from app.db.session import get_db
from app.core.deps import get_current_user, require_roles
from app.models import Material, User, Supplier
from app.schemas.materials import MaterialIn, MaterialUpdate, MaterialOut
from app.services.audit import log_activity, log_download
from app.services.excel_service import export_rows_to_excel, parse_material_import_excel, MATERIAL_COLUMNS

router = APIRouter(prefix="/materials", tags=["Material Master"])

VALID_TYPES = {"PRODUCTION", "CONSUMABLE"}


@router.get("", response_model=List[MaterialOut])
def list_materials(
    search: Optional[str] = Query(None, description="Searches code, name, category"),
    category: Optional[str] = None,
    material_type: Optional[str] = None,
    status: Optional[str] = None,
    warehouse: Optional[str] = None,
    low_stock_only: bool = False,
    high_stock_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Material)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Material.material_code.ilike(like), Material.material_name.ilike(like),
                          Material.category.ilike(like)))
    if category:
        q = q.filter(Material.category == category)
    if material_type:
        q = q.filter(Material.material_type == material_type)
    if status:
        q = q.filter(Material.status == status)
    if warehouse:
        q = q.filter(Material.warehouse == warehouse)
    if low_stock_only:
        q = q.filter(Material.low_stock_alert_open == True)  # noqa: E712
    if high_stock_only:
        q = q.filter(Material.high_stock_alert_open == True)  # noqa: E712

    return q.order_by(Material.material_code).offset((page - 1) * page_size).limit(page_size).all()


@router.get("/{material_code}", response_model=MaterialOut)
def get_material(material_code: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    material = db.query(Material).get(material_code)
    if not material:
        raise HTTPException(404, "Material not found")
    return material


@router.post("", response_model=MaterialOut, status_code=201)
def create_material(
    payload: MaterialIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "purchase")),
):
    if payload.material_type not in VALID_TYPES:
        raise HTTPException(400, f"material_type must be one of {VALID_TYPES}")
    if db.query(Material).get(payload.material_code):
        raise HTTPException(409, "Material code already exists")
    # Point: block duplicate Material Master entries -- same name already
    # exists under a different code (this is exactly how MC037/MC038 and
    # RM-0039/RM-0040 duplicates happened before).
    existing_name = db.query(Material).filter(
        Material.material_name.ilike(payload.material_name.strip())
    ).first()
    if existing_name:
        raise HTTPException(
            409,
            f"A material named '{payload.material_name}' already exists "
            f"(code {existing_name.material_code}). Edit that material instead "
            f"of creating a duplicate.",
        )
    if payload.material_type == "PRODUCTION" and (payload.min_qty is None or payload.max_qty is None):
        raise HTTPException(400, "PRODUCTION materials require both min_qty and max_qty")

    data = payload.model_dump()
    data["current_qty"] = data["opening_qty"]  # opening balance seeds current stock; never edited directly again
    material = Material(**data)
    db.add(material)
    db.commit()
    db.refresh(material)
    log_activity(db, current_user.id, f"Created material {material.material_code}", "materials")
    return material


@router.put("/{material_code}", response_model=MaterialOut)
def update_material(
    material_code: str,
    payload: MaterialUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "purchase")),
):
    material = db.query(Material).get(material_code)
    if not material:
        raise HTTPException(404, "Material not found")
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(material, k, v)
    db.commit()
    db.refresh(material)
    log_activity(db, current_user.id, f"Updated material {material_code}", "materials")
    return material


@router.delete("/{material_code}")
def deactivate_material(
    material_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "store_manager")),
):
    """
    Point 3: this used to always soft-deactivate and say "deleted", which was
    misleading -- the row stayed in the list. Now: try a real delete first.
    The database itself only allows that when the material has zero history
    (no purchases/issues/requests/ledger entries referencing it) via
    ON DELETE RESTRICT, so this can never silently orphan real records. If
    it's actually in use, we fall back to deactivating it (existing safe
    behaviour) and say so explicitly.
    """
    material = db.query(Material).get(material_code)
    if not material:
        raise HTTPException(404, "Material not found")

    try:
        db.delete(material)
        db.commit()
        log_activity(db, current_user.id, f"Deleted material {material_code}", "materials")
        return {"action": "deleted", "message": f"{material_code} permanently deleted"}
    except IntegrityError:
        db.rollback()
        material = db.query(Material).get(material_code)
        material.status = "inactive"
        db.commit()
        log_activity(db, current_user.id, f"Deactivated material {material_code}", "materials")
        return {
            "action": "deactivated",
            "message": f"{material_code} has purchase/issue history, so it was deactivated (hidden from the "
                       f"active list) instead of deleted, to keep that history intact.",
        }


@router.get("/export/excel")
def export_materials(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    materials = db.query(Material).order_by(Material.material_code).all()
    rows = [{
        "material_code": m.material_code, "material_name": m.material_name, "category": m.category,
        "material_type": m.material_type.value, "grade": m.grade, "size": m.size, "uom": m.uom,
        "min_qty": m.min_qty, "max_qty": m.max_qty, "opening_qty": m.opening_qty, "unit_cost": m.unit_cost,
        "per_day_req": m.per_day_req, "warehouse": m.warehouse, "rack": m.rack, "bin": m.bin,
        "hsn_code": m.hsn_code, "lead_time_days": m.lead_time_days, "status": m.status,
    } for m in materials]
    buf = export_rows_to_excel(rows, MATERIAL_COLUMNS, "Materials")
    log_download(db, current_user.id, "materials_export.xlsx", "material_master", "xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=materials_export.xlsx"},
    )


@router.post("/import/excel")
async def import_materials(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "purchase")),
):
    rows = await parse_material_import_excel(file)
    created, updated, errors = 0, 0, []

    for i, row in enumerate(rows, start=2):
        code = str(row.get("material_code") or "").strip()
        if not code:
            continue
        savepoint = db.begin_nested()
        try:
            existing = db.query(Material).get(code)
            m_type = str(row.get("material_type") or "PRODUCTION").upper()
            if m_type not in VALID_TYPES:
                m_type = "PRODUCTION"

            # Optional "supplier_name" column: look the supplier up by name
            # (case-insensitive) and auto-create it if it doesn't exist yet,
            # so a single import file can bring in new suppliers too.
            supplier_id = None
            supplier_name = str(row.get("supplier_name") or "").strip()
            if supplier_name:
                supplier = db.query(Supplier).filter(
                    Supplier.supplier_name.ilike(supplier_name)
                ).first()
                if not supplier:
                    supplier = Supplier(supplier_name=supplier_name)
                    db.add(supplier)
                    db.flush()
                supplier_id = supplier.id

            def _dec(val):
                try:
                    return Decimal(str(val)) if val not in (None, "") else None
                except InvalidOperation:
                    return None

            if existing:
                existing.material_name = row.get("material_name") or existing.material_name
                existing.category = row.get("category") or existing.category
                existing.material_type = m_type
                existing.grade = row.get("grade") or existing.grade
                existing.size = row.get("size") or existing.size
                existing.uom = row.get("uom") or existing.uom
                existing.min_qty = _dec(row.get("min_qty")) or existing.min_qty
                existing.max_qty = _dec(row.get("max_qty")) or existing.max_qty
                existing.unit_cost = _dec(row.get("unit_cost")) or existing.unit_cost
                existing.warehouse = row.get("warehouse") or existing.warehouse
                existing.rack = row.get("rack") or existing.rack
                existing.bin = row.get("bin") or existing.bin
                existing.hsn_code = row.get("hsn_code") or existing.hsn_code
                if supplier_id:
                    existing.supplier_id = supplier_id
                updated += 1
            else:
                opening = _dec(row.get("opening_qty")) or Decimal("0")
                min_qty = _dec(row.get("min_qty"))
                max_qty = _dec(row.get("max_qty"))
                if m_type == "PRODUCTION" and (min_qty is None or max_qty is None):
                    # DB constraint requires both for PRODUCTION items. Default to a safe
                    # placeholder (flagged) rather than reject the row outright -- matches
                    # the same approach used when the original DB data was imported.
                    min_qty = min_qty if min_qty is not None else Decimal("0")
                    max_qty = max_qty if max_qty is not None else max(min_qty * 10, Decimal("1000"))
                    errors.append({"row": i, "material_code": code,
                                    "warning": "min_qty/max_qty defaulted, review threshold manually"})
                # Point: flag (don't block) possible duplicate Material Master
                # entries during bulk import -- same name already exists under
                # a different code. Import still proceeds; admin reviews and
                # deactivates/merges the older code afterwards.
                name_val = row.get("material_name") or code
                dup = db.query(Material).filter(
                    Material.material_name.ilike(str(name_val).strip())
                ).first()
                if dup:
                    errors.append({"row": i, "material_code": code,
                                    "warning": f"Possible duplicate: '{name_val}' already exists "
                                               f"as {dup.material_code} -- review before keeping both"})
                db.add(Material(
                    material_code=code,
                    material_name=row.get("material_name") or code,
                    category=row.get("category"),
                    material_type=m_type,
                    grade=row.get("grade"),
                    size=row.get("size"),
                    uom=row.get("uom") or "NOS",
                    min_qty=min_qty,
                    max_qty=max_qty,
                    opening_qty=opening,
                    current_qty=opening,
                    unit_cost=_dec(row.get("unit_cost")) or Decimal("0"),
                    warehouse=row.get("warehouse"),
                    rack=row.get("rack"),
                    bin=row.get("bin"),
                    hsn_code=row.get("hsn_code"),
                    supplier_id=supplier_id,
                ))
                created += 1
            db.flush()
        except Exception as e:  # noqa: BLE001
            savepoint.rollback()
            errors.append({"row": i, "material_code": code, "error": str(e)})

    db.commit()
    log_activity(db, current_user.id, f"Imported materials: {created} created, {updated} updated", "materials")
    return {"created": created, "updated": updated, "errors": errors}
