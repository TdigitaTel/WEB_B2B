from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.bootstrap import main as bootstrap
from app.main import app
from app.line_planning import next_open,transfer_date,TZ
bootstrap()

def schedule():
    return [{'enabled':i<6,'morning_from':'08:00','morning_to':'12:00' if i==5 else '14:00','afternoon_from':'16:00' if i<5 else None,'afternoon_to':'19:00' if i<5 else None} for i in range(7)]

def test_working_dates_respect_saturday_half_day_and_sunday():
    hours=schedule()
    assert next_open(datetime(2026,10,31,13,tzinfo=TZ),hours)==datetime(2026,11,2,8,tzinfo=TZ)
    assert transfer_date(datetime(2026,10,30,10,tzinfo=TZ),1,hours)==datetime(2026,10,31,10,tzinfo=TZ)
    assert transfer_date(datetime(2026,10,30,13,tzinfo=TZ),1,hours)==datetime(2026,11,2,8,tzinfo=TZ)
    assert next_open(datetime.now(TZ),None) is None

def test_plan_stock_transfer_supplier_manual_and_conflict(monkeypatch):
    import app.line_planning as module
    from app.db import SessionLocal
    from app.models import PickupSettings,OrderLinePlanning
    lines=[{'line_key':str(i),'sku':sku,'description':sku,'quantity':2,'pending':2} for i,sku in enumerate(['LOCAL','TRANSFER','SUPPLIER','UNKNOWN'])]
    deadline=datetime(2030,10,25,10,tzinfo=TZ)
    monkeypatch.setattr(module,'resolve',lambda *a:('TEST:PLAN',1,'00',deadline,lines))
    monkeypatch.setattr(module,'source',lambda codes:({('LOCAL','00'):2,('TRANSFER','01'):4},{'SUPPLIER':3}))
    with SessionLocal() as db:
        config=db.get(PickupSettings,1)
        if config is None:
            config=PickupSettings(id=1,preparation_minutes=60,schedules={});db.add(config)
        original=config.schedules
        config.schedules={**(original or {}),'1:00':schedule()};db.commit()
    client=TestClient(app);assert client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    path='/api/v1/store/orders/line-planning?order_id=test'
    context=('TEST:PLAN',1,'00',deadline,lines)
    try:
        with SessionLocal() as db:
            assert module.initialize_context(db,context)
            db.commit()
        response=client.get(path)
        assert response.status_code==200,response.text
        data=response.json();assert [r['status'] for r in data['lines']]==['EN_STOCK','TRASLADO','PROVEEDOR','REVISAR']
        assert data['lines'][0]['expected_at']==deadline.isoformat()
        body={'line_key':'1','sku':'TRANSFER','version':data['version'],'status':'PROVEEDOR','expected_at':'2030-11-01T10:00:00+01:00','observation':'Confirmado por proveedor'}
        saved=client.patch(path,json=body);assert saved.status_code==200,saved.text
        assert client.patch(path,json=body).status_code==409
        with SessionLocal() as db:
            assert not module.initialize_context(db,context)
        recalculated=client.get(path).json()
        assert recalculated['lines'][1]['manual'] and recalculated['lines'][1]['observation']==body['observation']
        assert client.patch(path,json={**body,'version':recalculated['version'],'sku':'WRONG'}).status_code==409
        monkeypatch.setattr(module,'source',lambda codes:(_ for _ in ()).throw(RuntimeError('offline')))
        stored=client.get('/api/v1/store/orders/line-planning/preview?order_id=test').json()
        assert stored['lines'][0]['status']=='EN_STOCK' and stored['lines'][1]['manual']
        assert client.post('/api/v1/store/orders/line-planning/calculate?order_id=test').status_code in (404,405)
        with SessionLocal() as db:
            context_missing=('TEST:OFFLINE',1,'00',deadline,lines)
            assert module.initialize_context(db,context_missing)
            assert module.payload(db,'TEST:OFFLINE',lines)['lines'][0]['status']=='REVISAR'
            db.rollback()
    finally:
        with SessionLocal() as db:
            db.get(PickupSettings,1).schedules=original
            row=db.get(OrderLinePlanning,'TEST:PLAN')
            if row:db.delete(row)
            db.commit()


def test_customer_preview_is_scoped_read_only_and_reuses_manual_plan(monkeypatch):
    import app.line_planning as module
    from app.db import SessionLocal
    from app.models import Order,OrderItem,User,OrderLinePlanning
    from sqlalchemy import select
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        order=Order(order_number='WEB-LINE-PUBLIC',customer_id=user.customer_id,user_id=user.id,customer_code='CLI00001',company_code=1,delegation_code='00',attention_deadline_at=datetime(2030,10,25,10,tzinfo=TZ))
        db.add(order);db.flush();oid=order.public_id
        item=OrderItem(order_id=order.id,sku='PUBLIC',description='Material',quantity=1,unit='UD',unit_price=1,tax_rate=21,line_total=1)
        db.add(item);db.flush();line_key=str(item.id);db.commit()
    monkeypatch.setattr(module,'source',lambda codes:({('PUBLIC','00'):4},{'PUBLIC':2}))
    owner=TestClient(app);other=TestClient(app)
    assert owner.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    assert other.post('/api/v1/auth/login',json={'email':'compras002@cliente.test','password':'123456'}).status_code==200
    url=f'/api/v1/orders/{oid}/line-planning'
    try:
        result=owner.get(url);assert result.status_code==200,result.text
        assert 'status' not in result.json()['lines'][0]
        with SessionLocal() as db:
            order=db.scalar(select(Order).where(Order.public_id==oid))
            assert module.initialize_order(db,order)
            db.commit()
        result=owner.get(url)
        assert result.json()['lines'][0]['status']=='EN_STOCK'
        assert result.json()['lines'][0]['local_available']==4
        assert other.get(url).status_code==404
        assert owner.patch('/api/v1/store/orders/line-planning',params={'order_id':oid},json={}).status_code==403
        with SessionLocal() as db:
            plan=db.get(OrderLinePlanning,'WEB:'+oid)
            plan.lines={line_key:{'sku':'PUBLIC','status':'TRASLADO','expected_at':'2030-10-26T10:00:00+02:00','observation':'Traslado confirmado','manual':True},'_version':1};db.commit()
        monkeypatch.setattr(module,'source',lambda codes:(_ for _ in ()).throw(AssertionError('Should reuse saved plan')))
        assert owner.get(url).json()['lines'][0]['observation']=='Traslado confirmado'
    finally:
        with SessionLocal() as db:
            plan=db.get(OrderLinePlanning,'WEB:'+oid)
            if plan:db.delete(plan)
            db.delete(db.scalar(select(OrderItem).where(OrderItem.order_id==order.id)))
            db.delete(db.get(Order,order.id));db.commit()
