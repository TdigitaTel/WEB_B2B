from contextlib import contextmanager
from datetime import date
from copy import deepcopy
import re
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import erp_db, delivery_labels as module
from app.delivery_label_pdf import generate_pdf
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import User, OperatorAccess

bootstrap()


def note():
    return {'id':'1:2026~AL~123', 'company_code':1,'year':2026,'series':'AL','document_number':'123',
            'number':'2026-AL-123','created_at':date(2026,11,27),'store_code':'00','store_name':'Almeiras',
            'customer_code':'CLI1','customer_name':'Cliente de prueba','customer_address':'Calle de prueba 1',
            'exit_order_year':2026,'exit_series':'PV','exit_order_number':'88','order_date':date(2026,11,26),
            'order_number':'2026~PV~88','total':100,'subtotal':80,
            'items':[{'line':n,'sku':f'0328{n}','description':'TE LATÓN HEMBRA','quantity':float(n), 'unit':'UD',
                      'dispatch_delegation':'Almeiras','unit_price':12,'total':12} for n in range(1,5)]}


def test_query_scope_dates_company_series_pagination_and_parameterization(monkeypatch):
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):statements.append((sql,params))
        def fetchall(self):
            if len(statements)==1:return [{'COLUMN_NAME':'RazonSocial'}]
            return []
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    monkeypatch.setattr(erp_db,'connect_sqlserver',connect)
    assert erp_db.fetch_customer_delivery_notes(None,26,"123'",date(2026,1,1),date(2026,11,27),delegation_keys=[(1,'00'),(2,'00')],offset=25)==[]
    header,lines=statements[1:]
    assert header[1][:4]==(1,'00',2,'00')
    assert header[1]==lines[1]
    for sql,_ in (header,lines):
        assert 'a.CodigoEmpresa=%s' in sql and 'a.IdDelegacion' in sql
        assert 'OFFSET 25 ROWS FETCH NEXT 26 ROWS ONLY' in sql
        assert 'DATEADD(day, 1, %s)' in sql and "123'" not in sql
    assert 's.SerieAlbaran=l.SerieAlbaran' in lines[0]
    assert 's.CodigoEmpresa=l.CodigoEmpresa' in lines[0]
    assert 'p.SeriePedido=a.SeriePedido' in header[0]
    assert erp_db.fetch_customer_delivery_notes(None,delegation_keys=[])==[]
    statements.clear()
    erp_db.fetch_customer_delivery_notes(None,1,delegation_keys=[(1,'00')],document_key=(1,2026,'',123))
    assert statements[1][1]==(1,'00',1,2026,'',123)
    assert 'LTRIM(RTRIM(a.SerieAlbaran))=%s' in statements[1][0]


@pytest.fixture
def staff(monkeypatch):
    from app.auth import current_user, hash_password
    with SessionLocal() as db:
        user=User(email='labelstaff@test.local',full_name='Etiquetas',role='OPERADOR_TIENDA',password_hash=hash_password('test1234'),active=True,company_code=1,delegation_code='00')
        db.add(user);db.flush();db.add(OperatorAccess(user_id=user.id,exit_code='labelstaff',permissions={'labels':True,'delegation_ids':['1:02']}));db.commit();db.refresh(user);uid=user.id
    from app.delegations import Delegation
    stores=[Delegation(1,'00','Almeiras','','00',''),Delegation(1,'02','Ferrol','','02',''),Delegation(2,'00','Otra empresa','','00',''),Delegation(1,'04','Santiago','','04','')]
    monkeypatch.setattr(module,'fetch_delegations',lambda:stores)
    def identity():
        with SessionLocal() as db:return db.get(User,uid)
    app.dependency_overrides[current_user]=identity
    yield TestClient(app),uid
    app.dependency_overrides.pop(current_user,None)
    from app.models import LabelPrinterPreference, AuditEvent
    from sqlalchemy import delete
    with SessionLocal() as db:
        db.execute(delete(LabelPrinterPreference).where(LabelPrinterPreference.user_id==uid))
        db.execute(delete(AuditEvent).where(AuditEvent.user_id==uid))
        db.execute(delete(OperatorAccess).where(OperatorAccess.user_id==uid))
        db.execute(delete(User).where(User.id==uid));db.commit()


def test_listing_and_print_are_scoped_and_prices_not_exposed(staff,monkeypatch):
    client,uid=staff
    calls=[]
    def fetch(*a,**kw):
        calls.append(kw)
        if kw.get('document_key')==(2,2026,'AL',123):return []
        return [note()]
    monkeypatch.setattr(module,'fetch_customer_delivery_notes',fetch)
    monkeypatch.setattr(module,'fetch_product_image',lambda sku:None)
    response=client.get('/api/v1/store/delivery-labels')
    assert response.status_code==200,response.text
    body=response.json()
    assert calls[-1]['delegation_keys']==[(1,'00'),(1,'02')]
    assert len(body['delegations'])==2
    assert 'total' not in body['items'][0] and 'unit_price' not in body['items'][0]['items'][0]
    assert client.get('/api/v1/store/delivery-labels?delegation=2:00').status_code==403
    payload={'documents':[{'company':1,'year':2026,'series':'AL','number':123,'detail':True,'packing':True,'quantities':{'1':2,'2':0}}]}
    response=client.post('/api/v1/store/delivery-labels/pdf',json=payload)
    assert response.status_code==200,response.text
    assert response.headers['x-label-count']=='6'  # 4 details + 2 packing sheets
    assert len(re.findall(rb'/Type /Page\b',response.content))==6
    assert calls[-1]['document_key']==(1,2026,'AL',123)
    assert calls[-1]['delegation_keys']==[(1,'00'),(1,'02')]
    payload['documents'][0]['company']=2
    assert client.post('/api/v1/store/delivery-labels/pdf',json=payload).status_code==404
    payload['documents'][0]['company']=1;payload['documents'][0]['quantities']={'999':1}
    assert client.post('/api/v1/store/delivery-labels/pdf',json=payload).status_code==409
    assert client.get('/api/v1/store/delivery-labels?date_from=2026-11-27&date_to=2026-01-01').status_code==422


def test_preferences_are_user_private(staff):
    client,uid=staff
    assert client.put('/api/v1/store/delivery-labels/preferences',json={'printer_name':'Zebra local','dpi':203}).status_code==200
    assert client.get('/api/v1/store/delivery-labels/preferences').json()['printer_name']=='Zebra local'
    assert client.put('/api/v1/store/delivery-labels/preferences',json={'printer_name':'test','dpi':72}).status_code==422
    from app.models import LabelPrinterPreference
    with SessionLocal() as db:
        assert db.get(LabelPrinterPreference,uid).printer_name=='Zebra local'


def test_module_denied_on_every_endpoint(monkeypatch):
    # Exercise the real login + current_user path guard (no dependency override).
    from app.auth import hash_password
    with SessionLocal() as db:
        user=User(email='nolabels@test.local',full_name='Sin permiso',role='OPERADOR_TIENDA',password_hash=hash_password('test1234'),active=True)
        db.add(user);db.flush();db.add(OperatorAccess(user_id=user.id,exit_code='nolabels',permissions={'orders':True}));db.commit()
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':'nolabels@test.local','password':'test1234'}).status_code==200
    for path in ('','/preferences'):
        assert client.get('/api/v1/store/delivery-labels'+path).status_code==403
    assert client.post('/api/v1/store/delivery-labels/pdf',json={'documents':[]}).status_code==403
    assert client.put('/api/v1/store/delivery-labels/preferences',json={}).status_code==403


def test_pdf_modes_copies_and_packing_continuations():
    n=note()
    for detail,packing,count in [(True,False,4),(False,True,2),(True,True,6)]:
        pdf=generate_pdf([(n,detail,packing,{})])
        assert len(re.findall(rb'/Type /Page\b',pdf))==count
        assert pdf.startswith(b'%PDF')
    with pytest.raises(ValueError):
        n['items'][0]['sku']='á';generate_pdf([(n,True,False,{})])


def test_full_number_filter_retains_empty_series_and_hyphens():
    for value, series in [('2026//123', ''), ('2026/AL/123', 'AL'), ('2026~AL-B~123', 'AL-B')]:
        sql, params = erp_db._document_filters('a', 'Albaran', value)
        assert params == ['2026', series, '123']
        assert 'SerieAlbaran' in sql


def test_material_thumbnail_is_embedded_without_serial_number():
    from PIL import Image
    from io import BytesIO
    image=BytesIO()
    Image.new('RGB',(32,32),'white').save(image,format='PNG')
    n=note();n['items']=n['items'][:1]
    pdf=generate_pdf([(n,True,False,{})],{n['items'][0]['sku']:image.getvalue()})
    assert b'/Subtype /Image' in pdf
    assert len(re.findall(rb'/Type /Page\b',pdf))==1
