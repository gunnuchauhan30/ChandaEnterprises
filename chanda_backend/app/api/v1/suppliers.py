from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.db.session import get_db
from app.core.deps import get_current_user, require_roles
from app.models import Supplier, Material, User
from app.schemas.materials import SupplierIn, SupplierOut
from app.services.audit import log_activity

router = APIRouter(prefix="/suppliers", tags=["Supplier Master"])


@router.get("", response_model=List[SupplierOut])
def list_suppliers(
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Supplier)
    if search:
        q = q.filter(Supplier.supplier_name.ilike(f"%{search}%"))
    if is_active is not None:
        q = q.filter(Supplier.is_active == is_active)
    return q.order_by(Supplier.supplier_name).offset((page - 1) * page_size).limit(page_size).all()


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    return supplier


@router.get("/{supplier_id}/materials")
def supplier_materials(supplier_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Material).filter(Material.supplier_id == supplier_id).all()


@router.post("", response_model=SupplierOut, status_code=201)
def create_supplier(
    payload: SupplierIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("purchase", "store_manager")),
):
    if db.query(Supplier).filter(Supplier.supplier_name == payload.supplier_name).first():
        raise HTTPException(409, "Supplier with this name already exists")
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    log_activity(db, current_user.id, f"Created supplier {supplier.supplier_name}", "suppliers")
    return supplier


@router.put("/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    payload: SupplierIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("purchase", "store_manager")),
):
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    for k, v in payload.model_dump().items():
        setattr(supplier, k, v)
    db.commit()
    db.refresh(supplier)
    log_activity(db, current_user.id, f"Updated supplier {supplier_id}", "suppliers")
    return supplier


@router.delete("/{supplier_id}", status_code=204)
def deactivate_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("purchase", "store_manager")),
):
    """Soft-delete: suppliers are never hard-deleted (referenced by purchase history)."""
    supplier = db.query(Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(404, "Supplier not found")
    supplier.is_active = False
    db.commit()
    log_activity(db, current_user.id, f"Deactivated supplier {supplier_id}", "suppliers")
