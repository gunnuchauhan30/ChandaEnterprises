"""
Background scheduled jobs. Currently just the daily 12:00 PM inventory
summary email to admins. Uses APScheduler's BackgroundScheduler, started
once from app/main.py on process startup and shut down on process exit.
"""
import logging
from datetime import date
from sqlalchemy import text

from app.db.session import SessionLocal
from app.core.config import settings
from app.services.email_service import send_inventory_summary_email

logger = logging.getLogger("chanda.scheduler")


def _fmt_currency(value) -> str:
    try:
        return f"Rs. {float(value):,.2f}"
    except (TypeError, ValueError):
        return "Rs. 0.00"


def build_inventory_summary(db) -> dict:
    total_stock_value = db.execute(text("SELECT COALESCE(SUM(current_qty*unit_cost),0) FROM materials")).scalar()
    total_materials = db.execute(text("SELECT COUNT(*) FROM materials")).scalar()
    low_stock_count = db.execute(text("SELECT COUNT(*) FROM materials WHERE low_stock_alert_open = TRUE")).scalar()
    high_stock_count = db.execute(text("SELECT COUNT(*) FROM materials WHERE high_stock_alert_open = TRUE")).scalar()

    today = date.today()
    todays_purchase_count = db.execute(
        text("SELECT COUNT(*) FROM purchases WHERE created_at::date = :d"), {"d": today}
    ).scalar()
    todays_issue_count = db.execute(
        text("SELECT COUNT(*) FROM issues WHERE issue_date = :d"), {"d": today}
    ).scalar()
    pending_requests = db.execute(text("SELECT COUNT(*) FROM employee_requests WHERE status = 'pending'")).scalar()
    pending_qc = db.execute(text("SELECT COUNT(*) FROM purchases WHERE qc_status = 'pending'")).scalar()
    pending_reconciliations = db.execute(
        text("SELECT COUNT(*) FROM stock_reconciliations WHERE status = 'pending'")
    ).scalar()
    critical_spares_low = db.execute(text("""
        SELECT COUNT(*) FROM critical_spares cs
        JOIN materials m ON m.material_code = cs.material_code
        WHERE m.current_qty <= cs.threshold_qty
    """)).scalar()

    return {
        "report_date": today.strftime("%d %b %Y"),
        "total_stock_value": _fmt_currency(total_stock_value),
        "total_materials": total_materials or 0,
        "low_stock_count": low_stock_count or 0,
        "high_stock_count": high_stock_count or 0,
        "todays_purchase_count": todays_purchase_count or 0,
        "todays_issue_count": todays_issue_count or 0,
        "pending_requests": pending_requests or 0,
        "pending_qc": pending_qc or 0,
        "pending_reconciliations": pending_reconciliations or 0,
        "critical_spares_low": critical_spares_low or 0,
    }


def send_daily_inventory_summary():
    """Runs in its own DB session -- called by the scheduler, not a request."""
    db = SessionLocal()
    try:
        summary = build_inventory_summary(db)
        if not settings.EMAIL_ENABLED:
            logger.info("EMAIL_ENABLED=False, skipping daily inventory summary. Summary: %s", summary)
            return
        if not settings.ADMIN_ALERT_EMAILS:
            logger.warning("Daily inventory summary due, but ADMIN_ALERT_EMAILS is empty -- nothing to send.")
            return
        send_inventory_summary_email(summary)
        logger.info("Daily inventory summary sent to %s", settings.ADMIN_ALERT_EMAILS)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send daily inventory summary")
    finally:
        db.close()


def start_scheduler():
    """Starts the APScheduler background scheduler with the 12:00 PM daily job.
    Returns the scheduler instance so main.py can shut it down cleanly."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone=settings.SCHEDULER_TIMEZONE)
    scheduler.add_job(
        send_daily_inventory_summary,
        trigger=CronTrigger(hour=12, minute=0),
        id="daily_inventory_summary",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("Scheduler started: daily inventory summary email will send at 12:00 PM (%s)",
                settings.SCHEDULER_TIMEZONE)
    return scheduler
