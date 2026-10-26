from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import User, OperatorAccess, AuthSession, AuditEvent
from app.auth import verify_password, hash_password
from app import operator_access as module, exit_users
from app.operator_permissions import MODULES

bootstrap()


def manager():
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    return client

@pytest.fixture
def staff(monkeypatch):
    rows=[{'code':'MC-TEST-'+str(i),'username':'staff-test-'+str(i),'name':'Persona '+str(i)} for i in range(30)]
    monkeypatch.setattr(module,'fetch_exit_user',lambda code:next((row for row in rows if row['code']==code),None))
    monkeypatch.setattr(module,'fetch_exit_users',lambda q='',page=1,page_size=25:{'items':[row for row in rows if q.lower() in str(row).lower()][(page-1)*page_size:page*page_size],'total':len([row for row in rows if q.lower() in str(row).lower()])})
    from app.delegations import fetch_delegations
    monkeypatch.setattr(module,'fetch_delegations',fetch_delegations)
    yield rows
    with SessionLocal() as db:
        links=db.scalars(select(OperatorAccess).where(OperatorAccess.exit_code.like('MC-TEST-%'))).all()
        for link in links:
            db.execute(delete(AuthSession).where(AuthSession.user_id==link.user_id))
            db.execute(delete(AuditEvent).where(AuditEvent.user_id==link.user_id))
            account=db.get(User,link.user_id);db.delete(link);db.flush();db.delete(account)
        db.commit()


def payload(row,**updates):
    from app.delegations import fetch_delegations
    store=fetch_delegations()[0]
    return {'code':row['code'],'active':True,'company_code':store.company,'delegation_code':store.code,'permissions':{'orders':True},**updates}


def test_staff_access_pagination_login_and_server_permissions(staff):
    client=manager()
    first=client.get('/api/v1/store/operator-access').json()
    assert len(first['items'])==25 and first['total']==30
    assert len(client.get('/api/v1/store/operator-access?page=2').json()['items'])==5
    result=client.put('/api/v1/store/operator-access',json=payload(staff[0]))
    assert result.status_code==200,result.text
    initial=result.json()['initial_password']
    staff_client=TestClient(app)
    login=staff_client.post('/api/v1/auth/login',json={'email':staff[0]['username'],'password':initial})
    assert login.status_code==200 and login.json()['user']['operator_permissions']['orders']
    assert TestClient(app).post('/api/v1/auth/login',json={'email':staff[0]['code'],'password':initial}).status_code==200
    assert staff_client.get('/api/v1/store/orders').status_code==403  # initial password must be changed
    assert staff_client.patch('/api/v1/account/password',json={'current_password':initial,'new_password':'staff-valid-123'}).status_code==200
    assert staff_client.get('/api/v1/store/orders').status_code==200
    for path in ['/api/v1/store/operator-access','/api/v1/store/replenishment/options','/api/v1/store/customer-access','/api/v1/store/search-settings','/api/v1/store/category-visibility']:
        assert staff_client.get(path).status_code==403,path
    assert staff_client.put('/api/v1/login-appearance',json={}).status_code==403
    assert staff_client.patch('/api/v1/pickup-settings',json={}).status_code==403
    assert client.get('/api/v1/store/operator-access?enabled_only=true&q=staff-test-0').json()['total']==1
    assert client.put('/api/v1/store/operator-access',json=payload(staff[0],active=False)).status_code==200
    assert staff_client.get('/api/v1/account').status_code==401
    assert staff_client.post('/api/v1/auth/login',json={'email':staff[0]['username'],'password':'staff-valid-123'}).status_code==401


def test_staff_password_generation_assignment_and_revocation(staff):
    client=manager();row=staff[1]
    result=client.put('/api/v1/store/operator-access',json=payload(row)).json()
    initial=result['initial_password']
    staff_client=TestClient(app)
    assert staff_client.post('/api/v1/auth/login',json={'email':row['username'],'password':initial}).status_code==200
    reset=client.post('/api/v1/store/operator-access/password',json={'code':row['code'],'password':'custom123'})
    assert reset.status_code==200 and reset.json()['initial_password']=='custom123'
    assert staff_client.get('/api/v1/account').status_code==401
    assert staff_client.post('/api/v1/auth/login',json={'email':row['username'],'password':initial}).status_code==401
    assert staff_client.post('/api/v1/auth/login',json={'email':row['username'],'password':'custom123'}).status_code==200
    random=client.post('/api/v1/store/operator-access/password',json={'code':row['code']}).json()['initial_password']
    assert random!='custom123' and len(random)>=12
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.email==row['username']))
        assert verify_password(random,account.password_hash)
        events=db.scalars(select(AuditEvent).where(AuditEvent.entity_id==account.public_id)).all()
        assert all(random not in str(event.metadata_json) and 'custom123' not in str(event.metadata_json) for event in events)


def test_staff_rejects_missing_exit_user_collision_and_self_lockout(staff):
    client=manager()
    assert client.put('/api/v1/store/operator-access',json=payload({'code':'missing'})).status_code==404
    assert client.put('/api/v1/store/operator-access',json=payload(staff[2],permissions={'unknown':True})).status_code==422
    assert client.put('/api/v1/store/operator-access',json=payload(staff[2],delegation_code='missing')).status_code==422
    created=client.put('/api/v1/store/operator-access',json=payload(staff[2],permissions={'users':True})).json()
    own=TestClient(app);own.post('/api/v1/auth/login',json={'email':staff[2]['username'],'password':created['initial_password']})
    own.patch('/api/v1/account/password',json={'current_password':created['initial_password'],'new_password':'valid-password123'})
    assert own.put('/api/v1/store/operator-access',json=payload(staff[2],active=False,permissions={'users':True})).status_code==409
    assert own.put('/api/v1/store/operator-access',json=payload(staff[2],permissions={'orders':True})).status_code==409
    assert own.post('/api/v1/store/operator-access/password',json={'code':staff[2]['code']}).status_code==409
    staff[3]['username']=staff[2]['username']
    assert client.put('/api/v1/store/operator-access',json=payload(staff[3])).status_code==409
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'pumaresdavid@gmail.com','password':'123456'})
    assert customer.get('/api/v1/store/operator-access').status_code==403


def test_rpa_reuses_legacy_identity_and_never_resets_on_restart(monkeypatch):
    from app.delegations import fetch_delegations
    monkeypatch.setattr(module,'fetch_delegations',fetch_delegations)
    monkeypatch.setattr(module,'fetch_exit_users',lambda *a,**kw:{'items':[{'code':'MC-RPA','username':'RPA','name':'Robot EXIT'}]})
    client=manager()
    with SessionLocal() as db:
        legacy=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        before={key:getattr(legacy,key) for key in ['email','access_code','full_name','password_hash','must_change_password','initial_password_expires_at','company_code','delegation_code','active']}
        pk=legacy.id
        try:
            assert module.provision_rpa(db)
            rpa=db.get(User,pk)
            assert rpa.email=='rpa' and rpa.access_code=='RPA' and verify_password('123456',rpa.password_hash)
            assert client.get('/api/v1/account').status_code==401
            login=TestClient(app).post('/api/v1/auth/login',json={'email':'RPA','password':'123456'})
            assert login.status_code==200 and login.json()['user']['must_change_password']
            rpa.password_hash=hash_password('changed123');rpa.active=False;db.commit()
            assert not module.provision_rpa(db)
            assert verify_password('changed123',rpa.password_hash) and not rpa.active
        finally:
            db.rollback();rpa=db.get(User,pk)
            db.execute(delete(OperatorAccess).where(OperatorAccess.user_id==pk))
            for key,value in before.items():setattr(rpa,key,value)
            db.commit()


def test_exit_user_query_is_paginated_parameterized_and_never_reads_password(monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection;cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value=[{'code':0,'username':' RPA ','email':' rpa@example.test '}]
    cursor.fetchone.return_value={'total':1}
    monkeypatch.setattr(exit_users,'connect_sqlserver',lambda:connection)
    result=exit_users.fetch_exit_users("RPA%'",page=2,page_size=25)
    assert result['items'][0]=={'code':'0','username':'RPA','name':'RPA','email':'rpa@example.test'}
    calls=cursor.execute.call_args_list
    statement,params=calls[-1].args
    assert 'OFFSET %s ROWS FETCH NEXT %s ROWS ONLY' in statement
    assert 'm.CodigoUsuario AS code, m.NombreCorto AS username, m.Correo AS email' in statement
    assert 'FROM MCUsuarios m' in statement
    assert len(calls)==2 and 'INFORMATION_SCHEMA' not in str(calls)
    assert 'Password' not in statement and "RPA%'" not in statement
    assert params[-2:]==(25,25)
    assert params[0]=="%RPA~%'%"


def test_rpa_missing_in_exit_leaves_legacy_untouched(monkeypatch):
    monkeypatch.setattr(module, 'fetch_exit_users', lambda *args, **kwargs: {'items': []})
    with SessionLocal() as db:
        legacy = db.scalar(select(User).where(User.email == 'operador@bermudez.test'))
        previous = legacy.password_hash
        with pytest.raises(RuntimeError):
            module.provision_rpa(db)
        assert legacy.email == 'operador@bermudez.test' and legacy.password_hash == previous
        assert not db.get(OperatorAccess, legacy.id)


def test_short_name_code_and_email_are_login_aliases_and_update_preserves_password(staff):
    client=manager();row=staff[4];row['email']='staff-correoreal@example.test'
    response=client.put('/api/v1/store/operator-access',json=payload(row))
    assert response.status_code==200,response.text
    initial=response.json()['initial_password']
    assert response.json()['email']==row['email']
    for identifier in [row['code'],row['username'],row['email'].upper()]:
        assert TestClient(app).post('/api/v1/auth/login',json={'email':identifier,'password':initial}).status_code==200
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.access_code==row['username']))
        account_id=account.id;previous=account.password_hash
    row['email']='staff-correonuevo@example.test'
    response=client.put('/api/v1/store/operator-access',json=payload(row))
    assert response.status_code==200 and response.json()['initial_password'] is None
    with SessionLocal() as db:
        account=db.get(User,account_id)
        assert account.email==row['email'] and account.password_hash==previous
    assert TestClient(app).post('/api/v1/auth/login',json={'email':row['email'],'password':initial}).status_code==200
    listed=client.get('/api/v1/store/operator-access?enabled_only=true&q=correonuevo').json()['items']
    assert len(listed)==1 and listed[0]['email']==row['email']


def test_users_still_listed_when_delegation_query_fails(staff,monkeypatch):
    def failing():raise RuntimeError('Test delegation failure')
    monkeypatch.setattr(module,'fetch_delegations',failing)
    response=manager().get('/api/v1/store/operator-access')
    assert response.status_code==200,response.text
    data=response.json()
    assert len(data['items'])==25 and data['delegations']==[]
    assert 'sedes' in data['warning']


def test_user_query_failure_is_distinct_from_delegation_failure(staff,monkeypatch):
    def failing(*args,**kwargs):raise RuntimeError('Test MCUsuarios failure')
    monkeypatch.setattr(module,'fetch_exit_users',failing)
    response=manager().get('/api/v1/store/operator-access')
    assert response.status_code==503
    assert 'MCUsuarios' in response.json()['detail'] and 'NombreCorto' in response.json()['detail']
    assert 'sedes' not in response.json()['detail']
