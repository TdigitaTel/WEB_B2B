from datetime import datetime, timezone

from sqlalchemy import select

from app import main as module
from app.db import SessionLocal
from app.models import Order, User
from app.order_search import matches_order_search, order_number_sort_key
from test_customer_order_identity import client


def test_exact_lookup_and_numeric_ordering():
    assert matches_order_search({'web_number': 'WEB-2026-000286'}, 'web-2026-000286')
    assert matches_order_search({'exit_number': '2026/AL/6008375'}, '6008375')
    assert not matches_order_search({'exit_number': '2026/AL/6008375'}, '8375')
    assert not matches_order_search({'number': 'WEB-2026-000286'}, '286')
    rows=[{'number': 'WEB-2026-9'}, {'number': 'WEB-2026-100'}, {'exit_order_number': '20'}]
    assert [order_number_sort_key(row)[0] for row in sorted(rows,key=order_number_sort_key,reverse=True)]==[100,20,9]


def test_individual_lookup_ignores_dates_state_but_keeps_customer_scope(monkeypatch):
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        row=Order(order_number='WEB-2020-SEARCH',customer_code='CLI00001',user_id=user.id,
                  origen_pedido='B2B',estado_registro_exit='ENTREGADO',company_code=0,delegation_code='00',
                  exit_order_year=2020,exit_series='AL',exit_order_number='98765432',
                  nro_pedido_exit='2020/AL/98765432',created_at=datetime(2020,1,1,tzinfo=timezone.utc))
        db.add(row)
        db.add(Order(order_number='WEB-2020-FOREIGN',customer_code='OTHER',user_id=user.id,
                     origen_pedido='B2B',estado_registro_exit='PENDIENTE',company_code=8,delegation_code='00',
                     exit_order_number='98765432',created_at=datetime(2020,1,1,tzinfo=timezone.utc)))
        db.commit();oid=row.public_id
    calls=[]
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *args,**kwargs: calls.append((args,kwargs)) or [])
    monkeypatch.setattr(module,'fetch_customer_delivery_statuses',lambda *args: [])
    customer=client()
    for query in ('web-2020-search','98765432'):
        response=customer.get('/api/v1/orders',params={'date_from':'2026-10-01','date_to':'2026-10-29','state':'PENDIENTE','order_query':query})
        assert response.status_code==200,response.text
        assert [row['id'] for row in response.json()]==[oid]
        assert calls[-1][0][0]=='CLI00001' and calls[-1][1]['order_number']=='98765432'
    assert customer.get('/api/v1/orders?order_query=WEB-2020-FOREIGN').json()==[]
    assert customer.get('/api/v1/orders?order_query=2026/AL/98765432').status_code==422


def test_exit_number_sql_always_includes_customer_and_omits_dates(monkeypatch):
    from contextlib import nullcontext
    from datetime import date
    from app import exit_db
    calls=[]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql,params): calls.append((sql,params))
        def fetchall(self): return []
    class Connection:
        def cursor(self): return Cursor()
    monkeypatch.setattr(exit_db,'connect_sqlserver',lambda: nullcontext(Connection()))
    monkeypatch.setattr(exit_db,'_columns',lambda connection,table,candidates: {key:key for key in candidates})
    assert exit_db.fetch_customer_exit_orders('CLIENT-A',date(2026,10,1),date(2026,10,29),order_number='6008375')==[]
    sql,params=calls[0]
    assert params==('CLIENT-A','6008375')
    assert 'BETWEEN' not in sql and 'h.[customer]' in sql and 'h.[number]' in sql
