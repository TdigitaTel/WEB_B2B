"""Find a preparation window today, including the next afternoon shift."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from .models import PickupSettings


def immediate_ready_at(db, company, delegation, now=None):
    now = now or datetime.now(ZoneInfo("Europe/Madrid"))
    config = db.get(PickupSettings, 1)
    days = (config.schedules or {}).get(f"{company}:{delegation}") if config else None
    if not days:
        return None
    day = days[now.weekday()]
    if not day.get("enabled", True):
        return None
    windows = []
    for period in ("morning", "afternoon"):
        start, end = day.get(period+"_from"), day.get(period+"_to")
        if start and end:
            opening = datetime.combine(now.date(), time.fromisoformat(start), now.tzinfo)
            closing = datetime.combine(now.date(), time.fromisoformat(end), now.tzinfo)
            if windows and opening <= windows[-1][1]:
                windows[-1] = (windows[-1][0], max(closing, windows[-1][1]))
            else:
                windows.append((opening, closing))
    for opening, closing in windows:
        ready = max(now, opening) + timedelta(minutes=config.preparation_minutes)
        if ready <= closing:
            return ready
    return None


def immediate_available(db, company, delegation, now=None):
    return immediate_ready_at(db, company, delegation, now) is not None


def next_open_date(db, company, delegation, now=None):
    now = now or datetime.now(ZoneInfo("Europe/Madrid"))
    config = db.get(PickupSettings, 1)
    days = (config.schedules or {}).get(f"{company}:{delegation}") if config else None
    if not days:
        return None
    for offset in range(1, 8):
        candidate = now.date() + timedelta(days=offset)
        day = days[candidate.weekday()]
        if day.get("enabled", True) and any(day.get(period+"_from") and day.get(period+"_to") for period in ("morning", "afternoon")):
            return candidate
    return None


def scheduled_date_open(db, company, delegation, day):
    config = db.get(PickupSettings, 1)
    days = (config.schedules or {}).get(f"{company}:{delegation}") if config else None
    if not days:
        return False
    hours = days[day.weekday()]
    return hours.get("enabled", True) and any(hours.get(period+"_from") and hours.get(period+"_to") for period in ("morning", "afternoon"))


def scheduled_ready_at(db, company, delegation, pickup_date):
    """Apertura del día elegido más el mismo tiempo de preparación de inmediata."""
    start = datetime.combine(pickup_date, time.min, ZoneInfo("Europe/Madrid"))
    return immediate_ready_at(db, company, delegation, start)


def pickup_slots(db, company, delegation, pickup_date):
    """Franjas locales de una hora; nunca atraviesan el cierre de una sede."""
    config = db.get(PickupSettings, 1)
    days = (config.schedules or {}).get(f"{company}:{delegation}") if config else None
    if not days or not days[pickup_date.weekday()].get("enabled", True):
        return []
    day = days[pickup_date.weekday()]
    windows = []
    for period in ("morning", "afternoon"):
        start, end = day.get(period+"_from"), day.get(period+"_to")
        if start and end:
            opening = datetime.combine(pickup_date, time.fromisoformat(start), ZoneInfo("Europe/Madrid"))
            closing = datetime.combine(pickup_date, time.fromisoformat(end), opening.tzinfo)
            if closing > opening:
                windows.append((opening, closing))
    merged = []
    for opening, closing in sorted(windows):
        if merged and opening <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(closing, merged[-1][1]))
        else:
            merged.append((opening, closing))
    result = []
    for opening, closing in merged:
        earliest = opening + timedelta(minutes=config.preparation_minutes)
        start = opening
        while start < closing:
            end = min(start + timedelta(hours=1), closing)
            ready = max(start, earliest)
            if ready <= end and ready <= closing:
                result.append({"start":start.strftime("%H:%M"), "end":end.strftime("%H:%M"), "ready_at":ready.isoformat()})
            start = end
    return result


def pickup_slot_ready_at(db, company, delegation, pickup_date, start=None, end=None):
    from fastapi import HTTPException
    if not start and not end:
        return scheduled_ready_at(db, company, delegation, pickup_date)
    for slot in pickup_slots(db, company, delegation, pickup_date):
        if slot['start'] == start and slot['end'] == end:
            return datetime.fromisoformat(slot['ready_at'])
    raise HTTPException(422, "La franja elegida no está disponible en el horario de esta sede y fecha")


def assign_attention_deadline(order, db, *, operator_override=False, now=None):
    """Conserva el compromiso del pedido aunque después cambien los parámetros."""
    from datetime import timezone
    from fastapi import HTTPException
    now = now or datetime.now(ZoneInfo("Europe/Madrid"))
    config = db.get(PickupSettings, 1)
    minutes = config.preparation_minutes if config else 60
    if order.pickup_date:
        ready = pickup_slot_ready_at(db, order.company_code, order.delegation_code, order.pickup_date,
            getattr(order, "pickup_slot_start", None), getattr(order, "pickup_slot_end", None))
    elif operator_override:
        ready = now + timedelta(minutes=minutes)
    else:
        ready = immediate_ready_at(db, order.company_code, order.delegation_code, now)
    if ready is None:
        raise HTTPException(409, "No hay un horario de atención que permita preparar el pedido; revisa la fecha y el horario de la sede")
    order.attention_deadline_at = ready.astimezone(timezone.utc)
    order.preparation_minutes_snapshot = minutes
