import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models import User
from app.services.excel_service import export_rows_to_excel
from app.services.audit import log_download

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_QUERIES = {
    "purchase": """
        SELECT p.grn_no, p.material_code, m.material_name, s.supplier_name, p.qty, p.unit_cost,
               p.qc_status, p.invoice_no, p.invoice_date, p.created_at
        FROM purchases p
        JOIN materials m ON m.material_code = p.material_code
        LEFT JOIN suppliers s ON s.id = p.supplier_id
        WHERE (:date_from IS NULL OR p.created_at::date >= :date_from)
          AND (:date_to IS NULL OR p.created_at::date <= :date_to)
        ORDER BY p.created_at DESC
    """,
    "issue": """
        SELECT i.issue_no, i.material_code, m.material_name, i.department, i.job_card_no,
               i.production_order_no, i.issue_qty, i.consumed_qty, i.completion_status, i.issue_date
        FROM issues i
        JOIN materials m ON m.material_code = i.material_code
        WHERE (:date_from IS NULL OR i.issue_date >= :date_from)
          AND (:date_to IS NULL OR i.issue_date <= :date_to)
        ORDER BY i.issue_date DESC
    """,
    "supplier": """
        SELECT s.supplier_name, s.gst_no, s.phone, s.email, s.rating,
               COUNT(p.id) AS total_grns, COALESCE(SUM(p.qty),0) AS total_qty_supplied
        FROM suppliers s
        LEFT JOIN purchases p ON p.supplier_id = s.id
          AND (:date_from IS NULL OR p.created_at::date >= :date_from)
          AND (:date_to IS NULL OR p.created_at::date <= :date_to)
        GROUP BY s.id ORDER BY total_qty_supplied DESC
    """,
    "consumption": """
        SELECT i.material_code, m.material_name, COALESCE(SUM(i.issue_qty),0) AS total_consumed
        FROM issues i JOIN materials m ON m.material_code = i.material_code
        WHERE (:date_from IS NULL OR i.issue_date >= :date_from)
          AND (:date_to IS NULL OR i.issue_date <= :date_to)
        GROUP BY i.material_code, m.material_name ORDER BY total_consumed DESC
    """,
    "department": """
        SELECT COALESCE(i.department,'Unassigned') AS department,
               COUNT(*) AS issue_count, COALESCE(SUM(i.issue_qty),0) AS total_qty
        FROM issues i
        WHERE (:date_from IS NULL OR i.issue_date >= :date_from)
          AND (:date_to IS NULL OR i.issue_date <= :date_to)
        GROUP BY 1 ORDER BY total_qty DESC
    """,
    "stock": """
        SELECT material_code, material_name, category, material_type, uom,
               current_qty, reserved_qty, (current_qty - reserved_qty) AS available_qty,
               unit_cost, (current_qty * unit_cost) AS stock_value, warehouse, rack, bin
        FROM materials ORDER BY material_code
    """,
}


def _run_report(db: Session, report_type: str, date_from: Optional[date], date_to: Optional[date]):
    if report_type not in REPORT_QUERIES:
        raise HTTPException(400, f"Unknown report_type. Valid: {list(REPORT_QUERIES)}")
    rows = db.execute(text(REPORT_QUERIES[report_type]), {"date_from": date_from, "date_to": date_to}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{report_type}")
def get_report_json(
    report_type: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """report_type: purchase | issue | supplier | consumption | department | stock"""
    return _run_report(db, report_type, date_from, date_to)


@router.get("/{report_type}/export/excel")
def export_report_excel(
    report_type: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = _run_report(db, report_type, date_from, date_to)
    columns = list(rows[0].keys()) if rows else []
    buf = export_rows_to_excel(rows, columns, report_type.title())
    log_download(db, current_user.id, f"{report_type}_report.xlsx", report_type, "xlsx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={report_type}_report.xlsx"},
    )


@router.get("/{report_type}/export/csv")
def export_report_csv(
    report_type: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = _run_report(db, report_type, date_from, date_to)
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    log_download(db, current_user.id, f"{report_type}_report.csv", report_type, "csv")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={report_type}_report.csv"},
    )
