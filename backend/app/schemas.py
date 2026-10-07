from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator


class LoginIn(BaseModel):
    email: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6, max_length=200)


class CustomerAccessReset(BaseModel):
    customer_code: str = Field(min_length=1, max_length=40)
    new_password: str = Field(min_length=6, max_length=200)


class CartItemIn(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0, le=99999)


class CartItemUpdate(BaseModel):
    quantity: Decimal = Field(gt=0, le=99999)


class OrderCreate(BaseModel):
    store_id: str | None = None
    company_code: int | None = None
    delegation_code: str | None = Field(default=None, max_length=40)
    draft: bool = False
    customer_reference: str | None = Field(default=None, max_length=100)
    job_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


class StatusChange(BaseModel):
    estado_registro_exit: str
    note: str | None = Field(default=None, max_length=500)


class ExternalStatusChange(BaseModel):
    order_id: str | None = Field(default=None, min_length=1, max_length=80)
    order_number: str | None = Field(default=None, min_length=1, max_length=80)
    estado_registro_exit: str
    source: str = Field(default="EXTERNA", min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    nro_pedido_exit: str | None = Field(default=None, max_length=80)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def require_order_identifier(self):
        if not self.order_id and not self.order_number:
            raise ValueError("Debes indicar order_id u order_number")
        return self
