from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.misc import DashboardOut, PendingApprovalsOut, PendingApprovalItem

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    today = date.today()

    total_stock_qty = db.execute(text("SELECT COALESCE(SUM(current_qty),0) FROM materials")).scalar()
    total_stock_value = db.execute(text("SELECT COALESCE(SUM(current_qty*unit_cost),0) FROM materials")).scalar()

    todays_purchase = db.execute(
        text("SELECT COUNT(*), COALESCE(SUM(qty),0) FROM purchases WHERE created_at::date = :d"),
        {"d": today},
    ).first()

    todays_issue = db.execute(
        text("SELECT COUNT(*), COALESCE(SUM(issue_qty),0) FROM issues WHERE issue_date = :d"),
        {"d": today},
    ).first()

    low_stock_count = db.execute(text("SELECT COUNT(*) FROM materials WHERE low_stock_alert_open = TRUE")).scalar()
    high_stock_count = db.execute(text("SELECT COUNT(*) FROM materials WHERE high_stock_alert_open = TRUE")).scalar()
    # Point 3: critical spares currently at/below their configured threshold qty.
    critical_spares_count = db.execute(text("""
        SELECT COUNT(*) FROM critical_spares cs
        JOIN materials m ON m.material_code = cs.material_code
        WHERE m.current_qty <= cs.threshold_qty
    """)).scalar()
    pending_requests = db.execute(text("SELECT COUNT(*) FROM employee_requests WHERE status = 'pending'")).scalar()
    pending_qc = db.execute(text("SELECT COUNT(*) FROM purchases WHERE qc_status = 'pending'")).scalar()

    monthly_consumption = db.execute(text("""
        SELECT to_char(issue_date, 'YYYY-MM') AS month, COALESCE(SUM(issue_qty),0) AS total_qty
        FROM issues WHERE issue_date >= (CURRENT_DATE - INTERVAL '6 months')
        GROUP BY 1 ORDER BY 1
    """)).mappings().all()

    purchase_trend = db.execute(text("""
        SELECT created_at::date AS day, COALESCE(SUM(qty),0) AS total_qty
        FROM purchases WHERE created_at >= (CURRENT_DATE - INTERVAL '30 days')
        GROUP BY 1 ORDER BY 1
    """)).mappings().all()

    issue_trend = db.execute(text("""
        SELECT issue_date AS day, COALESCE(SUM(issue_qty),0) AS total_qty
        FROM issues WHERE issue_date >= (CURRENT_DATE - INTERVAL '30 days')
        GROUP BY 1 ORDER BY 1
    """)).mappings().all()

    department_consumption = db.execute(text("""
        SELECT COALESCE(department,'Unassigned') AS department, COALESCE(SUM(issue_qty),0) AS total_qty
        FROM issues WHERE issue_date >= (CURRENT_DATE - INTERVAL '30 days')
        GROUP BY 1 ORDER BY 2 DESC
    """)).mappings().all()

    return DashboardOut(
        total_stock_qty=total_stock_qty,
        total_stock_value=total_stock_value,
        todays_purchase_count=todays_purchase[0] or 0,
        todays_purchase_qty=todays_purchase[1] or 0,
        todays_issue_count=todays_issue[0] or 0,
        todays_issue_qty=todays_issue[1] or 0,
        low_stock_count=low_stock_count or 0,
        high_stock_count=high_stock_count or 0,
        critical_spares_count=critical_spares_count or 0,
        pending_employee_requests=pending_requests or 0,
        pending_qc=pending_qc or 0,
        unread_notifications=0,  # filled per-user on the frontend via /notifications/unread-count
        monthly_consumption=[dict(r) for r in monthly_consumption],
        purchase_trend=[dict(r) for r in purchase_trend],
        issue_trend=[dict(r) for r in issue_trend],
        department_consumption=[dict(r) for r in department_consumption],
    )


@router.get("/pending-approvals", response_model=PendingApprovalsOut)
def pending_approvals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Powers the 'Pending Approvals' dashboard card. Shows ONLY what the
    logged-in user's own role can act on -- Operation sees pending
    requests, Accounts sees pending GRNs + Issues, Quality sees pending
    QC, Store sees Operation-approved requests still waiting to be issued.
    Admin sees everything, all four kinds combined.
    """
    role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
    items: list[PendingApprovalItem] = []

    def add(kind, rows, label_fn, detail_fn):
        for r in rows:
            items.append(PendingApprovalItem(
                kind=kind, ref_id=r["id"], label=label_fn(r), detail=detail_fn(r), created_at=r["created_at"],
            ))

    if role in ("operation", "admin"):
        rows = db.execute(text("""
            SELECT er.id, er.request_no, er.material_code, er.requested_qty, er.raised_by_name,
                   er.department, er.created_at
            FROM employee_requests er
            WHERE er.status = 'pending'
            ORDER BY er.created_at ASC
        """)).mappings().all()
        add("request_operation", rows,
            lambda r: f"Request {r['request_no']}",
            lambda r: f"{r['material_code']} · qty {r['requested_qty']} · raised by {r['raised_by_name']} ({r['department'] or '-'})")

    if role in ("accounts", "admin"):
        grn_rows = db.execute(text("""
            SELECT p.id, p.grn_no, p.material_code, p.qty, p.created_at
            FROM purchases p
            WHERE p.qc_status = 'passed' AND p.accounts_approval_status = 'pending'
            ORDER BY p.created_at ASC
        """)).mappings().all()
        add("grn_accounts", grn_rows,
            lambda r: f"GRN {r['grn_no']}",
            lambda r: f"{r['material_code']} · qty {r['qty']} · QC passed, awaiting Accounts")

        issue_rows = db.execute(text("""
            SELECT i.id, i.issue_no, i.material_code, i.issue_qty, i.created_at
            FROM issues i
            WHERE i.accounts_approval_status = 'pending'
            ORDER BY i.created_at ASC
        """)).mappings().all()
        add("issue_accounts", issue_rows,
            lambda r: f"Issue {r['issue_no']}",
            lambda r: f"{r['material_code']} · qty {r['issue_qty']} · awaiting Accounts")

    if role in ("quality", "admin"):
        rows = db.execute(text("""
            SELECT p.id, p.grn_no, p.material_code, p.qty, p.created_at
            FROM purchases p
            WHERE p.qc_status = 'pending'
            ORDER BY p.created_at ASC
        """)).mappings().all()
        add("grn_qc", rows,
            lambda r: f"GRN {r['grn_no']}",
            lambda r: f"{r['material_code']} · qty {r['qty']} · awaiting QC")

    if role in ("store_manager", "admin"):
        rows = db.execute(text("""
            SELECT er.id, er.request_no, er.material_code,
                   (er.requested_qty - COALESCE(er.fulfilled_qty,0)) AS pending_qty, er.created_at
            FROM employee_requests er
            WHERE er.status IN ('approved','partial')
              AND (er.requested_qty - COALESCE(er.fulfilled_qty,0)) > 0
            ORDER BY er.created_at ASC
        """)).mappings().all()
        add("request_store", rows,
            lambda r: f"Request {r['request_no']}",
            lambda r: f"{r['material_code']} · pending {r['pending_qty']} · Operation-approved, ready to issue")

    items.sort(key=lambda x: x.created_at)
    return PendingApprovalsOut(role=role, items=items)
