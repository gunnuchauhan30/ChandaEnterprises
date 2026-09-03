from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.deps import get_current_user, require_roles
from app.models import Alert, Notification, Material, User
from app.schemas.misc import AlertOut, NotificationOut

router = APIRouter(tags=["Alerts & Notifications"])


# ================= Alerts (Low/High stock -- rows written by the DB trigger fn_check_stock_thresholds) =================

@router.get("/alerts", response_model=List[AlertOut])
def list_alerts(
    alert_type: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Alert)
    if alert_type:
        q = q.filter(Alert.alert_type == alert_type)
    if is_resolved is not None:
        q = q.filter(Alert.is_resolved == is_resolved)
    alerts = q.order_by(Alert.triggered_at.desc()).all()

    # Point 5: attach the material's name alongside its code so the Alerts
    # page doesn't force the user to go look the code up elsewhere.
    codes = {a.material_code for a in alerts}
    names = {}
    if codes:
        rows = db.query(Material.material_code, Material.material_name).filter(Material.material_code.in_(codes)).all()
        names = {code: name for code, name in rows}

    result = []
    for a in alerts:
        out = AlertOut.model_validate(a)
        out.material_name = names.get(a.material_code)
        result.append(out)
    return result


@router.get("/alerts/low-stock")
def low_stock(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(text("SELECT * FROM vw_low_stock_materials")).mappings().all()
    return [dict(r) for r in rows]


@router.get("/alerts/high-stock")
def high_stock(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(text("SELECT * FROM vw_high_stock_materials")).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("store_manager", "purchase")),
):
    alert = db.query(Alert).get(alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    alert.is_resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/alerts/{material_code}/confirm-high-stock-purchase")
def confirm_high_stock_purchase(
    material_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("purchase", "admin", "store_manager")),
):
    """Explicit confirmation step required by the spec before further purchase
    of a material that is already above its high-stock threshold."""
    open_alert = (
        db.query(Alert)
        .filter(Alert.material_code == material_code, Alert.alert_type == "high_stock", Alert.is_resolved == False)  # noqa: E712
        .first()
    )
    if not open_alert:
        return {"message": "No open high-stock alert for this material -- purchase can proceed normally."}
    return {
        "message": "High stock confirmed by purchase department. Proceeding with purchase is allowed for this GRN.",
        "alert_id": open_alert.id,
        "confirmed_by": current_user.username,
    }


# ================= Notification Center =================

@router.get("/notifications", response_model=List[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Notification).filter(
        (Notification.user_id == current_user.id) | (Notification.role == current_user.role)
    )
    if unread_only:
        q = q.filter(Notification.is_read == False)  # noqa: E712
    return q.order_by(Notification.created_at.desc()).limit(100).all()


@router.get("/notifications/unread-count")
def unread_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    count = db.query(Notification).filter(
        ((Notification.user_id == current_user.id) | (Notification.role == current_user.role)),
        Notification.is_read == False,  # noqa: E712
    ).count()
    return {"unread_count": count}


@router.patch("/notifications/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    n = db.query(Notification).get(notification_id)
    if not n:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return {"message": "marked as read"}


@router.patch("/notifications/read-all")
def mark_all_read(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(Notification).filter(
        (Notification.user_id == current_user.id) | (Notification.role == current_user.role),
        Notification.is_read == False,  # noqa: E712
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"message": "all marked as read"}
