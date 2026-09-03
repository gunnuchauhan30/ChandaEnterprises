from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text, func
from sqlalchemy.orm import Session
from typing import Optional, List

from app.db.session import get_db
from app.core.deps import get_current_user, require_roles
from app.models import StockBatch, StockLedger, Material, User, StockReconciliation, Return, Purchase, Supplier
from app.schemas.misc import StockBatchOut, StockLedgerOut, ReconciliationIn, ReconciliationDecision, ReconciliationOut
from app.schemas.materials import MaterialOut
from app.services.numbering import next_return_no
from app.services.audit import log_activity

router = APIRouter(prefix="/inventory", tags=["Inventory"])


def _reco_out(r: StockReconciliation) -> ReconciliationOut:
    return ReconciliationOut(
        id=r.id, material_code=r.material_code, system_qty=r.system_qty,
        physical_qty=r.physical_qty, difference_qty=r.difference_qty, remarks=r.remarks,
        status=r.status.value if hasattr(r.status, "value") else r.status,
        counted_by=r.counted_by, reviewed_by=r.reviewed_by, review_remarks=r.review_remarks,
        return_id=r.return_id, created_at=r.created_at, reviewed_at=r.reviewed_at,
        material_name=r.material.material_name if r.material else None,
    )


@router.get("/batches", response_model=List[StockBatchOut])
def list_batches(
    material_code: Optional[str] = None,
    only_available: bool = True,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """FIFO batch tracking view."""
    q = db.query(StockBatch)
    if material_code:
        q = q.filter(StockBatch.material_code == material_code)
    if only_available:
        q = q.filter(StockBatch.remaining_qty > 0)
    return q.order_by(StockBatch.received_date.asc()).all()


@router.get("/ledger", response_model=List[StockLedgerOut])
def stock_ledger(
    material_code: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Full append-only movement history -- the single source of truth for current_qty."""
    q = db.query(StockLedger)
    if material_code:
        q = q.filter(StockLedger.material_code == material_code)
    return q.order_by(StockLedger.id.desc()).offset((page - 1) * page_size).limit(page_size).all()


@router.get("/valuation")
def stock_valuation(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Uses the DB view vw_stock_valuation (current_qty * unit_cost per material)."""
    rows = db.execute(text("SELECT * FROM vw_stock_valuation")).mappings().all()
    return [dict(r) for r in rows]


@router.get("/aging")
def stock_aging(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Uses the DB view vw_stock_aging (age of each remaining batch, for FIFO/aging analysis)."""
    rows = db.execute(text("SELECT * FROM vw_stock_aging")).mappings().all()
    return [dict(r) for r in rows]


@router.get("/summary")
def inventory_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """
    Opening / Current / Reserved / Available snapshot across all materials,
    plus a FIFO supplier-wise breakdown (`suppliers`) of the batches that
    make up each material's remaining stock -- oldest batch first, same
    order fn_trg_issue_stock consumes them in on an actual Issue. Since a
    material can have stock left over from more than one supplier, this
    lets the UI show one sub-row per supplier under each material, with the
    material-level fields above acting as the authoritative TOTAL row.
    """
    materials = db.query(Material).all()

    batch_rows = (
        db.query(
            StockBatch.material_code,
            Supplier.supplier_name,
            func.sum(StockBatch.remaining_qty).label("qty"),
            func.min(StockBatch.received_date).label("oldest_date"),
        )
        .outerjoin(Purchase, StockBatch.purchase_id == Purchase.id)
        .outerjoin(Supplier, Purchase.supplier_id == Supplier.id)
        .filter(StockBatch.remaining_qty > 0)
        .group_by(StockBatch.material_code, Supplier.supplier_name)
        .order_by(StockBatch.material_code, func.min(StockBatch.received_date).asc())
        .all()
    )
    suppliers_by_material = {}
    for row in batch_rows:
        suppliers_by_material.setdefault(row.material_code, []).append({
            "supplier_name": row.supplier_name or "Direct / Unassigned",
            "qty": float(row.qty or 0),
            "oldest_date": row.oldest_date.isoformat() if row.oldest_date else None,
        })

    return [{
        "material_code": m.material_code,
        "material_name": m.material_name,
        "opening_qty": m.opening_qty,
        "current_qty": m.current_qty,
        "reserved_qty": m.reserved_qty,
        "available_qty": m.available_qty,
        "warehouse": m.warehouse, "rack": m.rack, "bin": m.bin,
        "suppliers": suppliers_by_material.get(m.material_code, []),
    } for m in materials]


# ================= Physical Stock Reconciliation =================
# Store Manager (or admin) enters a physical count -> system computes the
# mismatch and parks it as 'pending'. Nothing touches current_qty until
# Admin approves. On approval, an 'adjustment' Return row is inserted, which
# the existing DB trigger (fn_trg_return_stock) posts to stock_ledger --
# same source-of-truth path every other stock movement uses.

@router.get("/reconciliations", response_model=List[ReconciliationOut])
def list_reconciliations(
    status: Optional[str] = Query(None, description="pending|approved|rejected"),
    material_code: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(StockReconciliation)
    if status:
        q = q.filter(StockReconciliation.status == status)
    if material_code:
        q = q.filter(StockReconciliation.material_code == material_code)
    rows = q.order_by(StockReconciliation.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return [_reco_out(r) for r in rows]


@router.post("/reconciliations", response_model=ReconciliationOut, status_code=201)
def create_reconciliation(
    payload: ReconciliationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager")),
):
    """Store Manager records a physical count. current_qty is snapshotted
    right now as system_qty -- the diff is informational only until an
    admin approves it; current_qty itself is never touched here."""
    material = db.query(Material).get(payload.material_code)
    if not material:
        raise HTTPException(404, "Material not found")

    system_qty = material.current_qty
    diff = payload.physical_qty - system_qty

    reco = StockReconciliation(
        material_code=payload.material_code,
        system_qty=system_qty,
        physical_qty=payload.physical_qty,
        difference_qty=diff,
        remarks=payload.remarks,
        counted_by=current_user.id,
        status="pending",
    )
    db.add(reco)
    db.commit()
    db.refresh(reco)
    log_activity(db, current_user.id,
                 f"Physical count for {payload.material_code}: system={system_qty}, "
                 f"physical={payload.physical_qty}, diff={diff}", "inventory")
    return _reco_out(reco)


@router.patch("/reconciliations/{reco_id}/decision", response_model=ReconciliationOut)
def decide_reconciliation(
    reco_id: int,
    payload: ReconciliationDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Admin-only approve/reject. Approve books the difference as a stock
    ADJUSTMENT (via the returns/adjustment path) so current_qty and the
    ledger both update in the same trusted trigger path as every other
    stock movement in this system."""
    reco = db.query(StockReconciliation).get(reco_id)
    if not reco:
        raise HTTPException(404, "Reconciliation not found")
    if reco.status != "pending":
        raise HTTPException(400, f"Reconciliation already {reco.status}")

    if payload.action == "approve":
        if reco.difference_qty != 0:
            ret = Return(
                return_no=next_return_no(db),
                material_code=reco.material_code,
                return_type="adjustment",
                adjustment_qty=reco.difference_qty,
                reason=f"Physical stock reconciliation #{reco.id}"
                       + (f" — {reco.remarks}" if reco.remarks else ""),
                approved_by=current_user.id,
                created_by=current_user.id,
            )
            db.add(ret)
            db.flush()  # get ret.id, trigger fires on this INSERT
            reco.return_id = ret.id
        reco.status = "approved"
    elif payload.action == "reject":
        reco.status = "rejected"
    else:
        raise HTTPException(400, "action must be 'approve' or 'reject'")

    reco.reviewed_by = current_user.id
    reco.review_remarks = payload.review_remarks
    from datetime import datetime
    reco.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(reco)
    log_activity(db, current_user.id, f"{payload.action.title()}d reconciliation #{reco.id}", "inventory")
    return _reco_out(reco)


# ================= Quick Stock Edit (Material Master list) =================
# Point: "current stock" needed an edit option directly from the Material
# Master list. current_qty is intentionally never hand-set on the Material
# row itself (see MaterialUpdate) -- so this does NOT bypass that rule. It
# is a thin, admin-only wrapper around the exact same reconciliation ->
# adjustment -> stock_ledger trigger path used above, just created and
# auto-approved in one call instead of being left pending for a second
# admin to review. Every edit still lands in stock_reconciliations,
# returns (as an 'adjustment' row) and stock_ledger -- fully auditable.

@router.post("/quick-adjust", response_model=MaterialOut)
def quick_adjust_stock(
    payload: ReconciliationIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """One-step current-stock correction for the Material Master list's
    inline edit action. Admin-only -- Store Managers still use the
    two-step /reconciliations flow (submit -> separate admin approval)."""
    material = db.query(Material).get(payload.material_code)
    if not material:
        raise HTTPException(404, "Material not found")

    system_qty = material.current_qty
    diff = payload.physical_qty - system_qty

    reco = StockReconciliation(
        material_code=payload.material_code,
        system_qty=system_qty,
        physical_qty=payload.physical_qty,
        difference_qty=diff,
        remarks=payload.remarks or "Quick stock edit from Material Master list",
        counted_by=current_user.id,
        status="pending",
    )
    db.add(reco)
    db.flush()  # get reco.id for the reason text below

    if diff != 0:
        ret = Return(
            return_no=next_return_no(db),
            material_code=payload.material_code,
            return_type="adjustment",
            adjustment_qty=diff,
            reason=f"Quick stock edit (reconciliation #{reco.id})"
                   + (f" — {payload.remarks}" if payload.remarks else ""),
            approved_by=current_user.id,
            created_by=current_user.id,
        )
        db.add(ret)
        db.flush()  # trigger fires on this INSERT -> updates current_qty + stock_ledger
        reco.return_id = ret.id

    reco.status = "approved"
    reco.reviewed_by = current_user.id
    reco.review_remarks = "Auto-approved via quick edit"
    from datetime import datetime
    reco.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(material)
    log_activity(db, current_user.id,
                 f"Quick stock edit for {payload.material_code}: {system_qty} -> {payload.physical_qty}",
                 "inventory")
    return material
