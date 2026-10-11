from datetime import date
from fastapi.testclient import TestClient
from app.main import app
from app import main as main_module


def test_invoice_number_ignores_dates_but_list_keeps_them(monkeypatch):
    calls=[]
    monkeypatch.setattr(main_module,'fetch_customer_invoices',lambda *args: calls.append(args) or [])
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code == 200
    assert client.get('/api/v1/invoices?document_number=2025-AL-123&date_from=2026-10-01&date_to=2026-10-11').status_code == 200
    assert calls[-1][2:] == ('2025-AL-123',None,None)
    assert client.get('/api/v1/invoices?date_from=2026-10-01&date_to=2026-10-11').status_code == 200
    assert calls[-1][2:] == ('',date(2026,10,1),date(2026,10,11))
