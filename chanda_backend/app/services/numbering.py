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
    """
    Next number in a PREFIX-000123 series.

    Uses MAX(numeric suffix), not COUNT(*). COUNT(*) looks right but breaks
    the moment any row in the table is ever deleted (a bad test record, a
    force-deleted user's history getting cleaned up, etc.): the count drops
    below the highest number actually used, so it hands out a number
    that's already taken and the insert fails with a UNIQUE-constraint
    violation. MAX-based generation always continues from the highest
    number that ever existed, regardless of gaps.
    """
    result = db.execute(
        text(
            f"SELECT COALESCE(MAX(CAST(SUBSTRING({column} FROM :suffix_pos) AS INTEGER)), 0) "
            f"FROM {table} WHERE {column} LIKE :p"
        ),
        {"p": f"{prefix}-%", "suffix_pos": len(prefix) + 2},
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


def next_job_card_no(db: Session) -> str:
    """
    Plain sequential job card number (1, 2, 3, ...) -- NOT the PREFIX-000123
    style used elsewhere. Job Card No. is a free-text field (someone can
    also type a real job card number like 'TEST-001'), so this only looks
    at rows that are already plain integers and continues after the
    highest one, ignoring text ones. Used whenever an issue is created
    without an explicit job card number, so the Route Card list's Sr. No.
    and the actual Job Card No. stay in step with each other.
    """
    result = db.execute(
        text(
            "SELECT COALESCE(MAX(CAST(job_card_no AS INTEGER)), 0) FROM issues "
            "WHERE job_card_no ~ '^[0-9]+$'"
        )
    ).scalar()
    return str((result or 0) + 1)
