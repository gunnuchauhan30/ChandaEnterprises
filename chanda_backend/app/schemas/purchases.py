from pydantic import BaseModel, Field, model_validator
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
    material_name: Optional[str] = None
    supplier_id: Optional[int]
    supplier_name: Optional[str] = None
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

    @model_validator(mode="before")
    @classmethod
    def _inject_material_name(cls, data):
        # Point (GRN supplier fix): also inject supplier_name the same way
        # material_name is injected -- from the ORM relationship, since the
        # frontend needs the supplier's actual name, not just its numeric ID.
        material = getattr(data, "material", None)
        supplier = getattr(data, "supplier", None)
        if material is None and supplier is None:
            return data
        result = {f: getattr(data, f, None) for f in cls.model_fields if f not in ("material_name", "supplier_name")}
        result["material_name"] = material.material_name if material else None
        result["supplier_name"] = supplier.supplier_name if supplier else None
        return result
