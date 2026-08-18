from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import require_roles
from app.models import ActivityLog, LoginLog, User

router = APIRouter(prefix="/history", tags=["Activity History"])


@router.get("/activity")
def list_activity(
    module: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """
    Point 4: 'Who did what, all day, in the system' -- everything here was
    already being written by log_activity() on every create/update/approve
    action; this just makes it visible via a dedicated Admin page.
    """
    q = db.query(ActivityLog)
    if module:
        q = q.filter(ActivityLog.module == module)
    if user_id:
        q = q.filter(ActivityLog.user_id == user_id)
    if date_from:
        q = q.filter(ActivityLog.created_at >= date_from)
    if date_to:
        q = q.filter(ActivityLog.created_at <= date_to)
    total = q.count()
    rows = q.order_by(ActivityLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    user_ids = {r.user_id for r in rows if r.user_id}
    users = {u.id: (u.full_name or u.username) for u in db.query(User).filter(User.id.in_(user_ids)).all()} \
        if user_ids else {}

    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "user": users.get(r.user_id, "System"),
                "action": r.action,
                "module": r.module,
                "ip_address": r.ip_address,
                "created_at": r.created_at,
            }
            for r in rows
        ],
    }


@router.get("/logins")
def list_logins(
    success: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    """Admin-only: who logged in (and who tried and failed), all day."""
    q = db.query(LoginLog)
    if success is not None:
        q = q.filter(LoginLog.success == success)
    total = q.count()
    rows = q.order_by(LoginLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "username_attempted": r.username_attempted,
                "success": r.success,
                "ip_address": r.ip_address,
                "created_at": r.created_at,
            }
            for r in rows
        ],
    }
