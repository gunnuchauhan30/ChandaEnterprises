"""
Wires the DB-generated Alert rows (written by trg_check_stock_thresholds)
to actual outbound notifications: email + in-app Notification rows.

The DB trigger only *records* that a material crossed a threshold
(materials.low_stock_alert_open / high_stock_alert_open flip to True and a
row is inserted into `alerts`). Nothing in the original code path ever
looked at those rows again, so store managers / admins were never actually
notified. This module closes that gap.

Call `notify_new_alerts_for_material()` as a FastAPI BackgroundTask right
after any operation that can move stock across a threshold:
  - purchases.py  -> after QC status set to 'passed'
  - issues.py     -> after employee-request approval / direct issue create
  - inventory.py  -> after manual stock adjustments, if any

It is intentionally idempotent / cheap to over-call: it only acts on Alert
rows that are still unresolved AND don't yet have a Notification linked to
them (tracked via a simple "already notified" check on Notification.link).
"""
import logging
from sqlalchemy.orm import Session

from app.models import Alert, Material, Notification, UserRole
from app.services.email_service import send_low_stock_alert, send_high_stock_alert

logger = logging.getLogger("chanda.alerts")


def _already_notified(db: Session, alert: Alert) -> bool:
    link = f"/alerts/{alert.id}"
    return db.query(Notification).filter(Notification.link == link).first() is not None


def notify_new_alerts_for_material(db: Session, material_code: str) -> None:
    """
    Look at unresolved alerts for this material. For any that haven't been
    pushed out yet, send the appropriate email(s) and create in-app
    Notification rows for the relevant roles, then mark them as pushed.
    """
    material = db.query(Material).get(material_code)
    if not material:
        return

    open_alerts = (
        db.query(Alert)
        .filter(Alert.material_code == material_code, Alert.is_resolved == False)  # noqa: E712
        .all()
    )

    for alert in open_alerts:
        if _already_notified(db, alert):
            continue

        try:
            if alert.alert_type.value == "low_stock":
                send_low_stock_alert(
                    material.material_code, material.material_name,
                    alert.available_qty, alert.threshold_qty,
                )
                title = "Low Stock Alert"
                roles = [UserRole.store_manager, UserRole.admin]
            else:  # high_stock
                send_high_stock_alert(
                    material.material_code, material.material_name,
                    alert.available_qty, alert.threshold_qty,
                )
                title = "High Stock Alert"
                roles = [UserRole.purchase, UserRole.admin]
        except Exception:  # noqa: BLE001 -- never let an email failure break the request
            logger.exception("Failed to send alert email for %s (alert_id=%s)", material_code, alert.id)

        for role in roles:
            db.add(Notification(
                user_id=None,
                role=role,
                type="alert",
                title=title,
                message=alert.message or f"{material.material_name} ({material.material_code}) crossed threshold",
                link=f"/alerts/{alert.id}",
            ))

    db.commit()
