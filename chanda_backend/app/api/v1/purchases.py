import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from decimal import Decimal
from datetime import date

from app.db.session import get_db, SessionLocal
from app.core.deps import get_current_user, require_roles
from app.core.config import settings
from app.models import Purchase, Material, User
from app.schemas.purchases import PurchaseIn, PurchaseOut, PurchaseQCUpdate
from app.services.numbering import next_grn_no, next_lot_no
from app.services.audit import log_activity
from app.services.alert_notify import notify_new_alerts_for_material
from sqlalchemy import func

router = APIRouter(prefix="/purchases", tags=["Purchase / GRN"])

VALID_QC = {"pending", "passed", "failed"}


def _notify_alerts_task(material_code: str):
    """Runs after the response is sent. Opens its own DB session because the
    request-scoped session is already closed by then."""
    db = SessionLocal()
    try:
        notify_new_alerts_for_material(db, material_code)
    finally:
        db.close()


def _process_backorders_task(material_code: str, actor_user_id: int):
    """Point 12: after new stock lands (QC passed), automatically settle the
    FIFO backorder queue for that material before anyone has to click a
    button -- oldest pending employee request gets first claim on the new stock."""
    from app.api.v1.issues import _issue_against_request  # local import avoids a circular import at module load
    from app.models import EmployeeRequest

    db = SessionLocal()
    try:
        material = db.query(Material).get(material_code)
        if not material:
            return
        pending_reqs = (
            db.query(EmployeeRequest)
            .filter(EmployeeRequest.material_code == material_code, EmployeeRequest.status.in_(["partial", "pending"]))
            .order_by(EmployeeRequest.created_at.asc())
            .all()
        )
        for req in pending_reqs:
            remaining_needed = req.requested_qty - (req.fulfilled_qty or 0)
            if remaining_needed <= 0:
                continue
            db.refresh(material)
            if material.available_qty <= 0:
                break
            fulfill_qty = min(material.available_qty, remaining_needed)
            _issue_against_request(db, req, fulfill_qty, actor_user_id)
            req.approved_by = req.approved_by or actor_user_id
            req.approved_at = req.approved_at or func.now()
            req.status = "completed" if req.fulfilled_qty >= req.requested_qty else "partial"
        db.commit()
    finally:
        db.close()


@router.get("", response_model=List[PurchaseOut])
def list_purchases(
    material_code: Optional[str] = None,
    supplier_id: Optional[int] = None,
    qc_status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Purchase)
    if material_code:
        q = q.filter(Purchase.material_code == material_code)
    if supplier_id:
        q = q.filter(Purchase.supplier_id == supplier_id)
    if qc_status:
        q = q.filter(Purchase.qc_status == qc_status)
    if date_from:
        q = q.filter(Purchase.invoice_date >= date_from)
    if date_to:
        q = q.filter(Purchase.invoice_date <= date_to)
    return q.order_by(Purchase.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()


@router.get("/{purchase_id}", response_model=PurchaseOut)
def get_purchase(purchase_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = db.query(Purchase).get(purchase_id)
    if not p:
        raise HTTPException(404, "Purchase/GRN not found")
    return p


@router.post("", response_model=PurchaseOut, status_code=201)
def create_grn(
    payload: PurchaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("purchase", "store_manager")),
):
    """
    Generates a GRN. Stock is NOT increased yet -- the DB trigger only
    increases current_qty once qc_status is set to 'passed' (see
    PATCH /{id}/qc). This enforces: no material enters usable stock
    without QC sign-off.
    """
    if not db.query(Material).get(payload.material_code):
        raise HTTPException(404, "Material not found")

    grn_no = next_grn_no(db)
    payload_data = payload.model_dump()
    # Point 5: Lot No. is always an auto-generated series (LOT-000001, ...),
    # never hand-typed -- whatever the frontend sent for batch_no is ignored.
    payload_data["batch_no"] = next_lot_no(db)
    purchase = Purchase(
        grn_no=grn_no,
        received_by=current_user.id,
        created_by=current_user.id,
        **payload_data,
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)
    log_activity(db, current_user.id, f"Created GRN {grn_no} for {payload.material_code} (Lot {purchase.batch_no})", "purchases")
    return purchase


@router.patch("/{purchase_id}/qc", response_model=PurchaseOut)
def update_qc_status(
    purchase_id: int,
    payload: PurchaseQCUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("quality", "admin")),
):
    """QC pass/fail is exclusively the Quality role's job now (admin keeps an
    override for exceptional cases). Setting qc_status='passed' here is what
    actually triggers the automatic stock increase (DB trigger trg_purchase_stock),
    which in turn may flip a
    low/high stock threshold and write an `alerts` row (trg_check_stock_thresholds).
    After commit we kick off a background task that emails the right people
    and creates in-app notifications for any such new alert."""
    if payload.qc_status not in VALID_QC:
        raise HTTPException(400, f"qc_status must be one of {VALID_QC}")
    purchase = db.query(Purchase).get(purchase_id)
    if not purchase:
        raise HTTPException(404, "Purchase/GRN not found")

    purchase.qc_status = payload.qc_status
    purchase.qc_remarks = payload.qc_remarks
    purchase.received_by = current_user.id
    db.commit()
    db.refresh(purchase)
    log_activity(db, current_user.id, f"GRN {purchase.grn_no} QC set to {payload.qc_status}", "purchases")

    if payload.qc_status == "passed":
        background_tasks.add_task(_notify_alerts_task, purchase.material_code)
        background_tasks.add_task(_process_backorders_task, purchase.material_code, current_user.id)

    return purchase


@router.post("/{purchase_id}/invoice")
async def upload_invoice(
    purchase_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("purchase", "store_manager")),
):
    purchase = db.query(Purchase).get(purchase_id)
    if not purchase:
        raise HTTPException(404, "Purchase/GRN not found")
    if not file.filename.lower().endswith(".pdf") and not file.content_type.startswith("image/"):
        raise HTTPException(400, "Invoice must be a PDF or image file")

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {settings.MAX_UPLOAD_MB}MB limit")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    stored_name = f"{purchase.grn_no}_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(settings.UPLOAD_DIR, stored_name)
    with open(path, "wb") as f:
        f.write(contents)

    purchase.invoice_file_path = path
    db.commit()
    log_activity(db, current_user.id, f"Uploaded invoice for GRN {purchase.grn_no}", "purchases")
    return {"message": "Invoice uploaded", "path": path}
