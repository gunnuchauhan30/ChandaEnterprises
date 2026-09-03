from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List

from app.db.session import get_db, SessionLocal
from app.core.deps import get_current_user, require_roles
from app.models import EmployeeRequest, Issue, Return, Material, User, StockBatch, Purchase, Supplier
from app.schemas.issues import (
    EmployeeRequestIn, EmployeeRequestOut, EmployeeRequestDecision,
    IssueIn, IssueOut, IssueConsumptionUpdate,
    ReturnIn, ReturnOut, FIFOCheckIn,
)
from app.services.numbering import next_request_no, next_issue_no, next_return_no
from app.services.audit import log_activity, log_download
from app.services.alert_notify import notify_new_alerts_for_material
from app.services.excel_service import export_rows_to_excel


def _notify_alerts_task(material_code: str):
    """Runs after the response is sent, in its own DB session (see purchases.py)."""
    db = SessionLocal()
    try:
        notify_new_alerts_for_material(db, material_code)
    finally:
        db.close()

router = APIRouter(tags=["Material Issue / Route Card / Return"])


# ================= Employee Requests =================

@router.get("/employee-requests", response_model=List[EmployeeRequestOut])
def list_requests(
    status: Optional[str] = None,
    department: Optional[str] = None,
    my_requests_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(EmployeeRequest)
    if status:
        q = q.filter(EmployeeRequest.status == status)
    if department:
        q = q.filter(EmployeeRequest.department == department)
    if my_requests_only:
        q = q.filter(EmployeeRequest.requested_by == current_user.id)
    return q.order_by(EmployeeRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()


@router.post("/employee-requests", response_model=EmployeeRequestOut, status_code=201)
def create_request(
    payload: EmployeeRequestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Any authenticated employee (typically 'production' role) can raise a material request."""
    material = db.query(Material).get(payload.material_code)
    if not material:
        raise HTTPException(404, "Material not found")

    req = EmployeeRequest(
        request_no=next_request_no(db),
        requested_by=current_user.id,
        **payload.model_dump(),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    log_activity(db, current_user.id, f"Raised material request {req.request_no}", "employee_requests")

    # Point 8: if the store doesn't have enough right now, tell the employee
    # immediately (instead of silently failing later at approval time) so
    # they can knowingly submit a lower quantity, or accept it'll be a
    # partial/backorder fulfilment via the FIFO queue (point 12).
    out = EmployeeRequestOut.model_validate(req)
    if material.available_qty < req.requested_qty:
        out.stock_warning = (
            f"Only {material.available_qty} {material.uom} available in store right now "
            f"(you requested {req.requested_qty}). It may be issued in part now and the rest "
            f"queued as a backorder until new stock arrives."
        )
    return out


def _issue_against_request(db: Session, req: EmployeeRequest, fulfill_qty, issued_by_id: int) -> Issue:
    """
    Creates one Issue row for `fulfill_qty` against a request. Inserting into
    `issues` fires the existing DB trigger (fn_trg_issue_stock) which deducts
    material.current_qty and consumes FIFO stock_batches automatically -- so
    stock only ever moves through this one, already-battle-tested code path,
    whether it's a full approval or a partial/backorder top-up.
    """
    issue = Issue(
        issue_no=next_issue_no(db),
        material_code=req.material_code,
        employee_request_id=req.id,
        job_card_no=req.job_card_no,
        part_number=req.part_number,
        department=req.department,
        issue_qty=fulfill_qty,
        consumed_qty=0,
        completion_status="issued",
        issued_by=issued_by_id,
    )
    db.add(issue)
    db.flush()  # let trg_issue_stock run now, so material.available_qty is fresh for the next loop iteration
    req.fulfilled_qty = (req.fulfilled_qty or 0) + fulfill_qty
    return issue


@router.patch("/employee-requests/{request_id}/decision", response_model=EmployeeRequestOut)
def decide_request(
    request_id: int,
    payload: EmployeeRequestDecision,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager")),
):
    """
    Approve/reject a request.

    Point 11 (stock only ever moves after approval): unchanged and confirmed --
    nothing here touches material.current_qty until this endpoint runs; a
    pending request never reserves or deducts stock by itself.

    Point 12 (FIFO backorders): if there isn't enough available stock to
    cover the whole request, we issue whatever IS available right now and
    leave the rest as `pending_qty` with status='partial'. It then sits in
    the FIFO backorder queue (oldest request first) and gets topped up
    automatically as new stock arrives (see process_backorders below).
    """
    req = db.query(EmployeeRequest).get(request_id)
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status not in ("pending", "partial"):
        raise HTTPException(400, f"Request already {req.status}")

    if payload.action == "approve":
        # Lock the material row for the rest of this transaction. Without
        # this, two approvals for the same material at nearly the same
        # moment could both read the same available_qty, both think there's
        # enough stock, and the second one would crash with a 500 when the
        # DB's own overselling guard (fn_post_stock_ledger) rejects it. The
        # lock makes the second request simply wait a moment and then see
        # the correct, now-updated stock instead of racing.
        material = db.query(Material).filter(Material.material_code == req.material_code).with_for_update().first()
        remaining_needed = req.requested_qty - (req.fulfilled_qty or 0)
        fulfill_qty = min(material.available_qty, remaining_needed)

        if fulfill_qty <= 0:
            raise HTTPException(400, f"No stock available right now: have {material.available_qty}")

        _issue_against_request(db, req, fulfill_qty, current_user.id)
        req.approved_by = current_user.id
        req.approved_at = func.now()

        if req.fulfilled_qty >= req.requested_qty:
            req.status = "completed"
        else:
            req.status = "partial"  # rest queued as FIFO backorder

    elif payload.action == "reject":
        req.status = "rejected"
        req.approved_by = current_user.id
        req.rejection_reason = payload.rejection_reason
    else:
        raise HTTPException(400, "action must be 'approve' or 'reject'")

    db.commit()
    db.refresh(req)
    log_activity(
        db, current_user.id,
        f"{payload.action.title()}d request {req.request_no}"
        + (f" ({req.status})" if payload.action == "approve" else ""),
        "employee_requests",
    )

    if payload.action == "approve":
        background_tasks.add_task(_notify_alerts_task, req.material_code)

    return req


@router.get("/employee-requests/backorders", response_model=List[EmployeeRequestOut])
def list_backorders(
    material_code: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Point 12: the FIFO backorder queue -- every request that still has
    pending_qty > 0, oldest first. This is what the dedicated Backorders
    page reads from.
    """
    q = db.query(EmployeeRequest).filter(EmployeeRequest.status.in_(["partial", "pending"]))
    if material_code:
        q = q.filter(EmployeeRequest.material_code == material_code)
    rows = q.order_by(EmployeeRequest.created_at.asc()).all()
    return [r for r in rows if (r.requested_qty - (r.fulfilled_qty or 0)) > 0]


@router.post("/employee-requests/backorders/process/{material_code}")
def process_backorders(
    material_code: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager")),
):
    """
    Point 12 (FIFO settlement): call this whenever new stock has just come in
    for a material (e.g. automatically after a Purchase/GRN passes QC -- see
    purchases.py). Walks every open backorder for that material, oldest
    request first, and tops each one up from available stock until either
    the queue is empty or the stock runs out.
    """
    # Lock the material row for this whole settlement pass -- same reasoning
    # as decide_request above: prevents two "Try Fulfill" calls for the same
    # material (double-click, or two people clicking at once) from both
    # reading stale available_qty and racing each other into a 500.
    material = db.query(Material).filter(Material.material_code == material_code).with_for_update().first()
    if not material:
        raise HTTPException(404, "Material not found")

    pending_reqs = (
        db.query(EmployeeRequest)
        .filter(
            EmployeeRequest.material_code == material_code,
            EmployeeRequest.status.in_(["partial", "pending"]),
        )
        .order_by(EmployeeRequest.created_at.asc())  # FIFO: oldest first
        .all()
    )

    settled, still_pending = [], []
    for req in pending_reqs:
        remaining_needed = req.requested_qty - (req.fulfilled_qty or 0)
        if remaining_needed <= 0:
            continue
        db.refresh(material)  # pick up stock consumed by earlier iterations of this same loop
        if material.available_qty <= 0:
            still_pending.append(req.request_no)
            continue

        fulfill_qty = min(material.available_qty, remaining_needed)
        _issue_against_request(db, req, fulfill_qty, current_user.id)
        req.approved_by = req.approved_by or current_user.id
        req.approved_at = req.approved_at or func.now()
        req.status = "completed" if req.fulfilled_qty >= req.requested_qty else "partial"
        settled.append({"request_no": req.request_no, "issued_now": float(fulfill_qty), "status": req.status})

    db.commit()
    log_activity(
        db, current_user.id,
        f"Processed FIFO backorders for {material_code}: {len(settled)} request(s) topped up",
        "employee_requests",
    )
    background_tasks.add_task(_notify_alerts_task, material_code)
    return {"material_code": material_code, "settled": settled, "still_pending": still_pending}


# ================= Issues (Route Card) =================

@router.get("/issues", response_model=List[IssueOut])
def list_issues(
    material_code: Optional[str] = None,
    job_card_no: Optional[str] = None,
    production_order_no: Optional[str] = None,
    department: Optional[str] = None,
    completion_status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Issue)
    if material_code:
        q = q.filter(Issue.material_code == material_code)
    if job_card_no:
        q = q.filter(Issue.job_card_no == job_card_no)
    if production_order_no:
        q = q.filter(Issue.production_order_no == production_order_no)
    if department:
        q = q.filter(Issue.department == department)
    if completion_status:
        q = q.filter(Issue.completion_status == completion_status)
    rows = q.order_by(Issue.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    issuer_ids = {r.issued_by for r in rows if r.issued_by}
    names = {u.id: (u.full_name or u.username) for u in db.query(User).filter(User.id.in_(issuer_ids)).all()} \
        if issuer_ids else {}
    out = []
    for r in rows:
        item = IssueOut.model_validate(r)
        item.issued_by_name = names.get(r.issued_by)
        out.append(item)
    return out


@router.post("/issues/fifo-check")
def fifo_check(
    payload: FIFOCheckIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Read-only FIFO preview for the Issue form: shows exactly which supplier
    batches this quantity would be pulled from (oldest received_date first)
    if issued right now -- Supplier -> Available -> Issue -> Remaining, same
    order the real fn_trg_issue_stock DB trigger consumes stock_batches in.

    This does NOT write anything (no stock_batches/current_qty change, no
    Issue row) -- the actual deduction only ever happens via POST /issues.
    """
    material = db.query(Material).filter(Material.material_code == payload.material_code).first()
    if not material:
        raise HTTPException(404, "Material not found")

    batches = (
        db.query(StockBatch, Supplier.supplier_name)
        .outerjoin(Purchase, StockBatch.purchase_id == Purchase.id)
        .outerjoin(Supplier, Purchase.supplier_id == Supplier.id)
        .filter(StockBatch.material_code == payload.material_code, StockBatch.remaining_qty > 0)
        .order_by(StockBatch.received_date.asc(), StockBatch.id.asc())
        .all()
    )

    remaining_needed = float(payload.quantity)
    allocation = []
    for batch, supplier_name in batches:
        available = float(batch.remaining_qty)
        issue_qty = min(available, remaining_needed) if remaining_needed > 0 else 0.0
        allocation.append({
            "supplier_name": supplier_name or "Direct / Unassigned",
            "batch_no": batch.batch_no,
            "received_date": batch.received_date.isoformat() if batch.received_date else None,
            "available": available,
            "issue_qty": issue_qty,
            "remaining_after": available - issue_qty,
        })
        remaining_needed -= issue_qty

    total_available = sum(a["available"] for a in allocation)
    total_allocated = sum(a["issue_qty"] for a in allocation)
    shortfall = max(0.0, float(payload.quantity) - total_allocated)

    return {
        "material_code": material.material_code,
        "material_name": material.material_name,
        "uom": material.uom,
        "quantity_requested": float(payload.quantity),
        "total_available": total_available,
        "total_allocated": total_allocated,
        "shortfall": shortfall,
        "status": "success" if shortfall <= 0 else "insufficient",
        "allocation": allocation,
    }


@router.get("/issues/{issue_id}/fifo-source")
def issue_fifo_source(
    issue_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Read-only: which supplier/batch this ALREADY-ISSUED row actually came
    from, so the 'Update consumption' action can show the same FIFO
    Supplier Breakdown card as the New Issue form before the user fills
    in the consumed quantity.

    Issue.lot_no is the batch that was oldest (i.e. FIFO-first) at the
    moment this issue was created (see create_direct_issue below) --
    that's the batch/supplier we look up here. Note: if the issued qty
    was large enough to span more than one batch, the DB trigger
    (fn_trg_issue_stock) does the multi-batch FIFO deduction but doesn't
    persist a per-batch split anywhere, so lot_no reflects the first/
    oldest batch drawn from, not necessarily every batch touched.
    """
    issue = db.query(Issue).get(issue_id)
    if not issue:
        raise HTTPException(404, "Issue not found")

    if not issue.lot_no:
        return {"issue_id": issue.id, "issue_qty": float(issue.issue_qty), "allocation": []}

    batch, supplier_name = (
        db.query(StockBatch, Supplier.supplier_name)
        .outerjoin(Purchase, StockBatch.purchase_id == Purchase.id)
        .outerjoin(Supplier, Purchase.supplier_id == Supplier.id)
        .filter(StockBatch.material_code == issue.material_code, StockBatch.batch_no == issue.lot_no)
        .first()
    ) or (None, None)

    if not batch:
        return {"issue_id": issue.id, "issue_qty": float(issue.issue_qty), "allocation": []}

    available_now = float(batch.remaining_qty)

    # Same shape as one row of /issues/fifo-check's `allocation` array, so
    # the frontend can render it with the exact same flow-card component
    # used on the New Issue page. issue_qty here is what THIS issue actually
    # took at the time it was created (not a fresh recalculation).
    return {
        "issue_id": issue.id,
        "issue_qty": float(issue.issue_qty),
        "allocation": [{
            "supplier_name": supplier_name or "Direct / Unassigned",
            "batch_no": issue.lot_no,
            "received_date": batch.received_date.isoformat() if batch.received_date else None,
            "available": available_now,
            "issue_qty": float(issue.issue_qty),
            "remaining_after": available_now,
        }],
    }


@router.post("/issues", response_model=IssueOut, status_code=201)
def create_direct_issue(
    payload: IssueIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager")),
):
    """Direct store issue against a Production Order / Job Card / Machine /
    Operation (Route Card module) -- used when material is issued straight
    from the floor without going through the employee-request workflow."""
    # Same row-lock reasoning as decide_request / process_backorders: two
    # direct issues for the same material at nearly the same instant should
    # queue up rather than race and crash.
    material = db.query(Material).filter(Material.material_code == payload.material_code).with_for_update().first()
    if not material:
        raise HTTPException(404, "Material not found")
    if material.available_qty < payload.issue_qty:
        raise HTTPException(400, f"Insufficient available stock: have {material.available_qty}")

    payload_data = payload.model_dump()
    if not payload_data.get("lot_no"):
        # Point 5: same series that GRN generated (LOT-000001, ...) --
        # picked from the oldest batch with stock left, i.e. the one FIFO
        # will actually consume for this issue, so the Route Card print
        # always shows the lot that's genuinely going out the door.
        oldest_batch = (
            db.query(StockBatch)
            .filter(StockBatch.material_code == payload.material_code, StockBatch.remaining_qty > 0)
            .order_by(StockBatch.received_date.asc(), StockBatch.id.asc())
            .first()
        )
        if oldest_batch:
            payload_data["lot_no"] = oldest_batch.batch_no

    issue = Issue(
        issue_no=next_issue_no(db),
        issued_by=current_user.id,
        **payload_data,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    log_activity(db, current_user.id, f"Issued {issue.issue_no} for job card {payload.job_card_no}", "issues")
    background_tasks.add_task(_notify_alerts_task, issue.material_code)
    return issue


@router.patch("/issues/{issue_id}/consumption", response_model=IssueOut)
def update_consumption(
    issue_id: int,
    payload: IssueConsumptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("production", "store_manager")),
):
    """Update how much of an issued batch was actually consumed on the
    machine -- pending_qty (issue_qty - consumed_qty) is DB-computed."""
    issue = db.query(Issue).get(issue_id)
    if not issue:
        raise HTTPException(404, "Issue not found")
    if payload.consumed_qty > issue.issue_qty:
        raise HTTPException(400, "consumed_qty cannot exceed issue_qty")

    issue.consumed_qty = payload.consumed_qty
    issue.completion_status = payload.completion_status
    db.commit()
    db.refresh(issue)
    log_activity(db, current_user.id, f"Updated consumption for {issue.issue_no}", "issues")
    return issue


# ================= Route Card (formatted view of Issues) =================
# Same underlying data as /issues, reshaped to match the company's actual
# Excel Route Card sheet columns: Sr No, Date, Part Name, Issue Qty,
# Job-Card No, Lot No, Issue By, Department, Remark, Shift, Received.
# No separate data entry -- this is a read (+ export) view, per the
# finalized plan (Option A).

ROUTE_CARD_COLUMNS = [
    "sr_no", "date", "part_name", "issue_qty", "job_card_no", "lot_no",
    "issue_by", "department", "remark", "shift", "received",
]


def _route_card_rows(db: Session, date_from, date_to, department, job_card_no, shift):
    q = db.query(Issue)
    if date_from:
        q = q.filter(Issue.issue_date >= date_from)
    if date_to:
        q = q.filter(Issue.issue_date <= date_to)
    if department:
        q = q.filter(Issue.department == department)
    if job_card_no:
        q = q.filter(Issue.job_card_no == job_card_no)
    if shift:
        q = q.filter(Issue.shift == shift)
    issues = q.order_by(Issue.issue_date.asc(), Issue.id.asc()).all()

    user_ids = {i.issued_by for i in issues if i.issued_by}
    users = {u.id: u.full_name or u.username for u in db.query(User).filter(User.id.in_(user_ids)).all()} \
        if user_ids else {}

    rows = []
    for idx, i in enumerate(issues, start=1):
        # part_name falls back to the material name when no separate
        # part_number was captured on the issue (mirrors the Excel sheet,
        # where "Part Name" is really the material description).
        material = db.query(Material).get(i.material_code)
        part_name = i.part_number or (material.material_name if material else i.material_code)
        rows.append({
            "sr_no": idx,
            "date": i.issue_date.isoformat() if i.issue_date else "",
            "part_name": part_name,
            "issue_qty": float(i.issue_qty or 0),
            "job_card_no": i.job_card_no or "",
            "lot_no": i.lot_no or "",
            "issue_by": users.get(i.issued_by, "store"),
            "department": i.department or "",
            "remark": i.remark or "Issued",
            "shift": i.shift or "",
            "received": "Yes" if i.completion_status == "completed" else "",
        })
    return rows


@router.get("/issues/route-card")
def route_card(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    department: Optional[str] = None,
    job_card_no: Optional[str] = None,
    shift: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _route_card_rows(db, date_from, date_to, department, job_card_no, shift)


@router.get("/issues/route-card/export/excel")
def export_route_card(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    department: Optional[str] = None,
    job_card_no: Optional[str] = None,
    shift: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = _route_card_rows(db, date_from, date_to, department, job_card_no, shift)
    buf = export_rows_to_excel(rows, ROUTE_CARD_COLUMNS, sheet_title="Route Card")
    log_download(db, current_user.id, "route-card.xlsx", "route_card", "excel")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=route-card.xlsx"},
    )


# ================= Returns =================

@router.get("/returns", response_model=List[ReturnOut])
def list_returns(
    material_code: Optional[str] = None,
    return_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Return)
    if material_code:
        q = q.filter(Return.material_code == material_code)
    if return_type:
        q = q.filter(Return.return_type == return_type)
    return q.order_by(Return.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()


@router.post("/returns", response_model=ReturnOut, status_code=201)
def create_return(
    payload: ReturnIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager")),
):
    valid_types = {"unused", "vendor_return", "rejected", "adjustment"}
    if payload.return_type not in valid_types:
        raise HTTPException(400, f"return_type must be one of {valid_types}")
    if payload.return_type == "adjustment" and payload.adjustment_qty is None:
        raise HTTPException(400, "adjustment_qty is required for return_type='adjustment'")
    if payload.return_type != "adjustment" and not payload.qty:
        raise HTTPException(400, "qty is required for this return_type")
    if not db.query(Material).get(payload.material_code):
        raise HTTPException(404, "Material not found")

    ret = Return(
        return_no=next_return_no(db),
        approved_by=current_user.id,
        created_by=current_user.id,
        **payload.model_dump(),
    )
    db.add(ret)
    db.commit()
    db.refresh(ret)
    log_activity(db, current_user.id, f"Recorded return {ret.return_no} ({payload.return_type})", "returns")
    # unused/adjustment returns can push stock back up into high-stock territory
    background_tasks.add_task(_notify_alerts_task, ret.material_code)
    return ret
