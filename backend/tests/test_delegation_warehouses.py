from unittest.mock import MagicMock
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from app import delegation_warehouses as module
from app.db import SessionLocal
from app.delegations import Delegation
from app.models import DelegationWarehouse as Link, User, OperatorAccess, AuthSession
from test_sales_order_series import manager, series

PREFIX='/api/v1/store/delegation-warehouses'

@pytest.fixture
def configured(manager,monkeypatch):
    seats=[Delegation(1,'00','Almeiras','','P','Principal'),Delegation(1,'02','Ferrol','','F','Ferrol'),Delegation(2,'00','Otra empresa','','P','Otro')]
    warehouses=[{'company_code':company,'code':code,'name':f'Almacén {company} {code}'} for company,code in [(1,'P'),(1,'F'),(1,'A'),(1,'B'),(2,'P'),(2,'X')]]
    monkeypatch.setattr(module,'fetch_delegations',lambda:seats)
    monkeypatch.setattr(module,'fetch_warehouses',lambda:warehouses)
    yield manager,seats,warehouses
    with SessionLocal() as db:db.execute(delete(Link));db.commit()


def save(client,code='A',**patch):
    return client.put(PREFIX+'/assignments',json={'company_code':1,'delegation_code':'00','warehouse_code':code,**patch})


def rows(client,**params):
    response=client.get(PREFIX+'/assignments',params=params)
    assert response.status_code==200,response.text
    return response.json()


def test_principal_first_multiple_links_flags_and_composite_company_key(configured):
    client,_,_=configured
    assert client.post(PREFIX+'/sync').status_code==200
    assert len(rows(client))==3
    assert save(client,'A').status_code==200
    assert save(client,'B',use_for_stock=False).status_code==200
    data=rows(client,company_code=1,delegation_code='00')
    assert [r['warehouse_code'] for r in data]==['P','A','B']
    assert data[0]['is_primary'] and all(not r['is_primary'] for r in data[1:])
    assert data[1]['active'] and data[1]['use_for_stock']
    assert save(client,'A',active=False,expected_version=data[1]['version']).status_code==200
    assert [r['warehouse_code'] for r in rows(client,company_code=1,delegation_code='00',stock_only=True)]==['P']
    assert client.post(PREFIX+'/sync').status_code==200
    assert client.post(PREFIX+'/sync').status_code==200
    updated=rows(client,company_code=1,delegation_code='00')
    assert len(updated)==3 and not updated[1]['active'] and not updated[2]['use_for_stock']
    assert len(rows(client,company_code=2,delegation_code='00'))==1
    # Primary flags are configurable too, with no loss on synchronization.
    assert save(client,'P',active=False,use_for_stock=False,expected_version=updated[0]['version']).status_code==200
    assert client.post(PREFIX+'/sync').status_code==200
    assert rows(client,company_code=1,delegation_code='00',stock_only=True)==[]


def test_source_validation_duplicates_conflicts_and_primary_change(configured):
    client,seats,_=configured
    assert save(client,'X').status_code==422 # Other company only.
    assert save(client,'A',delegation_code='99').status_code==422
    assert save(client,'A').status_code==200 # Seeds primary even before explicit sync.
    assert save(client,'A').status_code==409
    item=rows(client,company_code=1,delegation_code='00')[1]
    assert save(client,'A',expected_version=item['version'],use_for_stock=False).status_code==200
    assert save(client,'A',expected_version=item['version']).status_code==409
    seats[0]=Delegation(1,'00','Almeiras nueva','','A','Nuevo principal')
    assert client.post(PREFIX+'/sync').status_code==200
    data=rows(client,company_code=1,delegation_code='00')
    assert [r['warehouse_code'] for r in data]==['A','P']
    assert data[0]['is_primary'] and not data[0]['use_for_stock']
    assert not data[1]['is_primary'] and data[1]['active']
    seats[0]=Delegation(1,'00','Almeiras','','B','Principal nuevo sin asociación previa')
    assert client.post(PREFIX+'/sync').status_code==200
    assert [r['warehouse_code'] for r in rows(client,company_code=1,delegation_code='00')]==['B','A','P']
    with SessionLocal() as db:
        db.add(Link(company_code=1,delegation_code='00',warehouse_code='INVALID',delegation_name='',warehouse_name='',is_primary=True))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()


def test_exit_failure_keeps_saved_configuration_and_read_is_not_a_sync(configured,monkeypatch):
    client,_,_=configured
    assert save(client,'A').status_code==200
    before=rows(client)
    def unavailable():raise RuntimeError('EXIT unavailable')
    monkeypatch.setattr(module,'fetch_warehouses',unavailable)
    assert client.get(PREFIX+'/options').status_code==503
    assert client.post(PREFIX+'/sync').status_code==503
    assert save(client,'B').status_code==503
    assert rows(client)==before


def test_operator_only_reads_authorized_delegations_and_cannot_write(configured):
    client,_,_=configured
    assert client.post(PREFIX+'/sync').status_code==200
    from app.auth import hash_password
    from fastapi.testclient import TestClient
    from app.main import app
    with SessionLocal() as db:
        user=User(email='warehouse-operator@test.invalid',full_name='Operador',role='OPERADOR_TIENDA',active=True,password_hash=hash_password('warehouse-test123'),company_code=1,delegation_code='02')
        db.add(user);db.flush();uid=user.id
        db.add(OperatorAccess(user_id=uid,exit_code='warehouse-op',permissions={'delegation_ids':['1:02']}));db.commit()
    try:
        operator=TestClient(app)
        assert operator.post('/api/v1/auth/login',json={'email':'warehouse-operator@test.invalid','password':'warehouse-test123'}).status_code==200
        assert {(r['company_code'],r['delegation_code']) for r in rows(operator)}=={(1,'02')}
        assert rows(operator,company_code=2)==[]
        options=operator.get(PREFIX+'/options').json()
        assert not options['can_edit'] and len(options['delegations'])==1
        assert operator.post(PREFIX+'/sync').status_code==403
        assert save(operator,'A').status_code==403
    finally:
        with SessionLocal() as db:
            db.execute(delete(AuthSession).where(AuthSession.user_id==uid));db.execute(delete(OperatorAccess).where(OperatorAccess.user_id==uid));db.execute(delete(User).where(User.id==uid));db.commit()


def test_warehouses_come_from_exit_with_company_key(monkeypatch):
    connection=MagicMock();cursor=connection.cursor.return_value
    cursor.fetchall.return_value=[{'company_code':1,'code':' A ','name':' Principal '},{'company_code':2,'code':'A','name':'Otro'}]
    monkeypatch.setattr(module,'connect_sqlserver',lambda:connection)
    connection.__enter__.return_value=connection
    data=module.fetch_warehouses()
    assert data==[{'company_code':1,'code':'A','name':'Principal'},{'company_code':2,'code':'A','name':'Otro'}]
    query=cursor.execute.call_args.args[0]
    assert 'FROM dbo.almacenes' in query and 'CodigoEmpresa' in query
