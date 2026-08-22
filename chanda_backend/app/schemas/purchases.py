from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class PurchaseIn(BaseModel):
    material_code: str
    supplier_id: Optional[int] = None
    invoice_no: Optional[str] = None
    invoice_date: Optional[date] = None
    batch_no: Optional[str] = None
    qty: Decimal = Field(gt=0)
    unit_cost: Decimal = Decimal("0")
    warehouse: Optional[str] = None
    rack: Optional[str] = None
    bin: Optional[str] = None


class PurchaseQCUpdate(BaseModel):
    qc_status: str = Field(description="pending|passed|failed")
    qc_remarks: Optional[str] = None


class PurchaseOut(BaseModel):
    id: int
    grn_no: str
    material_code: str
    supplier_id: Optional[int]
    invoice_no: Optional[str]
    invoice_date: Optional[date]
    batch_no: Optional[str]
    qty: Decimal
    unit_cost: Decimal
    warehouse: Optional[str]
    rack: Optional[str]
    bin: Optional[str]
    qc_status: str
    qc_remarks: Optional[str]
    invoice_file_path: Optional[str]
    received_by: Optional[int]
    created_by: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True
