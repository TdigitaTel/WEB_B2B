from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import (Order,OrderItem,OrderStatusHistory,User,OrderDeliveryNote,
                        OrderDeliveryNoteLine,OrderPickup,OrderPickupLine,AuditEvent)
from app.repair_historical_pickup import repair_confirmed_historical_pickup as repair, utc
from app.order_pickups import summary, refresh_documents
bootstrap()
STAMP=datetime(2026,10,26,15,38,47,tzinfo=timezone.utc)


def prepare(db):
    actor=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
    order=Order(order_number='WEB-2026-0000260',customer_code='11264',company_code=1,delegation_code='00',origen_pedido='B2B',estado_registro_exit='FACTURADO',exit_order_year=2026,exit_series='AL',exit_order_number='6007768',nro_pedido_exit='6007768',delivered_at=STAMP,pickup_managed_at=datetime.now(timezone.utc))
    db.add(order);db.flush()
    history=OrderStatusHistory(order_id=order.id,estado_registro_exit='ENTREGADO',source='WEB',changed_by_user_id=actor.id,created_at=STAMP,note='Entrega confirmada en Operaciones')
    db.add(history)
    note=OrderDeliveryNote(order_id=order.id,company_code=1,year=2026,series='AL',number='682017735',status='FACTURADO',current=True,synced_at=datetime.now(timezone.utc));db.add(note);db.flush()
    rows=[]
    for line,sku in [('5','21679'),('10','23538')]:
        item=OrderItem(order_id=order.id,sku=sku,description='Original',quantity=1,unit='UD',unit_price=1,tax_rate=21,line_total=1)
        db.add(item);db.flush()
        row=OrderDeliveryNoteLine(delivery_note_id=note.id,line_number=line,order_item_id=item.id,sku=sku,description='Original',unit='UD',quantity=1,current=True)
        db.add(row);rows.append(row)
    db.flush();return order,actor,history,note,rows


def test_preview_and_apply_keep_original_time_actor_and_invoice():
    with SessionLocal() as db:
        order,actor,history,note,rows=prepare(db)
        assert summary(db,order)['legacy_delivery'] is True
        assert repair(db)['status']=='ready'
        assert db.scalar(select(func.count()).select_from(OrderPickup).where(OrderPickup.order_id==order.id))==0
        assert repair(db,apply=True)['status']=='applied'
        result=summary(db,order)
        assert result['state']=='ENTREGADO_TOTAL' and result['delivered_percent']==100
        assert result['legacy_delivery'] is False and result['ready_materials']==0 and result['pending_materials']==0
        assert utc(result['completed_at'])==STAMP
        event=db.scalar(select(OrderPickup).where(OrderPickup.order_id==order.id))
        assert event.confirmed_by==actor.id and utc(event.confirmed_at)==STAMP
        assert utc(order.delivered_at)==STAMP and order.estado_registro_exit=='FACTURADO'
        assert history.note=='Entrega confirmada en Operaciones'
        assert len(db.scalars(select(OrderPickupLine).where(OrderPickupLine.pickup_id==event.id)).all())==2
        assert repair(db,apply=True)['status']=='already_recorded'
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.action=='HISTORICAL_PICKUP_REGULARIZED',AuditEvent.entity_id==order.public_id)).all())==1


@pytest.mark.parametrize('mutation',[
    'customer','company','year','series','number','web_number','no_date','wrong_date',
    'no_actor','wrong_actor_date','wrong_note','removed_note','removed_line','wrong_quantity',
    'wrong_unit','ambiguous_sku','line_warning','missing_line','existing_pickup',
])
def test_other_or_ambiguous_cases_are_not_delivered(mutation):
    with SessionLocal() as db:
        order,actor,history,note,rows=prepare(db)
        if mutation=='customer':order.customer_code='OTHER'
        if mutation=='company':order.company_code=2
        if mutation=='year':order.exit_order_year=2025
        if mutation=='series':order.exit_series='OT'
        if mutation=='number':order.exit_order_number='OTHER'
        if mutation=='web_number':order.order_number='WEB-OTHER'
        if mutation=='no_date':order.delivered_at=None
        if mutation=='wrong_date':order.delivered_at=datetime.now(timezone.utc)
        if mutation=='no_actor':history.changed_by_user_id=None
        if mutation=='wrong_actor_date':history.created_at=datetime.now(timezone.utc)
        if mutation=='wrong_note':note.number='OTHER'
        if mutation=='removed_note':note.current=False
        if mutation=='removed_line':rows[0].current=False
        if mutation=='wrong_quantity':rows[0].quantity=2
        if mutation=='wrong_unit':rows[0].unit='MT'
        if mutation=='ambiguous_sku':rows[0].sku='23538'
        if mutation=='line_warning':rows[0].warning='Revisar'
        if mutation=='missing_line':db.delete(rows[0])
        if mutation=='existing_pickup':db.add(OrderPickup(order_id=order.id,request_id=str(uuid4()),confirmed_by=actor.id,confirmed_at=STAMP))
        db.flush()
        assert repair(db,apply=True)['status'] in {'skipped','absent'}
        assert not db.scalars(select(OrderPickupLine).join(OrderPickup).where(OrderPickup.order_id==order.id)).all()


def test_normal_refresh_keeps_regularized_delivery():
    with SessionLocal() as db:
        order,actor,history,note,rows=prepare(db);repair(db,apply=True)
        doc={'company_code':1,'exit_order_year':2026,'exit_series':'AL','exit_order_number':'6007768','number':'2026/AL/682017735','status':'FACTURADO','items':[{'line':row.line_number,'sku':row.sku,'description':row.description,'unit':'UD','quantity':1} for row in rows]}
        assert not refresh_documents(db,[order],lambda *a,**k:[doc])
        assert summary(db,order)['state']=='ENTREGADO_TOTAL'
        assert utc(order.delivered_at)==STAMP
