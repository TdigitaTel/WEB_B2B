import copy
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import SearchSettings
from app.search import normalize_query, default_search_config
from app.search_settings import get_search_config
from app.measure_equivalences import initialize_measure_equivalences

bootstrap()
PATH="/api/v1/store/search-settings"


@pytest.fixture(autouse=True)
def restore_config():
    with SessionLocal() as db:
        previous=copy.deepcopy(db.get(SearchSettings,1).config)
    yield
    with SessionLocal() as db:
        db.get(SearchSettings,1).config=previous;db.commit()


def operator():
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    return client


def config(measures):
    return {**default_search_config(), 'material_groups':[{'name':'Inoxidable','synonyms':['inox']}],
            'measure_equivalences':measures}


def test_no_fixed_fallback_and_longest_phrase_without_substrings():
    assert normalize_query('piezas inoxidable de media')=='piezas inoxidable media'
    rules=[{'value':'1/2','aliases':['media','mitad']},{'value':'3/4','aliases':['tres cuartos']}]
    assert normalize_query('piezas inoxidable de media',rules)=='piezas inoxidable 1/2'
    assert normalize_query('válvula de tres cuartos',rules)=='valvula 3/4'
    assert normalize_query('mediador',rules)=='mediador'
    assert normalize_query('media',[])=='media'


def test_configuration_is_saved_and_used_by_preview_catalogue_and_suggestions(monkeypatch):
    from app import main as module
    client=operator()
    response=client.patch(PATH,json=config([{'value':'1/2','aliases':['media','medio','mitad']}]))
    assert response.status_code==200,response.text
    assert client.get(PATH).json()['measure_equivalences'][0]['aliases']==['media','medio','mitad']
    plan=client.get('/api/v1/store/product-type-synonyms/preview',params={'q':'piezas inoxidable de mitad'}).json()
    assert plan['normalized']=='piezas inoxidable 1/2'
    assert plan['ignored']==['piezas'] and plan['term_groups']==[['inoxidable','inox'],['1/2']]
    calls=[]
    def catalogue(*args,**kwargs):
        calls.append(kwargs['search_config']['search_plan']);return [],0
    monkeypatch.setattr(module,'fetch_catalog_articles',catalogue)
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    for endpoint in ('/api/v1/products','/api/v1/search/suggestions'):
        response=customer.get(endpoint,params={'q':'piezas inoxidable de mitad'})
        assert response.status_code==200,response.text
        assert calls[-1]['term_groups']==[['inoxidable','inox'],['1/2']]
    with SessionLocal() as db:
        assert db.get(SearchSettings,1).config['measure_equivalences'][0]['aliases'][-1]=='mitad'


def test_removal_and_legacy_patch_do_not_restore_fixed_rules():
    client=operator();payload=config([{'value':'3/4','aliases':['media']}])
    assert client.patch(PATH,json=payload).status_code==200
    assert client.get('/api/v1/store/product-type-synonyms/preview',params={'q':'media'}).json()['normalized']=='3/4'
    legacy={key:value for key,value in payload.items() if key!='measure_equivalences'}
    assert client.patch(PATH,json=legacy).status_code==200
    assert client.get(PATH).json()['measure_equivalences']==payload['measure_equivalences']
    assert client.patch(PATH,json={**payload,'measure_equivalences':[]}).status_code==200
    with SessionLocal() as db:
        assert initialize_measure_equivalences(db) is False;db.commit()
    assert client.get('/api/v1/store/product-type-synonyms/preview',params={'q':'media'}).json()['normalized']=='media'
    assert client.get(PATH).json()['measure_equivalences']==[]


@pytest.mark.parametrize('rules',[
    [{'value':'1/2','aliases':['media']},{'value':'3/4','aliases':['MEDIA']}],
    [{'value':'1/2','aliases':['media']},{'value':'1/2','aliases':['mitad']}],
    [{'value':'1/2','aliases':['3/4']},{'value':'3/4','aliases':['grande']}],
    [{'value':'1/0','aliases':['media']}],
    [{'value':'1/2','aliases':['%']}],
    [{'value':'1/2','aliases':[]}],
])
def test_ambiguous_or_invalid_equivalences_are_rejected_atomically(rules):
    client=operator();before=client.get(PATH).json()
    response=client.patch(PATH,json=config(rules))
    assert response.status_code==422,response.text
    assert client.get(PATH).json()==before


def test_initial_migration_preserves_materials_and_is_idempotent():
    with SessionLocal() as db:
        row=db.get(SearchSettings,1);row.config={**default_search_config(),'material_groups':[{'name':'Cobre','synonyms':['copper']}],'custom_marker':'preserve'};db.commit()
        assert initialize_measure_equivalences(db) is True;db.commit()
        assert row.config['custom_marker']=='preserve' and row.config['material_groups'][0]['name']=='Cobre'
        rules=get_search_config(db)['measure_equivalences']
        assert normalize_query('machón de media pulgada',rules)=='machon 1/2'
        assert normalize_query('½',rules)=='1/2'
        assert initialize_measure_equivalences(db) is False
        row.config={**row.config,'measure_equivalences':[{'value':'20','aliases':['veinte']}]};db.commit()
        assert initialize_measure_equivalences(db) is False
        assert get_search_config(db)['measure_equivalences'][0]['value']=='20'


def test_customer_cannot_change_measure_equivalences():
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert customer.patch(PATH,json=config([])).status_code==403
