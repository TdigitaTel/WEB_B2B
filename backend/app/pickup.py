"""Preparation must fit completely within the current opening shift."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from .models import PickupSettings


def immediate_available(db, company, delegation, now=None):
    now = now or datetime.now(ZoneInfo("Europe/Madrid"))
    config = db.get(PickupSettings, 1)
    schedules = config.schedules if config and config.schedules else {}
    days = schedules.get(f"{company}:{delegation}")
    if not days:
        return False
    day = days[now.weekday()]
    ready = now + timedelta(minutes=config.preparation_minutes)
    for period in ("morning", "afternoon"):
        start, end = day.get(period+"_from"), day.get(period+"_to")
        if start and end:
            opening = datetime.combine(now.date(), time.fromisoformat(start), now.tzinfo)
            closing = datetime.combine(now.date(), time.fromisoformat(end), now.tzinfo)
            if opening <= now and ready <= closing:
                return True
    return False


def next_open_date(db, company, delegation, now=None):
    now = now or datetime.now(ZoneInfo("Europe/Madrid"))
    config = db.get(PickupSettings, 1)
    days = (config.schedules or {}).get(f"{company}:{delegation}") if config else None
    if not days:
        return None
    for offset in range(1, 8):
        candidate = now.date() + timedelta(days=offset)
        day = days[candidate.weekday()]
        if any(day.get(period+"_from") and day.get(period+"_to") for period in ("morning", "afternoon")):
            return candidate
    return None


def scheduled_date_open(db, company, delegation, day):
    config = db.get(PickupSettings, 1)
    days = (config.schedules or {}).get(f"{company}:{delegation}") if config else None
    if not days:
        return False
    hours = days[day.weekday()]
    return any(hours.get(period+"_from") and hours.get(period+"_to") for period in ("morning", "afternoon"))
