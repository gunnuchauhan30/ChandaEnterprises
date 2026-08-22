from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class StockBatchOut(BaseModel):
    id: int
    material_code: str
    batch_no: str
    purchase_id: Optional[int]
    received_qty: Decimal
    remaining_qty: Decimal
    unit_cost: Optional[Decimal]
    received_date: Optional[date]
    warehouse: Optional[str]
    rack: Optional[str]

    class Config:
        from_attributes = True


class StockLedgerOut(BaseModel):
    id: int
    material_code: str
    txn_type: str
    qty_change: Decimal
    balance_after: Decimal
    ref_table: Optional[str]
    ref_id: Optional[int]
    batch_no: Optional[str]
    remarks: Optional[str]
    created_by: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class AlertOut(BaseModel):
    id: int
    material_code: str
    alert_type: str
    available_qty: Optional[Decimal]
    threshold_qty: Optional[Decimal]
    message: Optional[str]
    is_resolved: bool
    triggered_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


class NotificationOut(BaseModel):
    id: int
    user_id: Optional[int]
    role: Optional[str]
    type: str
    title: Optional[str]
    message: Optional[str]
    link: Optional[str]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CriticalSpareIn(BaseModel):
    material_code: str
    machine_name: Optional[str] = None
    priority: str = "critical"  # critical|high|medium
    threshold_qty: Decimal
    remarks: Optional[str] = None


class CriticalSpareUpdate(BaseModel):
    machine_name: Optional[str] = None
    priority: Optional[str] = None
    threshold_qty: Optional[Decimal] = None
    remarks: Optional[str] = None


class CriticalSpareOut(BaseModel):
    id: int
    material_code: str
    machine_name: Optional[str]
    priority: str
    threshold_qty: Decimal
    remarks: Optional[str]
    added_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    # enriched at read-time from the linked material, not stored here
    material_name: Optional[str] = None
    current_qty: Optional[Decimal] = None
    uom: Optional[str] = None
    is_below_threshold: Optional[bool] = None

    class Config:
        from_attributes = True


class ReconciliationIn(BaseModel):
    material_code: str
    physical_qty: Decimal
    remarks: Optional[str] = None


class ReconciliationDecision(BaseModel):
    action: str  # approve|reject
    review_remarks: Optional[str] = None


class ReconciliationOut(BaseModel):
    id: int
    material_code: str
    system_qty: Decimal
    physical_qty: Decimal
    difference_qty: Decimal
    remarks: Optional[str]
    status: str
    counted_by: Optional[int]
    reviewed_by: Optional[int]
    review_remarks: Optional[str]
    return_id: Optional[int]
    created_at: datetime
    reviewed_at: Optional[datetime]
    material_name: Optional[str] = None

    class Config:
        from_attributes = True


class DashboardOut(BaseModel):
    total_stock_qty: Decimal
    total_stock_value: Decimal
    todays_purchase_count: int
    todays_purchase_qty: Decimal
    todays_issue_count: int
    todays_issue_qty: Decimal
    low_stock_count: int
    high_stock_count: int
    pending_employee_requests: int
    pending_qc: int
    unread_notifications: int
    monthly_consumption: list
    purchase_trend: list
    issue_trend: list
    department_consumption: list
