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
    customer_reference: str | None = Field(default=None, max_length=100)
    job_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


class StatusChange(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=500)

