from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class CartItemIn(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0, le=99999)


class CartItemUpdate(BaseModel):
    quantity: Decimal = Field(gt=0, le=99999)


class OrderCreate(BaseModel):
    store_id: str
    draft: bool = False
    customer_reference: str | None = Field(default=None, max_length=100)
    job_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


class StatusChange(BaseModel):
    estado_registro_exit: str
    note: str | None = Field(default=None, max_length=500)


class ExternalStatusChange(BaseModel):
    order_number: str = Field(min_length=1, max_length=80)
    estado_registro_exit: str
    source: str = Field(default="EXTERNA", min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    nro_pedido_exit: str | None = Field(default=None, max_length=80)
    occurred_at: datetime | None = None
