from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class SupplierIn(BaseModel):
    supplier_name: str = Field(max_length=150)
    gst_no: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    payment_terms: Optional[str] = None
    rating: Optional[Decimal] = Field(default=None, ge=0, le=5)
    is_active: bool = True


class SupplierOut(SupplierIn):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class MaterialIn(BaseModel):
    material_code: str = Field(max_length=30)
    material_name: str = Field(max_length=200)
    category: Optional[str] = None
    material_type: str = Field(default="PRODUCTION", description="PRODUCTION|CONSUMABLE")
    grade: Optional[str] = None
    size: Optional[str] = None
    uom: str = "NOS"
    min_qty: Optional[Decimal] = None
    max_qty: Optional[Decimal] = None
    opening_qty: Decimal = Decimal("0")
    unit_cost: Decimal = Decimal("0")
    per_day_req: Optional[Decimal] = None
    warehouse: Optional[str] = None
    rack: Optional[str] = None
    bin: Optional[str] = None
    supplier_id: Optional[int] = None
    hsn_code: Optional[str] = None
    lead_time_days: int = 0
    status: str = "active"


class MaterialUpdate(BaseModel):
    material_name: Optional[str] = None
    category: Optional[str] = None
    material_type: Optional[str] = None
    grade: Optional[str] = None
    size: Optional[str] = None
    uom: Optional[str] = None
    min_qty: Optional[Decimal] = None
    max_qty: Optional[Decimal] = None
    unit_cost: Optional[Decimal] = None
    per_day_req: Optional[Decimal] = None
    warehouse: Optional[str] = None
    rack: Optional[str] = None
    bin: Optional[str] = None
    supplier_id: Optional[int] = None
    hsn_code: Optional[str] = None
    lead_time_days: Optional[int] = None
    status: Optional[str] = None
    # NOTE: current_qty is intentionally NOT editable here.
    # Stock only ever changes via Purchase / Issue / Return transactions.


class MaterialOut(BaseModel):
    material_code: str
    material_name: str
    category: Optional[str]
    material_type: str
    grade: Optional[str]
    size: Optional[str]
    uom: str
    min_qty: Optional[Decimal]
    max_qty: Optional[Decimal]
    opening_qty: Decimal
    current_qty: Decimal
    reserved_qty: Decimal
    available_qty: Decimal
    unit_cost: Decimal
    per_day_req: Optional[Decimal]
    warehouse: Optional[str]
    rack: Optional[str]
    bin: Optional[str]
    supplier_id: Optional[int]
    hsn_code: Optional[str]
    lead_time_days: int
    status: str
    low_stock_alert_open: bool
    high_stock_alert_open: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
