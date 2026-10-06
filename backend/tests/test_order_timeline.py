from datetime import datetime
from types import SimpleNamespace
from app.order_timeline import preparation_time, exit_events
from app.config import settings

def record(**values):
    defaults=dict(recorded_at=datetime(2026,10,5,9,30), prepared_at=None, delivered_at=None,
                  invoiced_at=None, source_updated_at=datetime(2026,10,6,15,42))
    return SimpleNamespace(**(defaults|values))

def test_preparation_without_time_uses_configured_offset(monkeypatch):
    monkeypatch.setattr(settings,'exit_preparation_offset_seconds',25)
    stamp=preparation_time(datetime(2026,10,6),datetime(2026,10,5,9,30))
    assert (stamp.day,stamp.hour,stamp.minute,stamp.second)==(6,9,30,25)

def test_preparation_real_time_is_preserved():
    stamp=preparation_time(datetime(2026,10,6,8,10),datetime(2026,10,5,9,30))
    assert (stamp.hour,stamp.minute,stamp.second)==(8,10,0)

def test_delivery_requires_printing_and_invoice_has_no_time():
    data=record(delivered_at=datetime(2026,10,5),invoiced_at=datetime(2026,10,6,18,20))
    delivery=dict(attended_at=datetime(2026,10,5,11),is_printed=False,is_invoiced=True)
    events=dict((state,stamp) for state,stamp,_ in exit_events(data,delivery))
    assert 'ENTREGADO' not in events
    assert events['FACTURADO'].hour==0
    delivery['is_printed']=True
    events=dict((state,stamp) for state,stamp,_ in exit_events(data,delivery))
    assert (events['ENTREGADO'].day,events['ENTREGADO'].hour,events['ENTREGADO'].minute)==(5,15,42)

def test_exit_does_not_invent_web_or_missing_stages():
    assert [state for state,_,_ in exit_events(record())]==['REGISTRADO']
