from pydantic import BaseModel, Field, computed_field, model_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class EmployeeRequestIn(BaseModel):
    material_code: str
    requested_qty: Decimal = Field(gt=0)
    raised_by_name: str = Field(min_length=1, description="Name of the person raising this request (mandatory)")
    department: Optional[str] = None
    job_card_no: Optional[str] = None
    part_number: Optional[str] = None
    purpose: Optional[str] = None


class EmployeeRequestDecision(BaseModel):
    action: str = Field(description="approve|reject")
    rejection_reason: Optional[str] = None


class EmployeeRequestOut(BaseModel):
    id: int
    request_no: str
    material_code: str
    material_name: Optional[str] = None
    requested_qty: Decimal
    fulfilled_qty: Decimal = Decimal("0")
    requested_by: int
    raised_by_name: Optional[str] = None
    department: Optional[str]
    job_card_no: Optional[str]
    part_number: Optional[str]
    purpose: Optional[str]
    status: str
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    rejection_reason: Optional[str]
    created_at: datetime
    stock_warning: Optional[str] = None  # point 8: set only in the create_request response

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _inject_material_name(cls, data):
        # `material` is a viewonly SQLAlchemy relationship (see models.py) --
        # pull the name off it here so every endpoint that returns this
        # schema automatically includes material_name, without each one
        # having to remember to join/attach it manually.
        material = getattr(data, "material", None)
        if material is None:
            return data
        return {
            **{f: getattr(data, f, None) for f in cls.model_fields if f != "material_name"},
            "material_name": material.material_name,
        }

    @computed_field
    @property
    def pending_qty(self) -> Decimal:
        return self.requested_qty - self.fulfilled_qty

    class Config:
        from_attributes = True


# Direct store-issue (Route Card module) — bypasses employee_request when store
# manager issues material directly against a production order / job card.
# NOTE: this is kept only as the shared field-set for IssueOut. The endpoint
# that let you create one of these WITHOUT a request has been removed --
# every issue now has to come from an approved employee_request (see
# IssueFromRequestIn below).
class IssueIn(BaseModel):
    material_code: str
    employee_request_id: Optional[int] = None
    job_card_no: Optional[str] = None
    lot_no: Optional[str] = None
    production_order_no: Optional[str] = None
    part_number: Optional[str] = None
    machine: Optional[str] = None
    operation: Optional[str] = None
    department: Optional[str] = None
    shift: Optional[str] = None
    required_qty: Optional[Decimal] = None
    issue_qty: Decimal = Field(gt=0)
    remark: Optional[str] = None


class IssueFromRequestIn(BaseModel):
    """Store creates an issue against an already Operation-approved request.
    material_code/employee_request_id come from the request itself, not
    from this payload. Stock does NOT move yet -- only once Accounts
    approves this issue (see IssueAccountsApproval)."""
    issue_qty: Decimal = Field(gt=0)
    job_card_no: Optional[str] = None
    production_order_no: Optional[str] = None
    part_number: Optional[str] = None
    machine: Optional[str] = None
    operation: Optional[str] = None
    department: Optional[str] = None
    shift: Optional[str] = None
    required_qty: Optional[Decimal] = None
    remark: Optional[str] = None


class IssueAccountsApproval(BaseModel):
    status: str = Field(description="approved|rejected")
    remarks: Optional[str] = None


class IssueBatchAllocationOut(BaseModel):
    batch_no: Optional[str] = None
    qty_taken: Decimal
    supplier_name: Optional[str] = None
    received_date: Optional[date] = None

    class Config:
        from_attributes = True


class FIFOCheckIn(BaseModel):
    """Dry-run FIFO preview request for the Issue form."""
    material_code: str
    quantity: float = Field(gt=0)


class IssueConsumptionUpdate(BaseModel):
    consumed_qty: Decimal = Field(ge=0)
    completion_status: str = Field(default="completed", description="issued|partial|completed")


class IssueOut(BaseModel):
    id: int
    issue_no: str
    material_code: str
    material_name: Optional[str] = None
    employee_request_id: Optional[int]
    job_card_no: Optional[str]
    lot_no: Optional[str]
    production_order_no: Optional[str]
    part_number: Optional[str]
    machine: Optional[str]
    operation: Optional[str]
    department: Optional[str]
    shift: Optional[str]
    required_qty: Optional[Decimal]
    issue_qty: Decimal
    consumed_qty: Optional[Decimal]
    completion_status: str
    issued_by: Optional[int]
    issued_by_name: Optional[str] = None
    remark: Optional[str]
    issue_date: date
    created_at: datetime
    accounts_approval_status: str = "pending"
    accounts_approved_by: Optional[int] = None
    accounts_approved_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _inject_material_name(cls, data):
        # `data` is the SQLAlchemy ORM object here (from_attributes=True).
        # Pull material_name off the `material` relationship (see models.py)
        # so callers get the human-readable name alongside material_code
        # without every endpoint having to remember a manual join.
        material = getattr(data, "material", None)
        if material is None:
            return data
        return {
            **{f: getattr(data, f, None) for f in cls.model_fields if f != "material_name"},
            "material_name": material.material_name,
        }


class ReturnIn(BaseModel):
    material_code: str
    return_type: str = Field(description="unused|vendor_return|rejected|adjustment")
    qty: Optional[Decimal] = Field(default=None, gt=0)
    adjustment_qty: Optional[Decimal] = None
    reference_issue_id: Optional[int] = None
    supplier_id: Optional[int] = None
    reason: Optional[str] = None
    returned_by_name: Optional[str] = None


class ReturnOut(BaseModel):
    id: int
    return_no: str
    material_code: str
    material_name: Optional[str] = None
    return_type: str
    qty: Optional[Decimal]
    adjustment_qty: Optional[Decimal]
    reference_issue_id: Optional[int]
    supplier_id: Optional[int]
    reason: Optional[str]
    returned_by_name: Optional[str]
    approved_by: Optional[int]
    created_by: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _inject_material_name(cls, data):
        material = getattr(data, "material", None)
        if material is None:
            return data
        return {
            **{f: getattr(data, f, None) for f in cls.model_fields if f != "material_name"},
            "material_name": material.material_name,
        }
