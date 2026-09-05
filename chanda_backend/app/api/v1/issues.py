from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import DBAPIError
from typing import Optional, List

from app.db.session import get_db, SessionLocal
from app.core.deps import get_current_user, require_roles
from app.models import EmployeeRequest, Issue, IssueBatchAllocation, Return, Material, User, StockBatch, Purchase, Supplier
from app.schemas.issues import (
    EmployeeRequestIn, EmployeeRequestOut, EmployeeRequestDecision,
    IssueFromRequestIn, IssueAccountsApproval, IssueOut, IssueConsumptionUpdate,
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
    Creates one Issue row for `fulfill_qty` against a request, with
    accounts_approval_status='pending'. This does NOT move any stock and
    does NOT touch req.fulfilled_qty -- that only happens once Accounts
    approves this specific issue (see issue_accounts_approval below). This
    keeps the backorder auto-settlement path consistent with the manual
    Store-creates-issue path: an Issue existing is never, by itself,
    evidence that stock has actually moved.
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
        accounts_approval_status="pending",
    )
    db.add(issue)
    db.flush()
    return issue


@router.patch("/employee-requests/{request_id}/decision", response_model=EmployeeRequestOut)
def decide_request(
    request_id: int,
    payload: EmployeeRequestDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("operation", "admin")),
):
    """
    Approve/reject a request. This is the OPERATION sign-off only.

    IMPORTANT (changed): approving here no longer creates an Issue or moves
    any stock. It only flips status to 'approved'. Store then creates the
    actual Issue from this approved request as a separate step, and stock
    only moves once Accounts approves that Issue -- see issues endpoints
    below. This keeps three distinct people/steps in the loop: Operation
    approves the request itself, Store decides how/when to issue it,
    Accounts is the final gate before stock actually changes.
    """
    req = db.query(EmployeeRequest).get(request_id)
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status not in ("pending", "partial"):
        raise HTTPException(400, f"Request already {req.status}")

    if payload.action == "approve":
        req.status = "approved"
        req.approved_by = current_user.id
        req.approved_at = func.now()

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
        f"{payload.action.title()}d request {req.request_no}",
        "employee_requests",
    )

    return req


@router.get("/employee-requests/backorders", response_model=List[EmployeeRequestOut])
def list_backorders(
    material_code: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Point 12: the FIFO backorder queue -- every Operation-approved request
    that still has pending_qty > 0, oldest first. This is what the
    dedicated Backorders page reads from. Only 'approved'/'partial'
    requests qualify -- a request Operation hasn't approved yet is not a
    backorder, it's just an unapproved request.
    """
    q = db.query(EmployeeRequest).filter(EmployeeRequest.status.in_(["approved", "partial"]))
    if material_code:
        q = q.filter(EmployeeRequest.material_code == material_code)
    rows = q.order_by(EmployeeRequest.created_at.asc()).all()
    return [r for r in rows if (r.requested_qty - (r.fulfilled_qty or 0)) > 0]


@router.post("/employee-requests/backorders/process/{material_code}")
def process_backorders(
    material_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "admin")),
):
    """
    Point 12 (FIFO settlement): call this whenever new stock has just come in
    for a material (e.g. after a GRN's Accounts approval -- see
    purchases.py). Walks every open backorder for that material, oldest
    Operation-approved request first, and auto-creates a pending Issue for
    each one to the extent stock is nominally available right now.

    IMPORTANT: this only creates Issue rows (accounts_approval_status=
    'pending') -- it is the automated equivalent of Store's "create issue
    from approved request" step, nothing more. It does NOT move stock and
    does NOT touch req.fulfilled_qty/status -- Accounts still has to
    approve each of these issues individually before stock actually
    changes (see issue_accounts_approval below). Because of that, the
    "available stock" this checks against does not account for OTHER
    pending-but-not-yet-accounts-approved issues that may already be
    queued against the same material -- Accounts approval itself is the
    real backstop against overselling (it will reject with 400 if stock
    genuinely runs short by the time it's actually deducted).
    """
    material = db.query(Material).filter(Material.material_code == material_code).first()
    if not material:
        raise HTTPException(404, "Material not found")

    pending_reqs = (
        db.query(EmployeeRequest)
        .filter(
            EmployeeRequest.material_code == material_code,
            EmployeeRequest.status.in_(["approved", "partial"]),
        )
        .order_by(EmployeeRequest.created_at.asc())  # FIFO: oldest first
        .all()
    )

    created, skipped = [], []
    remaining_stock = material.available_qty
    for req in pending_reqs:
        already_committed = (req.fulfilled_qty or 0) + sum(
            i.issue_qty for i in
            db.query(Issue).filter(Issue.employee_request_id == req.id, Issue.accounts_approval_status == "pending").all()
        )
        remaining_needed = req.requested_qty - already_committed
        if remaining_needed <= 0:
            continue
        if remaining_stock <= 0:
            skipped.append(req.request_no)
            continue

        fulfill_qty = min(remaining_stock, remaining_needed)
        issue = _issue_against_request(db, req, fulfill_qty, current_user.id)
        remaining_stock -= fulfill_qty
        created.append({"request_no": req.request_no, "issue_no": issue.issue_no, "issue_qty": float(fulfill_qty)})

    db.commit()
    log_activity(
        db, current_user.id,
        f"Auto-created {len(created)} pending issue(s) from backorders for {material_code} (awaiting Accounts approval)",
        "employee_requests",
    )
    return {"material_code": material_code, "issues_created": created, "still_pending": skipped}


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

    Reads from issue_batch_allocations, written by the DB trigger at the
    moment Accounts approved this issue (fn_trg_issue_stock) -- so this
    now shows the FULL FIFO split (every batch actually drawn from), not
    just the first one. Issues from before this table existed (or issues
    still awaiting Accounts approval) fall back to the single lot_no view,
    or an empty allocation if nothing has been drawn yet.
    """
    issue = db.query(Issue).get(issue_id)
    if not issue:
        raise HTTPException(404, "Issue not found")

    allocations = (
        db.query(IssueBatchAllocation, StockBatch, Supplier.supplier_name)
        .outerjoin(StockBatch, IssueBatchAllocation.stock_batch_id == StockBatch.id)
        .outerjoin(Purchase, StockBatch.purchase_id == Purchase.id)
        .outerjoin(Supplier, Purchase.supplier_id == Supplier.id)
        .filter(IssueBatchAllocation.issue_id == issue.id)
        .order_by(IssueBatchAllocation.id.asc())
        .all()
    )

    if allocations:
        rows = []
        for alloc, batch, supplier_name in allocations:
            rows.append({
                "supplier_name": supplier_name or "Direct / Unassigned",
                "batch_no": alloc.batch_no,
                "received_date": batch.received_date.isoformat() if batch and batch.received_date else None,
                "available": float(batch.remaining_qty) if batch else None,
                "issue_qty": float(alloc.qty_taken),
                "remaining_after": float(batch.remaining_qty) if batch else None,
            })
        return {"issue_id": issue.id, "issue_qty": float(issue.issue_qty), "allocation": rows}

    if issue.accounts_approval_status != "approved":
        return {
            "issue_id": issue.id, "issue_qty": float(issue.issue_qty), "allocation": [],
            "note": "Stock has not moved yet -- this issue is still awaiting Accounts approval.",
        }

    # Fallback for issues approved before this table existed: old single
    # lot_no view (first/oldest batch only, not necessarily the full split).
    if issue.lot_no:
        batch, supplier_name = (
            db.query(StockBatch, Supplier.supplier_name)
            .outerjoin(Purchase, StockBatch.purchase_id == Purchase.id)
            .outerjoin(Supplier, Purchase.supplier_id == Supplier.id)
            .filter(StockBatch.material_code == issue.material_code, StockBatch.batch_no == issue.lot_no)
            .first()
        ) or (None, None)

        if batch:
            available_now = float(batch.remaining_qty)
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

    # Last resort for issues that predate ALL of this tracking (no
    # allocation rows, no lot_no either -- e.g. old requests-based auto
    # issues): simulate FIFO against TODAY's stock_batches, same logic as
    # the New Issue preview (fifo_check). This is clearly an ESTIMATE, not
    # the real historical record -- the actual batches on hand have moved
    # on since this issue happened. is_estimate=True tells the frontend to
    # label it as such.
    batches = (
        db.query(StockBatch, Supplier.supplier_name)
        .outerjoin(Purchase, StockBatch.purchase_id == Purchase.id)
        .outerjoin(Supplier, Purchase.supplier_id == Supplier.id)
        .filter(StockBatch.material_code == issue.material_code, StockBatch.remaining_qty > 0)
        .order_by(StockBatch.received_date.asc(), StockBatch.id.asc())
        .all()
    )
    remaining_needed = float(issue.issue_qty)
    estimated_allocation = []
    for batch, supplier_name in batches:
        if remaining_needed <= 0:
            break
        available = float(batch.remaining_qty)
        take = min(available, remaining_needed)
        estimated_allocation.append({
            "supplier_name": supplier_name or "Direct / Unassigned",
            "batch_no": batch.batch_no,
            "received_date": batch.received_date.isoformat() if batch.received_date else None,
            "available": available,
            "issue_qty": take,
            "remaining_after": available - take,
        })
        remaining_needed -= take

    return {
        "issue_id": issue.id,
        "issue_qty": float(issue.issue_qty),
        "allocation": estimated_allocation,
        "is_estimate": True,
        "note": "No historical batch record exists for this issue (it predates per-batch tracking). This is an ESTIMATE based on today's stock, not the actual batches used at the time.",
    }


@router.post("/issues/from-request/{request_id}", response_model=IssueOut, status_code=201)
def create_issue_from_request(
    request_id: int,
    payload: IssueFromRequestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "admin")),
):
    """
    Store creates an issue against a request Operation has already
    approved. This does NOT move stock -- it only records that Store is
    committing to issue this quantity. Stock only actually moves once
    Accounts approves this issue (PATCH /issues/{id}/accounts-approval).
    This replaces the old "New Issue" direct-issue button -- every issue
    now has to trace back to an approved request.
    """
    req = db.query(EmployeeRequest).get(request_id)
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status not in ("approved", "partial"):
        raise HTTPException(400, f"Request must be Operation-approved first (current status: {req.status})")

    already_committed = (req.fulfilled_qty or 0) + sum(
        i.issue_qty for i in
        db.query(Issue).filter(Issue.employee_request_id == req.id, Issue.accounts_approval_status == "pending").all()
    )
    remaining = req.requested_qty - already_committed
    if payload.issue_qty > remaining:
        raise HTTPException(400, f"issue_qty exceeds what's left on this request: {remaining} remaining")

    issue = Issue(
        issue_no=next_issue_no(db),
        material_code=req.material_code,
        employee_request_id=req.id,
        issue_qty=payload.issue_qty,
        job_card_no=payload.job_card_no or req.job_card_no,
        production_order_no=payload.production_order_no,
        part_number=payload.part_number or req.part_number,
        machine=payload.machine,
        operation=payload.operation,
        department=payload.department or req.department,
        shift=payload.shift,
        required_qty=payload.required_qty,
        remark=payload.remark,
        consumed_qty=0,
        completion_status="issued",
        issued_by=current_user.id,
        accounts_approval_status="pending",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    log_activity(db, current_user.id, f"Created issue {issue.issue_no} against request {req.request_no} (awaiting Accounts approval)", "issues")
    return issue


@router.patch("/issues/{issue_id}/accounts-approval", response_model=IssueOut)
def issue_accounts_approval(
    issue_id: int,
    payload: IssueAccountsApproval,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("accounts", "admin")),
):
    """
    Final sign-off on an issue. This is the ONLY step that actually moves
    stock -- the DB trigger (fn_trg_issue_stock) deducts current_qty,
    consumes FIFO stock_batches, and writes the full per-batch breakdown to
    issue_batch_allocations only when accounts_approval_status flips to
    'approved' here. Rejecting leaves stock untouched and the underlying
    request stays 'approved'/'partial' so Store can create a corrected
    issue against it if needed.
    """
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be 'approved' or 'rejected'")
    issue = db.query(Issue).get(issue_id)
    if not issue:
        raise HTTPException(404, "Issue not found")
    if issue.accounts_approval_status != "pending":
        raise HTTPException(400, f"This issue has already been {issue.accounts_approval_status} by Accounts")

    issue.accounts_approval_status = payload.status
    issue.accounts_approved_by = current_user.id
    issue.accounts_approved_at = datetime.utcnow()

    try:
        db.commit()
    except DBAPIError as e:
        db.rollback()
        # fn_post_stock_ledger raises a plain Postgres exception when stock
        # would go negative -- surface that as a clean 400 instead of a 500.
        raise HTTPException(400, f"Could not approve: insufficient stock right now for {issue.material_code}") from e

    db.refresh(issue)
    log_activity(db, current_user.id, f"Issue {issue.issue_no} accounts-{payload.status}", "issues")

    if payload.status == "approved":
        background_tasks.add_task(_notify_alerts_task, issue.material_code)
        if issue.employee_request_id:
            req = db.query(EmployeeRequest).get(issue.employee_request_id)
            if req:
                req.fulfilled_qty = (req.fulfilled_qty or 0) + issue.issue_qty
                req.status = "completed" if req.fulfilled_qty >= req.requested_qty else "partial"
                db.commit()

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
