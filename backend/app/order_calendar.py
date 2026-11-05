"""La agenda usa la previsión vigente; una franja solo vale en su fecha acordada."""
from zoneinfo import ZoneInfo
from datetime import timezone


def appointment(order):
    expected = order.attention_deadline_at
    if expected is not None:
        if expected.tzinfo is None:
            expected = expected.replace(tzinfo=timezone.utc)
        local = expected.astimezone(ZoneInfo('Europe/Madrid'))
        day = local.date()
    else:
        day = order.pickup_date
    window = bool(order.pickup_date == day and order.pickup_slot_start and order.pickup_slot_end)
    if window and expected is not None:
        window = order.pickup_slot_start <= local.strftime('%H:%M') <= order.pickup_slot_end
    return {'calendar_date':day, 'calendar_slot_start':order.pickup_slot_start if window else None,
        'calendar_slot_end':order.pickup_slot_end if window else None,
        'calendar_time_source':'PICKUP_WINDOW' if window else 'EXPECTED' if expected else 'DATE_ONLY'}
