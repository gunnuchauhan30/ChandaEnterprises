from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.db.session import get_db
from app.core.deps import get_current_user, require_roles
from app.models import CriticalSpare, Material, User
from app.schemas.misc import CriticalSpareIn, CriticalSpareUpdate, CriticalSpareOut
from app.services.audit import log_activity

router = APIRouter(prefix="/critical-spares", tags=["Critical Spares List"])

VALID_PRIORITIES = {"critical", "high", "medium"}


def _to_out(spare: CriticalSpare) -> CriticalSpareOut:
    material = spare.material
    current_qty = material.current_qty if material else None
    return CriticalSpareOut(
        id=spare.id,
        material_code=spare.material_code,
        machine_name=spare.machine_name,
        priority=spare.priority.value if hasattr(spare.priority, "value") else spare.priority,
        threshold_qty=spare.threshold_qty,
        remarks=spare.remarks,
        added_by=spare.added_by,
        created_at=spare.created_at,
        updated_at=spare.updated_at,
        material_name=material.material_name if material else None,
        current_qty=current_qty,
        uom=material.uom if material else None,
        is_below_threshold=(current_qty is not None and current_qty <= spare.threshold_qty),
    )


@router.get("", response_model=List[CriticalSpareOut])
def list_critical_spares(
    priority: Optional[str] = None,
    below_threshold_only: bool = False,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(CriticalSpare)
    if priority:
        q = q.filter(CriticalSpare.priority == priority)
    if search:
        like = f"%{search}%"
        q = q.join(Material).filter(
            (Material.material_name.ilike(like)) | (CriticalSpare.material_code.ilike(like))
        )
    spares = q.order_by(CriticalSpare.priority, CriticalSpare.created_at.desc()).all()
    result = [_to_out(s) for s in spares]
    if below_threshold_only:
        result = [r for r in result if r.is_below_threshold]
    return result


@router.post("", response_model=CriticalSpareOut, status_code=201)
def create_critical_spare(
    payload: CriticalSpareIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "purchase")),
):
    if payload.priority not in VALID_PRIORITIES:
        raise HTTPException(400, f"priority must be one of {VALID_PRIORITIES}")
    if not db.query(Material).get(payload.material_code):
        raise HTTPException(404, "Material not found")

    spare = CriticalSpare(added_by=current_user.id, **payload.model_dump())
    db.add(spare)
    db.commit()
    db.refresh(spare)
    log_activity(db, current_user.id, f"Added critical spare {spare.material_code}", "critical_spares")
    return _to_out(spare)


@router.put("/{spare_id}", response_model=CriticalSpareOut)
def update_critical_spare(
    spare_id: int,
    payload: CriticalSpareUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "purchase")),
):
    spare = db.query(CriticalSpare).get(spare_id)
    if not spare:
        raise HTTPException(404, "Critical spare not found")
    updates = payload.model_dump(exclude_unset=True)
    if "priority" in updates and updates["priority"] not in VALID_PRIORITIES:
        raise HTTPException(400, f"priority must be one of {VALID_PRIORITIES}")
    for k, v in updates.items():
        setattr(spare, k, v)
    db.commit()
    db.refresh(spare)
    log_activity(db, current_user.id, f"Updated critical spare {spare.material_code}", "critical_spares")
    return _to_out(spare)


@router.delete("/{spare_id}", status_code=204)
def delete_critical_spare(
    spare_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "purchase")),
):
    spare = db.query(CriticalSpare).get(spare_id)
    if not spare:
        raise HTTPException(404, "Critical spare not found")
    db.delete(spare)
    db.commit()
    log_activity(db, current_user.id, f"Removed critical spare {spare.material_code}", "critical_spares")
