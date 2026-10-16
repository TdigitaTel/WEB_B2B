from datetime import date, datetime
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


class OpeningDay(BaseModel):
    enabled: bool = True
    morning_from: str = ""
    morning_to: str = ""
    afternoon_from: str = ""
    afternoon_to: str = ""

    @model_validator(mode="after")
    def validate_hours(self):
        if not self.enabled:
            return self
        from datetime import time
        windows = []
        for start, end in [(self.morning_from, self.morning_to), (self.afternoon_from, self.afternoon_to)]:
            if bool(start) != bool(end):
                raise ValueError("Indica apertura y cierre de cada turno")
            if start:
                if len(start) != 5 or len(end) != 5:
                    raise ValueError("Usa horas HH:MM")
                first, last = time.fromisoformat(start), time.fromisoformat(end)
                if first >= last:
                    raise ValueError("El cierre debe ser posterior a la apertura")
                windows.append((first, last))
        if len(windows) == 2 and windows[0][1] > windows[1][0]:
            raise ValueError("Los turnos no pueden solaparse")
        return self


class PickupSettingsIn(BaseModel):
    schedules: dict[str, list[OpeningDay]] | None = None

    @model_validator(mode="after")
    def validate_days(self):
        if self.schedules is not None and any(len(days) != 7 for days in self.schedules.values()):
            raise ValueError("Configura los siete días de cada sede")
        return self

    preparation_minutes: int = Field(ge=1, le=10080)


class OrderCreate(BaseModel):
    pickup_date: date | None = None
    store_id: str | None = None
    company_code: int | None = None
    delegation_code: str | None = Field(default=None, max_length=40)
    draft: bool = False
    customer_reference: str | None = Field(default=None, max_length=100)
    job_name: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


class PickupChange(BaseModel):
    pickup_date: date | None


class DeliveryConfirmation(BaseModel):
    order_id: str = Field(min_length=1, max_length=80)
    order_date: date


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


class WebOrderRegistrationChange(BaseModel):
    state: str = Field(pattern="^(PENDIENTE|REGISTRADO)$")
    exit_order_number: str | None = Field(default=None, max_length=80)


class UserDisplayPreferences(BaseModel):
    model_config = {"extra": "forbid"}
    show_delivery_note_images: bool
    show_order_images: bool
