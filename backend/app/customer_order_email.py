"""Notification choices belong to the ERP customer, never to a login email."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import text
from sqlalchemy.orm import Session
from .account_permissions import effective_permissions
from .auth import current_user, audit
from .customer_catalog import own_customer_code
from .db import get_db
from .models import CustomerOrderEmailSetting, User
from .order_email_settings import email_address

router = APIRouter(prefix='/api/v1/account/order-emails', tags=['account'])


def preferences(db, code):
    row = db.get(CustomerOrderEmailSetting, code)
    return {name: bool(row and getattr(row, name)) for name in ('email1_enabled', 'email2_enabled')}


def destinations(customer, selected):
    """Resolve current ERP slots. Web, login email and legacy local copies never qualify."""
    result = []
    for slot in ('email1', 'email2'):
        if not selected.get(slot + '_enabled'):
            continue
        try:
            address = email_address(str(customer.get(slot) or (customer.get('email') if slot == 'email1' else '') or ''))
        except ValueError:
            continue
        duplicate = next((entry for entry in result if entry['address'].casefold() == address.casefold()), None)
        if duplicate:
            duplicate['slots'].append(slot)
        else:
            result.append({'address': address, 'slots': [slot]})
    return result


class RecipientPreference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email1_enabled: StrictBool
    email2_enabled: StrictBool


@router.patch('')
def update_preference(data: RecipientPreference, user: User = Depends(current_user), db: Session = Depends(get_db)):
    code = own_customer_code(user, db)
    if user.parent_user_id is not None or not effective_permissions(user, db)['can_manage_preferences']:
        raise HTTPException(403, 'Los destinatarios los elige la cuenta principal del cliente')
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': 'order-emails:' + code})
    # Read the ERP now; never accept an arbitrary address or another customer from the browser.
    from .main import fetch_customer
    try:
        customer = fetch_customer(code)
    except Exception:
        raise HTTPException(503, 'No se pudo actualizar la ficha desde EXIT. Inténtalo de nuevo') from None
    if not customer:
        raise HTTPException(404, 'El cliente no está disponible en EXIT')
    values = data.model_dump()
    for slot in ('email1', 'email2'):
        if values[slot + '_enabled'] and not destinations(customer, {slot + '_enabled': True}):
            raise HTTPException(422, f'{slot.title()} no contiene un correo válido en EXIT')
    row = db.get(CustomerOrderEmailSetting, code, populate_existing=True)
    before = preferences(db, code)
    if row is None:
        row = CustomerOrderEmailSetting(customer_code=code)
        db.add(row)
    row.email1_enabled = data.email1_enabled
    row.email2_enabled = data.email2_enabled
    if not any(before.values()) and any(values.values()):
        # Start at the current state; opting in must never replay historical changes.
        from .order_email_events import baseline_customer
        baseline_customer(db, code)
    audit(db, user, 'CUSTOMER_ORDER_EMAIL_RECIPIENTS_CHANGED', 'CUSTOMER', code, values)
    db.commit()
    return {**customer, 'order_email_recipients': values}
