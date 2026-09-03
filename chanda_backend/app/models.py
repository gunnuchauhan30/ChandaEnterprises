"""
CHANDA ENTERPRISES — SQLAlchemy ORM models mirroring schema.sql exactly.
material_code is used as the natural primary key throughout, matching the
company's real Excel files (which have no other unique linking field).
"""
from datetime import datetime, date
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Numeric, Boolean, Date, DateTime,
    ForeignKey, Enum, CheckConstraint, UniqueConstraint, func
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserRole(str, PyEnum):
    admin = "admin"
    store_manager = "store_manager"
    purchase = "purchase"
    production = "production"
    management = "management"
    quality = "quality"  # QC pass/fail on GRNs only -- nothing else
    operation = "operation"  # approves employee material requests
    accounts = "accounts"    # final approval on GRN + Issues -- only step that moves stock


class MaterialType(str, PyEnum):
    PRODUCTION = "PRODUCTION"
    CONSUMABLE = "CONSUMABLE"


class QCStatus(str, PyEnum):
    pending = "pending"
    passed = "passed"
    failed = "failed"


class RequestStatus(str, PyEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    partial = "partial"    # point 12: some qty issued now, rest queued as FIFO backorder
    completed = "completed"


class ReturnType(str, PyEnum):
    unused = "unused"
    vendor_return = "vendor_return"
    rejected = "rejected"
    adjustment = "adjustment"


class LedgerTxnType(str, PyEnum):
    OPENING = "OPENING"
    PURCHASE = "PURCHASE"
    ISSUE = "ISSUE"
    RETURN = "RETURN"
    ADJUSTMENT = "ADJUSTMENT"


class AlertType(str, PyEnum):
    low_stock = "low_stock"
    high_stock = "high_stock"


class SparePriority(str, PyEnum):
    critical = "critical"
    high = "high"
    medium = "medium"


class ReconciliationStatus(str, PyEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# ------------------------- Users -------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(120))
    role = Column(Enum(UserRole, name="user_role"), nullable=False, default=UserRole.production)
    department = Column(String(80))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(500), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)


# ------------------------- Suppliers -------------------------
class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    supplier_name = Column(String(150), unique=True, nullable=False)
    gst_no = Column(String(20))
    address = Column(Text)
    email = Column(String(120))
    phone = Column(String(20))
    payment_terms = Column(String(100))
    rating = Column(Numeric(2, 1))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    materials = relationship("Material", back_populates="supplier")


# ------------------------- Materials -------------------------
class Material(Base):
    __tablename__ = "materials"

    material_code = Column(String(30), primary_key=True)
    material_name = Column(String(200), nullable=False)
    category = Column(String(80))
    material_type = Column(Enum(MaterialType, name="material_type_enum"),
                            nullable=False, default=MaterialType.PRODUCTION)
    grade = Column(String(50))
    size = Column(String(80))
    uom = Column(String(20), default="NOS")
    min_qty = Column(Numeric(12, 2))
    max_qty = Column(Numeric(12, 2))
    opening_qty = Column(Numeric(12, 2), nullable=False, default=0)
    current_qty = Column(Numeric(12, 2), nullable=False, default=0)   # engine-maintained, never set by hand
    reserved_qty = Column(Numeric(12, 2), nullable=False, default=0)
    unit_cost = Column(Numeric(12, 2), default=0)
    per_day_req = Column(Numeric(12, 2))
    warehouse = Column(String(50))
    rack = Column(String(50))
    bin = Column(String(50))
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"))
    hsn_code = Column(String(20))
    lead_time_days = Column(Integer, default=0)
    status = Column(String(20), default="active")
    low_stock_alert_open = Column(Boolean, default=False)
    high_stock_alert_open = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("min_qty IS NULL OR max_qty IS NULL OR min_qty <= max_qty", name="chk_min_max"),
        CheckConstraint(
            "material_type = 'CONSUMABLE' OR (min_qty IS NOT NULL AND max_qty IS NOT NULL)",
            name="chk_production_has_threshold",
        ),
    )

    supplier = relationship("Supplier", back_populates="materials")

    @property
    def available_qty(self):
        return (self.current_qty or 0) - (self.reserved_qty or 0)


# ------------------------- Stock Ledger + Batches -------------------------
class StockLedger(Base):
    __tablename__ = "stock_ledger"

    id = Column(BigInteger, primary_key=True)
    material_code = Column(String(30), ForeignKey("materials.material_code"), nullable=False)
    txn_type = Column(Enum(LedgerTxnType, name="ledger_txn_type"), nullable=False)
    qty_change = Column(Numeric(12, 2), nullable=False)
    balance_after = Column(Numeric(12, 2), nullable=False)
    ref_table = Column(String(30))
    ref_id = Column(Integer)
    batch_no = Column(String(50))
    remarks = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())


class StockBatch(Base):
    __tablename__ = "stock_batches"

    id = Column(Integer, primary_key=True)
    material_code = Column(String(30), ForeignKey("materials.material_code"), nullable=False)
    batch_no = Column(String(50), nullable=False)
    purchase_id = Column(Integer, ForeignKey("purchases.id", ondelete="SET NULL"))
    received_qty = Column(Numeric(12, 2), nullable=False)
    remaining_qty = Column(Numeric(12, 2), nullable=False)
    unit_cost = Column(Numeric(12, 2))
    received_date = Column(Date, server_default=func.current_date())
    warehouse = Column(String(50))
    rack = Column(String(50))


# ------------------------- Purchase / GRN -------------------------
class Purchase(Base):
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True)
    grn_no = Column(String(30), unique=True, nullable=False)
    material_code = Column(String(30), ForeignKey("materials.material_code"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"))
    invoice_no = Column(String(50))
    invoice_date = Column(Date)
    batch_no = Column(String(50))
    qty = Column(Numeric(12, 2), nullable=False)
    unit_cost = Column(Numeric(12, 2), default=0)
    # Point 7: where this specific batch was put away -- can differ GRN to GRN
    # even for the same material (e.g. overflow bin), separate from the
    # material's default master location.
    warehouse = Column(String(50))
    rack = Column(String(50))
    bin = Column(String(50))
    qc_status = Column(Enum(QCStatus, name="qc_status_type"), default=QCStatus.pending)
    qc_remarks = Column(Text)
    invoice_file_path = Column(String(255))
    received_by = Column(Integer, ForeignKey("users.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    # Accounts is the final approval step -- stock only ever increases once
    # this flips to 'approved' (see fn_trg_purchase_stock in schema.sql /
    # migration 0004). QC passing no longer moves stock by itself.
    accounts_approval_status = Column(String(20), nullable=False, default="pending")
    accounts_approved_by = Column(Integer, ForeignKey("users.id"))
    accounts_approved_at = Column(DateTime)

    __table_args__ = (CheckConstraint("qty > 0", name="chk_purchase_qty_positive"),)

    material = relationship("Material", foreign_keys=[material_code], viewonly=True)
    supplier = relationship("Supplier", foreign_keys=[supplier_id], viewonly=True)


# ------------------------- Employee Request + Issue -------------------------
class EmployeeRequest(Base):
    __tablename__ = "employee_requests"

    id = Column(Integer, primary_key=True)
    request_no = Column(String(30), unique=True, nullable=False)
    material_code = Column(String(30), ForeignKey("materials.material_code"), nullable=False)
    requested_qty = Column(Numeric(12, 2), nullable=False)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Mandatory: the actual person raising the request types their name here.
    # requested_by already tracks WHO was logged in, but the floor wants the
    # raiser's name captured explicitly on the request itself too.
    raised_by_name = Column(String(120), nullable=False)
    department = Column(String(80))
    job_card_no = Column(String(50))
    part_number = Column(String(80))
    purpose = Column(Text)
    status = Column(Enum(RequestStatus, name="request_status"), default=RequestStatus.pending)
    # --- Point 12: FIFO backorder tracking ---
    # fulfilled_qty accumulates every partial issue against this request.
    # pending_qty = requested_qty - fulfilled_qty (kept in sync in app code,
    # NOT DB-generated, because it must survive multiple partial fulfillments).
    fulfilled_qty = Column(Numeric(12, 2), nullable=False, default=0)
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    rejection_reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (CheckConstraint("requested_qty > 0", name="chk_request_qty_positive"),)

    # Used so API responses can include material_name without every caller
    # having to do a manual join -- the Requests/Backorders lists only had
    # material_code before, which wasn't useful without the name next to it.
    material = relationship("Material", foreign_keys=[material_code], viewonly=True)


class Issue(Base):
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True)
    issue_no = Column(String(30), unique=True, nullable=False)
    material_code = Column(String(30), ForeignKey("materials.material_code"), nullable=False)
    employee_request_id = Column(Integer, ForeignKey("employee_requests.id", ondelete="SET NULL"))
    job_card_no = Column(String(50))
    lot_no = Column(String(50))
    production_order_no = Column(String(50))
    part_number = Column(String(80))
    machine = Column(String(80))
    operation = Column(String(80))
    department = Column(String(80))
    shift = Column(String(30))
    required_qty = Column(Numeric(12, 2))
    issue_qty = Column(Numeric(12, 2), nullable=False)
    consumed_qty = Column(Numeric(12, 2), default=0)
    # pending_qty is a DB-generated column (STORED) -- not writable from the ORM
    completion_status = Column(String(20), default="issued")
    issued_by = Column(Integer, ForeignKey("users.id"))
    remark = Column(String(255))
    issue_date = Column(Date, server_default=func.current_date())
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (CheckConstraint("issue_qty > 0", name="chk_issue_qty_positive"),)

    material = relationship("Material", foreign_keys=[material_code], viewonly=True)


# ------------------------- Return -------------------------
class Return(Base):
    __tablename__ = "returns"

    id = Column(Integer, primary_key=True)
    return_no = Column(String(30), unique=True, nullable=False)
    material_code = Column(String(30), ForeignKey("materials.material_code"), nullable=False)
    return_type = Column(Enum(ReturnType, name="return_type_enum"), nullable=False)
    qty = Column(Numeric(12, 2))
    adjustment_qty = Column(Numeric(12, 2))
    reference_issue_id = Column(Integer, ForeignKey("issues.id", ondelete="SET NULL"))
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"))
    reason = Column(Text)
    returned_by_name = Column(String(120))  # point 5: who physically returned the material
    approved_by = Column(Integer, ForeignKey("users.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())

    material = relationship("Material", foreign_keys=[material_code], viewonly=True)


# ------------------------- Alerts / Notifications -------------------------
class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    material_code = Column(String(30), ForeignKey("materials.material_code", ondelete="CASCADE"), nullable=False)
    alert_type = Column(Enum(AlertType, name="alert_type"), nullable=False)
    available_qty = Column(Numeric(12, 2))
    threshold_qty = Column(Numeric(12, 2))
    message = Column(Text)
    is_resolved = Column(Boolean, default=False)
    triggered_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    role = Column(Enum(UserRole, name="user_role"))
    type = Column(String(30), default="info")
    title = Column(String(150))
    message = Column(Text)
    link = Column(String(255))
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


# ------------------------- Audit + Logging -------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True)
    table_name = Column(String(50), nullable=False)
    record_id = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)
    old_value = Column(Text)  # JSONB in DB; use dict via psycopg2 JSONB adapter at the app layer
    new_value = Column(Text)
    changed_by = Column(Integer, ForeignKey("users.id"))
    ip_address = Column(String(45))
    changed_at = Column(DateTime, server_default=func.now())


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(255), nullable=False)
    module = Column(String(50))
    ip_address = Column(String(45))
    created_at = Column(DateTime, server_default=func.now())


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    username_attempted = Column(String(50))
    success = Column(Boolean, default=False)
    ip_address = Column(String(45))
    user_agent = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(BigInteger, primary_key=True)
    path = Column(String(255))
    method = Column(String(10))
    status_code = Column(Integer)
    error_message = Column(Text, nullable=False)
    traceback = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())


class CriticalSpare(Base):
    __tablename__ = "critical_spares"

    id = Column(Integer, primary_key=True)
    material_code = Column(String(30), ForeignKey("materials.material_code", ondelete="CASCADE"), nullable=False)
    machine_name = Column(String(150))
    priority = Column(Enum(SparePriority, name="spare_priority"), nullable=False, default=SparePriority.critical)
    threshold_qty = Column(Numeric(12, 2), nullable=False)
    remarks = Column(Text)
    added_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("material_code", "machine_name", name="uq_critical_spare_machine"),
    )

    material = relationship("Material")


class StockReconciliation(Base):
    __tablename__ = "stock_reconciliations"

    id = Column(Integer, primary_key=True)
    material_code = Column(String(30), ForeignKey("materials.material_code"), nullable=False)
    system_qty = Column(Numeric(12, 2), nullable=False)
    physical_qty = Column(Numeric(12, 2), nullable=False)
    difference_qty = Column(Numeric(12, 2), nullable=False)
    remarks = Column(Text)
    status = Column(Enum(ReconciliationStatus, name="reconciliation_status"),
                     nullable=False, default=ReconciliationStatus.pending)
    counted_by = Column(Integer, ForeignKey("users.id"))
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    review_remarks = Column(Text)
    return_id = Column(Integer, ForeignKey("returns.id"))
    created_at = Column(DateTime, server_default=func.now())
    reviewed_at = Column(DateTime)

    material = relationship("Material")


class DownloadLog(Base):
    __tablename__ = "download_logs"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    file_name = Column(String(255), nullable=False)
    report_type = Column(String(50))
    format = Column(String(10))
    ip_address = Column(String(45))
    created_at = Column(DateTime, server_default=func.now())
