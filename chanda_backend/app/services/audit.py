import json
from typing import Optional, Any
from sqlalchemy.orm import Session
from app.models import AuditLog, ActivityLog, LoginLog, ErrorLog, DownloadLog


def log_activity(db: Session, user_id: Optional[int], action: str, module: str, ip_address: Optional[str] = None):
    db.add(ActivityLog(user_id=user_id, action=action, module=module, ip_address=ip_address))
    db.commit()


def log_audit(
    db: Session,
    table_name: str,
    record_id: Any,
    action: str,
    old_value: Optional[dict],
    new_value: Optional[dict],
    changed_by: Optional[int],
    ip_address: Optional[str] = None,
):
    db.add(AuditLog(
        table_name=table_name,
        record_id=str(record_id),
        action=action,
        old_value=json.dumps(old_value, default=str) if old_value else None,
        new_value=json.dumps(new_value, default=str) if new_value else None,
        changed_by=changed_by,
        ip_address=ip_address,
    ))
    db.commit()


def log_login(db: Session, user_id: Optional[int], username_attempted: str, success: bool,
              ip_address: Optional[str] = None, user_agent: Optional[str] = None):
    db.add(LoginLog(
        user_id=user_id, username_attempted=username_attempted, success=success,
        ip_address=ip_address, user_agent=user_agent,
    ))
    db.commit()


def log_error(db: Session, path: str, method: str, status_code: int, error_message: str,
              traceback_str: Optional[str] = None, user_id: Optional[int] = None):
    db.add(ErrorLog(
        path=path, method=method, status_code=status_code, error_message=error_message,
        traceback=traceback_str, user_id=user_id,
    ))
    db.commit()


def log_download(db: Session, user_id: Optional[int], file_name: str, report_type: str,
                  fmt: str, ip_address: Optional[str] = None):
    db.add(DownloadLog(user_id=user_id, file_name=file_name, report_type=report_type,
                        format=fmt, ip_address=ip_address))
    db.commit()
