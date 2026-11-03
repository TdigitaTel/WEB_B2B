from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app import order_pickups as service
from app.models import Order, OrderItem, User, OrderPickup, OrderPickupLine, OrderDeliveryNoteLine
from app.exit_orders import ExitOrderInput, ExitOrderLineInput

bootstrap()
pytestmark = pytest.mark.usefixtures('operator_with_almeiras_access')


def setup(monkeypatch, quantities=(10,), units=None):
    from app import main as module
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        customer = db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        order = Order(order_number='WEB-PICKUP-'+uuid4().hex[:16],user_id=customer.id,customer_code='CLI00001',company_code=actor.company_code,delegation_code=actor.delegation_code,origen_pedido='B2B',estado_registro_exit='ATENDIDO',exit_order_year=2026,exit_series='PU',exit_order_number=str(int(uuid4().hex[:8],16)))
        db.add(order);db.flush();order.nro_pedido_exit=f'2026/PU/{order.exit_order_number}'
        items=[]
        for index,qty in enumerate(quantities):
            row=OrderItem(order_id=order.id,sku=f'PICKUP-{index}',description=f'Material {index}',quantity=qty,unit=(units or ['UD']*len(quantities))[index],unit_price=1,tax_rate=21,line_total=qty,exit_line_number=str(index+1),created_in_web=True)
            db.add(row);db.flush();items.append(row)
        identity={'company_code':order.company_code,'exit_order_year':2026,'exit_series':'PU','exit_order_number':order.exit_order_number}
        record=ExitOrderInput(exit_order_id=order.nro_pedido_exit,order_number=order.nro_pedido_exit,exit_company_code=order.company_code,exit_order_year=2026,exit_series='PU',exit_order_number=order.exit_order_number,customer_code=order.customer_code,company_code=order.company_code,store_code=order.delegation_code,estado_registro_exit='ATENDIDO',source_updated_at=datetime.now(timezone.utc),lines=[ExitOrderLineInput(line_number=item.exit_line_number,sku=item.sku,description=item.description,quantity=item.quantity,unit=item.unit) for item in items])
        oid=order.public_id;ids=[item.id for item in items];db.commit()
    docs=[]
    monkeypatch.setattr(module,'fetch_customer_delivery_notes',lambda *a,**k:deepcopy(docs))
    monkeypatch.setattr(module,'fetch_exit_orders_live',lambda *a,**k:[record])
    client=TestClient(app);assert client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    note_offset=int(uuid4().hex[:8],16)
    def note(n, entries):
        return {**identity,'number':f'2026-AL-{note_offset+n}','status':'EMITIDO','items':[{'line':i+1,'sku':f'PICKUP-{sku}','description':f'Material {sku}','quantity':qty,'unit':(units or ['UD']*len(quantities))[sku]} for i,(sku,qty) in enumerate(entries)]}
    return client,oid,ids,docs,note,record


versions = {}

def detail(client,oid):
    response=client.get(f'/api/v1/store/orders/{oid}/pickups');assert response.status_code==200,response.text
    versions[(id(client),oid)] = response.json()["version"]
    return response.json()


def collect(client,oid,ids,request_id=None,**extra):
    response = client.post(f'/api/v1/store/orders/{oid}/pickups',json={'request_id':request_id or str(uuid4()),'expected_version':versions.get((id(client),oid),'0'*64),'line_ids':ids,**extra})
    if response.status_code == 200:
        versions[(id(client),oid)] = response.json()['version']
    return response


def available(data):
    return [line['id'] for doc in data['documents'] for line in doc['lines'] if line['can_collect']]


def test_complete_lifecycle_one_material_split_across_three_notes(monkeypatch):
    client,oid,ids,docs,note,record=setup(monkeypatch)
    assert detail(client,oid)['summary']['state']=='EN_PREPARACION'
    docs.append(note(1,[(0,4)]));data=detail(client,oid)
    assert data['summary']['state']=='PENDIENTE_RECOGIDA_PARCIAL'
    request_id=str(uuid4());first_ids=available(data)
    response=collect(client,oid,first_ids,request_id,observation='Primera recogida');assert response.status_code==200,response.text
    assert response.json()['summary']['state']=='ENTREGADO_PARCIAL'
    assert response.json()['summary']['delivered_materials']==0  # Four units do not complete a ten-unit material.
    assert response.json()['summary']['partial_delivered_materials']==1
    repeat=collect(client,oid,first_ids,request_id,observation='Primera recogida');assert repeat.status_code==200
    assert len(repeat.json()['history'])==1
    assert collect(client,oid,first_ids).status_code==409
    docs.append(note(2,[(0,3)]));data=detail(client,oid)
    assert data['summary']['state']=='PENDIENTE_RECOGIDA_PARCIAL'
    assert collect(client,oid,available(data)).json()['summary']['state']=='ENTREGADO_PARCIAL'
    docs.append(note(3,[(0,3)]));data=detail(client,oid)
    assert data['summary']['state']=='PENDIENTE_RECOGIDA_TOTAL'
    response=collect(client,oid,available(data));assert response.status_code==200,response.text
    assert response.json()['summary']['state']=='ENTREGADO_TOTAL'
    assert response.json()['summary']['delivered_percent']==100
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==oid))
        assert order.delivered_at and len(db.scalars(select(OrderPickup).where(OrderPickup.order_id==order.id)).all())==3
        assert len(db.scalars(select(OrderPickupLine).join(OrderPickup).where(OrderPickup.order_id==order.id)).all())==3
        assert service.summary(db,order)['lines'][0]['delivered_quantity']==10
        assert db.get(OrderItem,ids[0]).quantity==10
    # Refresh is idempotent; invoicing does not imply another physical collection.
    docs[0]['status']='FACTURADO';assert detail(client,oid)['summary']['state']=='ENTREGADO_TOTAL'


def test_select_whole_lines_not_quantities_deleted_items_excluded(monkeypatch):
    client,oid,ids,docs,note,record=setup(monkeypatch,(1,20,3),['UD','MT','UD'])
    docs.append(note(1,[(0,1),(1,20),(2,3)]))
    with SessionLocal() as db:
        db.get(OrderItem,ids[2]).exit_removed_at=datetime.now(timezone.utc);db.commit()
    record.lines=record.lines[:2]
    data=detail(client,oid);assert data['summary']['total_materials']==2
    lines=data['documents'][0]['lines'];assert not lines[2]['can_collect']
    first=collect(client,oid,[lines[0]['id']]);assert first.status_code==200,first.text
    assert first.json()['summary']['state']=='PENDIENTE_RECOGIDA_TOTAL'
    assert first.json()['summary']['delivered_percent']==50
    assert collect(client,oid,[lines[2]['id']]).status_code==409
    assert collect(client,oid,[lines[1]['id']]).json()['summary']['state']=='ENTREGADO_TOTAL'


def test_source_change_removal_and_outage_preserve_ledger(monkeypatch):
    from app import main as module
    client,oid,ids,docs,note,record=setup(monkeypatch,(2,1))
    docs.append(note(1,[(0,2),(1,1)]));data=detail(client,oid);line_ids=available(data)
    assert collect(client,oid,[line_ids[0]]).status_code==200
    docs[0]['items'][0]['quantity']=999
    data=detail(client,oid);assert data['summary']['requires_review']
    assert data['summary']['lines'][0]['delivered_quantity']==2
    docs.clear();data=detail(client,oid)
    assert not available(data);assert data['summary']['delivered_materials']==1
    def offline(*a,**k):raise RuntimeError('offline')
    monkeypatch.setattr(module,'fetch_customer_delivery_notes',offline)
    assert detail(client,oid)['warning']
    assert collect(client,oid,[line_ids[1]]).status_code==503
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==oid))
        assert len(service.detail(db,order)['history'])==1
        assert len(service.detail(db,order)['documents'][0]['lines'])==2


def test_permissions_full_order_key_ambiguity_and_pending_notes(monkeypatch):
    client,oid,ids,docs,note,record=setup(monkeypatch,(1,1))
    docs.append(note(1,[(0,1)]));docs[0]['company_code']+=100
    assert not detail(client,oid)['documents']
    docs[0]['company_code']-=100;docs[0]['status']='PENDIENTE_EMISION'
    assert not available(detail(client,oid))
    docs[0]['status']='EMITIDO'
    with SessionLocal() as db:
        db.get(OrderItem,ids[1]).sku='PICKUP-0';db.commit()
    data=detail(client,oid);assert data['documents'][0]['lines'][0]['warning'];assert not available(data)
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert customer.get(f'/api/v1/store/orders/{oid}/pickups').status_code==403
    assert collect(customer,oid,[1]).status_code==403
    assert TestClient(app).get(f'/api/v1/store/orders/{oid}/pickups').status_code==401
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==oid));order.company_code=999;db.commit()
    assert client.get(f'/api/v1/store/orders/{oid}/pickups').status_code==404


def test_stale_selection_oversupply_and_legacy_delivery_cannot_be_confirmed(monkeypatch):
    client,oid,ids,docs,note,record=setup(monkeypatch,(2,))
    docs.append(note(1,[(0,3)]));data=detail(client,oid)
    assert collect(client,oid,available(data)).status_code==409
    docs[0]['items'][0]['quantity']=2;data=detail(client,oid);old=available(data)
    docs.clear();assert collect(client,oid,old).status_code==409
    docs.append(note(1,[(0,2)]));detail(client,oid)
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==oid));order.delivered_at=datetime.now(timezone.utc);db.commit()
    data=detail(client,oid);assert data['summary']['legacy_delivery']
    assert collect(client,oid,old).status_code==409


def test_removed_exit_line_is_rechecked_at_confirmation(monkeypatch):
    client,oid,ids,docs,note,record=setup(monkeypatch)
    docs.append(note(1,[(0,10)]));old=available(detail(client,oid))
    record.lines=[]
    assert collect(client,oid,old).status_code==409
    with SessionLocal() as db:
        assert not db.scalars(select(OrderPickup).where(OrderPickup.order_id==db.get(OrderItem,ids[0]).order_id)).all()


def test_post_request_id_cannot_be_reused_for_different_lines(monkeypatch):
    client,oid,ids,docs,note,record=setup(monkeypatch,(1,1))
    docs.append(note(1,[(0,1),(1,1)]));data=detail(client,oid);lines=available(data);request_id=str(uuid4())
    assert collect(client,oid,[lines[0]],request_id).status_code==200
    assert collect(client,oid,[lines[1]],request_id).status_code==409


def test_changed_line_quantity_requires_new_confirmation_snapshot(monkeypatch):
    client,oid,ids,docs,note,record=setup(monkeypatch,(10,))
    docs.append(note(1,[(0,3)]));data=detail(client,oid);selection=available(data)
    docs[0]['items'][0]['quantity']=4
    response=collect(client,oid,selection)
    assert response.status_code==409 and 'cambiado' in response.text
    data=detail(client,oid)
    assert collect(client,oid,available(data)).status_code==200


def test_lists_filters_and_public_preview_without_writes(monkeypatch):
    from app import main as module, order_tracking as tracking
    from app.models import OrderDeliveryNote
    client,oid,ids,docs,note,record=setup(monkeypatch,(1,1))
    docs.append(note(1,[(0,1)]))
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *a,**k:[record])
    monkeypatch.setattr(tracking,'fetch_customer_exit_orders',lambda *a,**k:[record])
    monkeypatch.setattr(tracking,'fetch_delivery_statuses_for_orders',lambda *a,**k:[])
    monkeypatch.setattr(tracking,'fetch_customer_delivery_notes',lambda *a,**k:deepcopy(docs))
    link=client.post(f'/api/v1/store/orders/{oid}/tracking-link');assert link.status_code==200,link.text
    token=link.json()['path'].split('=',1)[1]
    public=TestClient(app).post('/api/v1/order-tracking/read',json={'token':token})
    assert public.status_code==200,public.text
    assert public.json()['pickup_summary']['state']=='PENDIENTE_RECOGIDA_PARCIAL'
    assert 'history' not in public.json() and 'observation' not in public.text and 'confirmed_by' not in public.text
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==oid))
        assert order.pickup_managed_at is None
        assert not db.scalars(select(OrderDeliveryNote).where(OrderDeliveryNote.order_id==order.id)).all()
    data=detail(client,oid);assert collect(client,oid,available(data)).status_code==200
    response=client.get('/api/v1/store/orders?view=web&delegation=TODAS&state=ENTREGADO_PARCIAL')
    assert response.status_code==200,response.text
    row=next(row for row in response.json() if row['id']==oid)
    assert row['pickup_summary']['state']=='ENTREGADO_PARCIAL'
    assert row['delivered_at'] is None
    docs.append(note(2,[(1,1)]))
    response=client.get('/api/v1/store/orders?view=web&delegation=TODAS&state=PENDIENTE_RECOGIDA_TOTAL')
    assert response.status_code==200,response.text
    assert any(row['id']==oid for row in response.json())
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    response=customer.get('/api/v1/orders?state=PENDIENTE_RECOGIDA_TOTAL&date_from=2026-01-01&date_to=2027-12-31')
    assert response.status_code==200,response.text
    assert any(row['id']==oid for row in response.json())


def test_cannot_unlink_or_change_exit_identity_after_partial_pickup(monkeypatch):
    from app.exit_order_key import apply_key
    from fastapi import HTTPException
    client,oid,ids,docs,note,record=setup(monkeypatch,(1,1))
    docs.append(note(1,[(0,1)]));data=detail(client,oid)
    assert collect(client,oid,available(data)).status_code==200
    response=client.patch(f'/api/v1/store/orders/{oid}/registration',json={'state':'PENDIENTE'})
    assert response.status_code==409
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==oid))
        assert service.has_pickups(db,order)
        assert service.receipt_order_keys(db,[order])
        with pytest.raises(HTTPException,match='llave EXIT'):
            apply_key(db,order,{'exit_order_number':'999999999'})


def test_albaran_detail_sql_uses_four_parameterized_order_fields(monkeypatch):
    from app import erp_db
    calls=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):calls.append((sql,params))
        def fetchall(self):return []
    class Connection(Cursor):
        def cursor(self):return Cursor()
    monkeypatch.setattr(erp_db,'connect_sqlserver',lambda:Connection())
    key=(1,2026,"AL'",'6008552')
    assert erp_db.fetch_customer_delivery_notes('CLI',1000,order_keys=[key])==[]
    assert len(calls)==2
    for sql,params in calls:
        assert 'a.CodigoEmpresa=%s AND a.EjercicioPedido=%s' in sql
        assert 'a.NumeroPedido=%s' in sql and "AL'" not in sql
        assert tuple(params[-4:])==key


def test_new_preparation_after_complete_collection_reopens_without_losing_history(monkeypatch):
    client,oid,ids,docs,note,record=setup(monkeypatch,(1,1))
    original_lines=record.lines.copy();record.lines=record.lines[:1]
    with SessionLocal() as db:
        db.get(OrderItem,ids[1]).exit_removed_at=datetime.now(timezone.utc);db.commit()
    docs.append(note(1,[(0,1)]));data=detail(client,oid)
    assert collect(client,oid,available(data)).json()['summary']['state']=='ENTREGADO_TOTAL'
    with SessionLocal() as db:
        assert db.scalar(select(Order).where(Order.public_id==oid)).delivered_at
        db.get(OrderItem,ids[1]).exit_removed_at=None;db.commit()
    record.lines=original_lines;docs.append(note(2,[(1,1)]));data=detail(client,oid)
    assert data['summary']['state']=='PENDIENTE_RECOGIDA_TOTAL'
    assert len(data['history'])==1
    with SessionLocal() as db:
        assert db.scalar(select(Order).where(Order.public_id==oid)).delivered_at is None
    assert collect(client,oid,available(data)).json()['summary']['state']=='ENTREGADO_TOTAL'
    assert len(detail(client,oid)['history'])==2
