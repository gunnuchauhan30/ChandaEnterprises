from pydantic import BaseModel, Field, computed_field
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


class EmployeeRequestIn(BaseModel):
    material_code: str
    requested_qty: Decimal = Field(gt=0)
    department: Optional[str] = None
    job_card_no: Optional[str] = None
    part_number: Optional[str] = None
    purpose: Optional[str] = None


class EmployeeRequestLineItem(BaseModel):
    """Single line item for bulk request"""
    material_code: str
    requested_qty: Decimal = Field(gt=0)


class EmployeeRequestBulkIn(BaseModel):
    """Bulk request with multiple materials at once (UPDATE 5-POINTS)"""
    department: str
    job_card_no: Optional[str] = None
    part_number: Optional[str] = None
    purpose: Optional[str] = None
    items: List[EmployeeRequestLineItem] = Field(min_items=1, max_items=20)


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

    @computed_field
    @property
    def pending_qty(self) -> Decimal:
        return self.requested_qty - self.fulfilled_qty

    class Config:
        from_attributes = True


# Direct store-issue (Route Card module) — bypasses employee_request when store
# manager issues material directly against a production order / job card.
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

    class Config:
        from_attributes = True


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
