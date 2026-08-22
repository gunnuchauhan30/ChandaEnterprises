"""
Generates human-readable, sequential reference numbers.
issues.issue_no is generated INSIDE the DB trigger (fn_trg_request_approved)
when an employee request is auto-converted to an issue -- so it's not
handled here. Everything else (GRN, request, return, and direct route-card
issues) is generated at the app layer before insert.
"""
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import text


def _next_seq(db: Session, table: str, column: str, prefix: str) -> str:
    like_pattern = f"{prefix}-%"
    result = db.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE {column} LIKE :p"),
        {"p": like_pattern},
    ).scalar()
    seq = (result or 0) + 1
    return f"{prefix}-{seq:06d}"


def next_grn_no(db: Session) -> str:
    return _next_seq(db, "purchases", "grn_no", "GRN")


def next_request_no(db: Session) -> str:
    return _next_seq(db, "employee_requests", "request_no", "REQ")


def next_issue_no(db: Session) -> str:
    """Only used for direct store-issue (route card), not for the
    auto-generated employee-request -> issue path."""
    return _next_seq(db, "issues", "issue_no", "ISS")


def next_return_no(db: Session) -> str:
    return _next_seq(db, "returns", "return_no", "RET")


def next_lot_no(db: Session) -> str:
    """Point 5: Lot No. for a Purchase/GRN batch is auto-generated as a
    series (LOT-000001, LOT-000002, ...) instead of being typed by hand.
    The same value then flows straight through to Issues (issues.lot_no is
    copied from the source batch) and shows up on the printed Route Card,
    so it's consistent end-to-end from GRN to shop floor."""
    return _next_seq(db, "purchases", "batch_no", "LOT")
