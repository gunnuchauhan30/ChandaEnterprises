from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.misc import DashboardOut

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
