from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from app.bootstrap import main as bootstrap
from app.main import app
from app import main as main_module, sales_order_series as module
from app.auth import hash_password
from app.db import SessionLocal
from app.delegations import Delegation
from app.models import SalesOrderSeriesAssignment as Assignment, User, OperatorAccess, AuthSession, AuditEvent

bootstrap()
PREFIX='/api/v1/store/sales-order-series'

@pytest.fixture
def series(monkeypatch):
    rows=[{'company_code':company,'series_code':code,'document_type':'PedV','description':f'Pedidos {company} {code}'} for company,code in [(1,'WEB'),(1,'ALT'),(1,''),(2,'WEB')]]
    seats=[Delegation(company,code,name,'','','') for company,code,name in [(1,'00','Almeiras'),(1,'02','Ferrol'),(2,'00','Otra empresa')]]
    monkeypatch.setattr(module,'fetch_sales_order_series',lambda:rows)
    monkeypatch.setattr(module,'fetch_delegations',lambda:seats)
    return rows,seats

@pytest.fixture
def manager(series):
    with SessionLocal() as db:
        user=User(email='series-admin@test.invalid',full_name='Administrador de series',role='ADMIN',active=True,password_hash=hash_password('series-test123'))
        db.add(user);db.commit();uid=user.id
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':'series-admin@test.invalid','password':'series-test123'}).status_code==200
    yield client
    with SessionLocal() as db:
        db.execute(delete(Assignment));db.execute(delete(AuditEvent).where(AuditEvent.user_id==uid))
        db.execute(delete(AuthSession).where(AuthSession.user_id==uid));db.execute(delete(User).where(User.id==uid));db.commit()


def data(company=1,delegation='00',series='WEB',active=True):
    return {'company_code':company,'delegation_code':delegation,'series_code':series,'active':active}


def save(client,**kwargs):
    response=client.put(PREFIX+'/assignments',json=data(**kwargs))
    assert response.status_code==200,response.text
    return response.json()


def active(client,company=1,delegation='00'):
    return client.get(PREFIX+'/active',params={'company_code':company,'delegation_code':delegation})


def test_interface_options_mapping_and_atomic_switch_in_both_directions(manager):
    options=manager.get(PREFIX+'/options').json()
    assert len(options['series'])==4 and options['document_type']=='PedV'
    assert options['delegations'][0]['code']=='00'
    first=save(manager)
    assert save(manager)['id']==first['id']  # saving the same association must not duplicate it
    second=save(manager,series='ALT')
    assert active(manager).json()['series_code']=='ALT'
    rows=manager.get(PREFIX+'/assignments').json()
    assert len(rows)==2 and sum(row['active'] for row in rows)==1
    old=next(row for row in rows if row['id']==first['id'])
    changed=manager.patch(f"{PREFIX}/assignments/{first['id']}",json={'active':True,'expected_version':old['version']})
    assert changed.status_code==200,changed.text
    assert active(manager).json()['series_code']=='WEB'  # activating the older PK must release the newer active row first
    assert manager.patch(f"{PREFIX}/assignments/{second['id']}",json={'active':False,'expected_version':second['version']}).status_code==409
    with SessionLocal() as db:
        row=db.get(Assignment,first['id'])
        assert row.company_code==1 and row.delegation_code=='00' and ':' not in row.delegation_code
        assert db.scalar(select(AuditEvent).where(AuditEvent.action=='SALES_ORDER_SERIES_STATE_CHANGED')) is not None


def test_company_delegation_isolation_inactive_and_missing_configuration(manager):
    save(manager)
    save(manager,company=2)
    save(manager,delegation='02',series='ALT')
    assert active(manager,2).json()['series_code']=='WEB'
    assert active(manager,1,'02').json()['series_code']=='ALT'
    inactive=save(manager,series='ALT',active=False)
    assert active(manager).json()['series_code']=='WEB'
    assert len(manager.get(PREFIX+'/assignments?company_code=2').json())==1
    current=active(manager).json()
    assert manager.patch(f"{PREFIX}/assignments/{current['id']}",json={'active':False,'expected_version':current['version']}).status_code==200
    assert active(manager).status_code==404
    assert active(manager,2).status_code==200
    assert inactive['active'] is False


def test_rejects_invalid_delegation_and_series_from_another_company(manager):
    for patch in [data(delegation='1:00'),data(delegation='0'),data(delegation='AL'),data(delegation='99'),data(company=2,series='ALT'),data(series='NOT-IN-EXIT')]:
        assert manager.put(PREFIX+'/assignments',json=patch).status_code==422
    customer=TestClient(app)
    assert customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    assert customer.get(PREFIX+'/options').status_code==403
    assert active(customer).status_code==403
    assert manager.get(PREFIX+'/assignments').json()==[]
    blank=save(manager,series='')
    assert blank['series_code']=='' and active(manager).json()['series_code']==''


def test_database_constraint_prevents_two_active_series_even_outside_api(manager):
    save(manager)
    with SessionLocal() as db:
        db.add(Assignment(company_code=1,delegation_code='00',document_type='PedV',series_code='MANUAL',active=True))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
    assert active(manager).json()['series_code']=='WEB'


def test_saved_api_still_works_when_exit_is_down_and_deactivation_is_allowed(manager,monkeypatch):
    saved=save(manager)
    def unavailable():raise RuntimeError('secret connection detail')
    monkeypatch.setattr(module,'fetch_sales_order_series',unavailable)
    monkeypatch.setattr(module,'fetch_delegations',unavailable)
    assert active(manager).status_code==200
    assert manager.get(PREFIX+'/assignments').status_code==200
    failed=manager.get(PREFIX+'/options')
    assert failed.status_code==503 and 'secret connection' not in failed.text
    result=manager.patch(f"{PREFIX}/assignments/{saved['id']}",json={'active':False,'expected_version':saved['version']})
    assert result.status_code==200
    assert manager.patch(f"{PREFIX}/assignments/{saved['id']}",json={'active':True,'expected_version':result.json()['version']}).status_code==503
    assert active(manager).status_code==404


def test_lookup_integration_key_and_no_exit_dependency(manager,monkeypatch):
    save(manager)
    monkeypatch.setattr(main_module.settings,'integration_api_key','series-integration-test-key')
    path='/api/v1/integrations/sales-order-series/active?company_code=1&delegation_code=00'
    external=TestClient(app)
    assert external.get(path).status_code==401
    assert external.get(path,headers={'X-Integration-Key':'wrong'}).status_code==401
    def no_exit():raise AssertionError('A stored lookup must not call EXIT')
    monkeypatch.setattr(module,'fetch_sales_order_series',no_exit);monkeypatch.setattr(module,'fetch_delegations',no_exit)
    response=external.get(path,headers={'X-Integration-Key':'series-integration-test-key'})
    assert response.status_code==200 and response.json()['series_code']=='WEB'
    assert 'no-store' in response.headers['cache-control']
    assert external.get(path.replace('00','02'),headers={'X-Integration-Key':'series-integration-test-key'}).status_code==404
    monkeypatch.setattr(main_module.settings,'integration_api_key','')
    assert external.get(path).status_code==503


def test_operator_scope_and_module_permissions(manager,monkeypatch):
    save(manager);save(manager,company=2)
    with SessionLocal() as db:
        user=User(email='series-operator@test.invalid',full_name='Operador limitado',role='OPERADOR_TIENDA',company_code=1,delegation_code='00',active=True,password_hash=hash_password('series-op123'))
        db.add(user);db.flush();uid=user.id
        db.add(OperatorAccess(user_id=uid,exit_code='SERIES-SCOPE-TEST',permissions={'orders':True}));db.commit()
    client=TestClient(app)
    try:
        assert client.post('/api/v1/auth/login',json={'email':'series-operator@test.invalid','password':'series-op123'}).status_code==200
        assert active(client).status_code==200
        assert active(client,2).status_code==403
        assert client.get(PREFIX+'/options').status_code==403
        assert client.get(PREFIX+'/assignments').status_code==403
        assert client.put(PREFIX+'/assignments',json=data()).status_code==403
        with SessionLocal() as db:
            link=db.get(OperatorAccess,uid);link.permissions={'settings':True};db.commit()
        assert active(client).status_code==200
        assert active(client,2).status_code==403
        options=client.get(PREFIX+'/options').json()
        assert {row['company_code'] for row in options['series']}=={1}
        assert [(row['company_code'],row['code']) for row in options['delegations']]==[(1,'00')]
        assert len(client.get(PREFIX+'/assignments').json())==1
        assert client.put(PREFIX+'/assignments',json=data(company=2)).status_code==403
        with SessionLocal() as db:
            link=db.get(OperatorAccess,uid);link.permissions={'orders':False,'settings':False};db.commit()
        assert active(client).status_code==403
    finally:
        with SessionLocal() as db:
            db.execute(delete(OperatorAccess).where(OperatorAccess.user_id==uid));db.execute(delete(AuthSession).where(AuthSession.user_id==uid))
            db.execute(delete(AuditEvent).where(AuditEvent.user_id==uid));db.execute(delete(User).where(User.id==uid));db.commit()


def test_exit_query_uses_only_supplied_fields_and_read_only_statement(monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection
    cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value=[{'company_code':1,'series_code':' 001 ','document_type':'PedV','description':' Web '}]
    monkeypatch.setattr(module,'connect_sqlserver',lambda:connection)
    rows=module.fetch_sales_order_series()
    sql,params=cursor.execute.call_args.args
    assert params==('PedV',) and 'FROM Series s WHERE s.TipoDocumento = %s' in sql
    for name in ('s.CodigoEmpresa','s.serie','s.TipoDocumento','s.DescripcionSerie'):assert name in sql
    assert 'SELECT' in sql and 'UPDATE' not in sql and 'INSERT' not in sql
    assert rows==[{'company_code':1,'series_code':'001','document_type':'PedV','description':'Web'}]
