"""
Email sender. Two backends:
  1. Resend HTTPS API (used automatically whenever RESEND_API_KEY is set) --
     this is the one to use on Railway, since Railway blocks outbound SMTP
     ports (25/587/465) on every plan, free or paid. An HTTPS POST to
     Resend is not SMTP and is never blocked.
  2. Raw SMTP (smtplib) -- kept only as a fallback for hosts that don't
     block SMTP (e.g. a real VPS), used when RESEND_API_KEY is empty.
Disabled entirely by default (settings.EMAIL_ENABLED=False) so the backend
runs fully without any email creds configured.
"""
import httpx
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

from app.core.config import settings

logger = logging.getLogger("chanda.email")

_ALERT_TEMPLATE = """
<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden">
  <div style="background:linear-gradient(135deg,#6a1b9a,#4a148c);padding:20px;text-align:center">
    <h2 style="color:#fff;margin:0">CHANDA ENTERPRISES</h2>
    <p style="color:#e1bee7;margin:4px 0 0">Store Management System</p>
  </div>
  <div style="padding:24px">
    <h3 style="color:{color};margin-top:0">{alert_title}</h3>
    <table style="width:100%;border-collapse:collapse">
      <tr><td style="padding:6px 0;color:#666">Material Name</td><td style="padding:6px 0;font-weight:bold">{material_name}</td></tr>
      <tr><td style="padding:6px 0;color:#666">Material Code</td><td style="padding:6px 0;font-weight:bold">{material_code}</td></tr>
      <tr><td style="padding:6px 0;color:#666">Current Quantity</td><td style="padding:6px 0;font-weight:bold">{current_qty}</td></tr>
      <tr><td style="padding:6px 0;color:#666">Threshold</td><td style="padding:6px 0;font-weight:bold">{threshold}</td></tr>
      <tr><td style="padding:6px 0;color:#666">Suggested Action</td><td style="padding:6px 0;font-weight:bold">{suggested_action}</td></tr>
    </table>
  </div>
  <div style="background:#f5f5f5;padding:12px;text-align:center;color:#999;font-size:12px">
    Automated notification from Chanda Enterprises Store Management System
  </div>
</div>
"""


def _send_via_resend(to_emails: List[str], subject: str, html_body: str, from_email: str):
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": f"{settings.SMTP_FROM_NAME} <{from_email}>",
            "to": to_emails,
            "subject": subject,
            "html": html_body,
        },
        timeout=15,
    )
    if resp.status_code >= 400:
        # Surface Resend's actual error (e.g. "domain not verified") instead of
        # failing silently -- this is exactly the kind of thing that was
        # invisible before and made debugging impossible.
        logger.error("Resend send failed (%s): %s", resp.status_code, resp.text)
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")
    logger.info("Email sent via Resend to %s: %s", to_emails, subject)


def _send_via_smtp(to_emails: List[str], subject: str, html_body: str, from_email: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{from_email}>"
    msg["To"] = ", ".join(to_emails)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(from_email, to_emails, msg.as_string())
    logger.info("Email sent via SMTP to %s: %s", to_emails, subject)


def _send(to_emails: List[str], subject: str, html_body: str):
    if not settings.EMAIL_ENABLED:
        logger.info("EMAIL_ENABLED=False, skipping send. Would have sent to %s: %s", to_emails, subject)
        return
    if not to_emails:
        return

    # Gmail (and most providers) reject or silently rewrite the envelope
    # sender if it doesn't match the authenticated SMTP_USER account, so if
    # SMTP_FROM_EMAIL was left at its default / a different address than the
    # logged-in Gmail account, use SMTP_USER instead -- otherwise sends fail
    # with something like "authenticated sender does not match".
    from_email = settings.SMTP_FROM_EMAIL if settings.RESEND_API_KEY else (settings.SMTP_USER or settings.SMTP_FROM_EMAIL)

    try:
        if settings.RESEND_API_KEY:
            _send_via_resend(to_emails, subject, html_body, from_email)
        else:
            _send_via_smtp(to_emails, subject, html_body, from_email)
    except Exception:
        # Log with full traceback so a Railway deploy log actually shows
        # WHY a send failed, instead of the failure vanishing silently.
        logger.exception("Email send failed (to=%s, subject=%s)", to_emails, subject)
        raise


def send_low_stock_alert(material_code: str, material_name: str, current_qty, threshold):
    body = _ALERT_TEMPLATE.format(
        color="#c62828", alert_title="⚠ LOW STOCK ALERT",
        material_name=material_name, material_code=material_code,
        current_qty=current_qty, threshold=threshold,
        suggested_action="Raise a purchase order immediately",
    )
    to = settings.STORE_MANAGER_ALERT_EMAILS + settings.ADMIN_ALERT_EMAILS
    _send(to, f"LOW STOCK ALERT: {material_name} ({material_code})", body)


def send_high_stock_alert(material_code: str, material_name: str, current_qty, threshold):
    body = _ALERT_TEMPLATE.format(
        color="#e65100", alert_title="⚠ HIGH STOCK ALERT",
        material_name=material_name, material_code=material_code,
        current_qty=current_qty, threshold=threshold,
        suggested_action="Confirmation required before any further purchase",
    )
    to = settings.PURCHASE_DEPT_ALERT_EMAILS + settings.ADMIN_ALERT_EMAILS
    _send(to, f"HIGH STOCK ALERT: {material_name} ({material_code})", body)


_SUMMARY_TEMPLATE = """
<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden">
  <div style="background:linear-gradient(135deg,#c0392b,#e67e22);padding:20px;text-align:center">
    <h2 style="color:#fff;margin:0">CHANDA ENTERPRISES</h2>
    <p style="color:#fde8d8;margin:4px 0 0">Daily Inventory Summary — {report_date}</p>
  </div>
  <div style="padding:24px">
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      <tr><td style="padding:8px 0;color:#666">Total Stock Value</td><td style="padding:8px 0;font-weight:bold;text-align:right">{total_stock_value}</td></tr>
      <tr><td style="padding:8px 0;color:#666">Total Materials Tracked</td><td style="padding:8px 0;font-weight:bold;text-align:right">{total_materials}</td></tr>
      <tr><td style="padding:8px 0;color:#c0392b">Low Stock Items</td><td style="padding:8px 0;font-weight:bold;text-align:right;color:#c0392b">{low_stock_count}</td></tr>
      <tr><td style="padding:8px 0;color:#e67e22">High Stock Items</td><td style="padding:8px 0;font-weight:bold;text-align:right;color:#e67e22">{high_stock_count}</td></tr>
      <tr><td style="padding:8px 0;color:#666">Today's Purchases (GRN)</td><td style="padding:8px 0;font-weight:bold;text-align:right">{todays_purchase_count}</td></tr>
      <tr><td style="padding:8px 0;color:#666">Today's Issues</td><td style="padding:8px 0;font-weight:bold;text-align:right">{todays_issue_count}</td></tr>
      <tr><td style="padding:8px 0;color:#666">Pending Employee Requests</td><td style="padding:8px 0;font-weight:bold;text-align:right">{pending_requests}</td></tr>
      <tr><td style="padding:8px 0;color:#666">Pending QC</td><td style="padding:8px 0;font-weight:bold;text-align:right">{pending_qc}</td></tr>
      <tr><td style="padding:8px 0;color:#8e44ad">Pending Stock Reconciliations</td><td style="padding:8px 0;font-weight:bold;text-align:right;color:#8e44ad">{pending_reconciliations}</td></tr>
      <tr><td style="padding:8px 0;color:#666">Critical Spares Below Threshold</td><td style="padding:8px 0;font-weight:bold;text-align:right">{critical_spares_low}</td></tr>
    </table>
    <p style="color:#999;font-size:12px">Automated daily summary, sent every day at 12:00 PM.</p>
  </div>
</div>
"""


def send_inventory_summary_email(summary: dict):
    body = _SUMMARY_TEMPLATE.format(**summary)
    to = settings.ADMIN_ALERT_EMAILS
    subject = f"Daily Inventory Summary — Chanda Enterprises — {summary.get('report_date', '')}"
    _send(to, subject, body)


def send_password_reset_email(to_email: str, reset_link: str):
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <h2 style="color:#4a148c">Password Reset - Chanda Enterprises</h2>
      <p>Click the link below to reset your password. This link expires in
      {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
      <p><a href="{reset_link}" style="background:#6a1b9a;color:#fff;padding:10px 20px;
      border-radius:6px;text-decoration:none">Reset Password</a></p>
      <p>If you did not request this, you can safely ignore this email.</p>
    </div>
    """
    _send([to_email], "Password Reset - Chanda Enterprises", body)
