"""
Generates human-readable, sequential reference numbers.
issues.issue_no is generated INSIDE the DB trigger (fn_trg_request_approved)
when an employee request is auto-converted to an issue -- so it's not
handled here. Everything else (GRN, request, return, and direct route-card
issues) is generated at the app layer before insert.

These use real Postgres sequences (see migration_atomic_numbering.sql) so
concurrent requests -- e.g. a user double-clicking "Try Fulfill" on the
Backorders page, or several backorder rows settling in the same request --
can never be handed the same number. The previous COUNT(*)-based approach
was not safe under concurrency and could raise a duplicate-key error.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text


def _next_seq(db: Session, sequence_name: str, prefix: str) -> str:
    seq = db.execute(text(f"SELECT nextval('{sequence_name}')")).scalar()
    return f"{prefix}-{seq:06d}"


def next_grn_no(db: Session) -> str:
    return _next_seq(db, "purchases_grn_no_seq", "GRN")


def next_request_no(db: Session) -> str:
    return _next_seq(db, "employee_requests_request_no_seq", "REQ")


def next_issue_no(db: Session) -> str:
    """Only used for direct store-issue (route card), not for the
    auto-generated employee-request -> issue path."""
    return _next_seq(db, "issues_issue_no_seq", "ISS")


def next_return_no(db: Session) -> str:
    return _next_seq(db, "returns_return_no_seq", "RET")


def next_lot_no(db: Session) -> str:
    """Point 5: Lot No. for a Purchase/GRN batch is auto-generated as a
    series (LOT-000001, LOT-000002, ...) instead of being typed by hand.
    The same value then flows straight through to Issues (issues.lot_no is
    copied from the source batch) and shows up on the printed Route Card,
    so it's consistent end-to-end from GRN to shop floor."""
    return _next_seq(db, "purchases_batch_no_seq", "LOT")
