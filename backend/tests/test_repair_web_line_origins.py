from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import Order, OrderItem, AuditEvent
from app.repair_web_line_origins import confirmed_targets, repair_confirmed_web_origins

bootstrap()


def prepare(db, target, extra=True):
    order=Order(order_number=target['web_number'],customer_code=target['customer_code'],company_code=1,delegation_code='00',origen_pedido='B2B',estado_registro_exit='REGISTRADO',exit_order_year=target['exit_year'],exit_series=target['exit_series'],exit_order_number=target['exit_number'],nro_pedido_exit=f"{target['exit_year']}/{target['exit_series']}/{target['exit_number']}")
    db.add(order);db.flush()
    for index,sku in enumerate(target['skus']+(['EXTRA-EXIT'] if extra else [])):
        db.add(OrderItem(order_id=order.id,sku=sku,description='Texto original',quantity=1,unit='UD',unit_price=5,tax_rate=21,line_total=5,created_in_web=False if index==1 else None,exit_removed_at=datetime(2026,11,1,tzinfo=timezone.utc) if index==0 else None,exit_entered_at=datetime(2026,11,1,tzinfo=timezone.utc),exit_line_number=str(index+1)))
    db.flush()
    return order


def target():
    return {'web_number':'WEB-ORIGIN-'+uuid4().hex[:16],'customer_code':'11264','exit_year':2026,'exit_series':'AL','exit_number':str(int(uuid4().hex[:7],16)),'skus':['23622','23493','23508','22498']}


def test_exact_six_confirmed_materials_are_listed():
    targets=confirmed_targets()
    assert [(row['web_number'],row['skus']) for row in targets]==[
        ('WEB-2026-0000321',['23622','23493','23508','22498']),
        ('WEB-2026-0000260',['21679','23538'])]


def test_preview_is_read_only_apply_changes_only_flags_and_audits_once():
    with SessionLocal() as db:
        expected=target();order=prepare(db,expected)
        rows=list(db.scalars(select(OrderItem).where(OrderItem.order_id==order.id).order_by(OrderItem.id)))
        before=[(row.id,row.sku,row.quantity,row.description,row.unit_price,row.exit_removed_at,row.exit_entered_at,row.exit_line_number) for row in rows]
        preview=repair_confirmed_web_origins(db,targets=[expected])
        assert len(preview['changed'])==4 and rows[0].created_in_web is None
        assert not db.scalars(select(AuditEvent).where(AuditEvent.entity_id.in_([str(row.id) for row in rows]))).all()
        report=repair_confirmed_web_origins(db,apply=True,targets=[expected]);db.commit()
        assert len(report['changed'])==4
        assert all(row.created_in_web is True for row in rows[:4])
        assert rows[4].created_in_web is None
        assert before==[(row.id,row.sku,row.quantity,row.description,row.unit_price,row.exit_removed_at,row.exit_entered_at,row.exit_line_number) for row in rows]
        assert repair_confirmed_web_origins(db,apply=True,targets=[expected])['changed']==[]
        events=db.scalars(select(AuditEvent).where(AuditEvent.action=='ORDER_LINE_WEB_ORIGIN_CONFIRMED',AuditEvent.entity_id.in_([str(row.id) for row in rows]))).all()
        assert len(events)==4


def test_other_customer_or_exit_key_or_non_web_order_is_not_changed():
    with SessionLocal() as db:
        expected=target();order=prepare(db,expected)
        for field,value in [('customer_code','OTHER'),('exit_series','OT'),('exit_order_number','OTHER'),('origen_pedido','EXIT')]:
            original=getattr(order,field);setattr(order,field,value)
            report=repair_confirmed_web_origins(db,apply=True,targets=[expected])
            assert report['changed']==[] and report['skipped']
            setattr(order,field,original)


def test_legacy_number_is_accepted_only_with_exact_web_order_and_customer():
    with SessionLocal() as db:
        expected=target();order=prepare(db,expected)
        order.exit_order_year=None;order.exit_series=None;order.exit_order_number=None
        order.nro_pedido_exit=expected['exit_number']
        assert len(repair_confirmed_web_origins(db,apply=True,targets=[expected])['changed'])==4


def test_duplicate_sku_is_not_arbitrarily_attributed_to_web():
    with SessionLocal() as db:
        expected=target();order=prepare(db,expected)
        db.add(OrderItem(order_id=order.id,sku=expected['skus'][0],description='Añadida en tienda',quantity=1,unit='UD',unit_price=1,tax_rate=21,line_total=1,created_in_web=False));db.flush()
        report=repair_confirmed_web_origins(db,apply=True,targets=[expected])
        assert len(report['changed'])==3
        assert report['skipped'][0]['sku']==expected['skus'][0]
        assert [row.created_in_web for row in db.scalars(select(OrderItem).where(OrderItem.order_id==order.id,OrderItem.sku==expected['skus'][0]))]==[None,False]
