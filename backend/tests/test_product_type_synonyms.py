import io
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.main import app
from app.db import SessionLocal
from app.models import (MaterialArea, MaterialFamily, MaterialSubfamily, MaterialProductType,
                        ProductTypeSynonyms, ProductTypeNameSynonyms, Product)
from app.product_type_synonyms import HEADERS, catalog_search_config

bootstrap()
PREFIX='/api/v1/store/product-type-synonyms'


def login(email='operador@bermudez.test'):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


@pytest.fixture
def types():
    records=[]
    with SessionLocal() as db:
        for index,name in enumerate(['MACHÓN','machon','Machón']):
            area=MaterialArea(code=f'GROUP-AREA-{index}',name=f'Área prueba {index}');db.add(area);db.flush()
            family=MaterialFamily(code=f'GROUP-FAM-{index}',name=f'Familia {index}',area_id=area.id);db.add(family);db.flush()
            sub=MaterialSubfamily(code=f'GROUP-SUB-{index}',name=f'Subfamilia {index}',family_id=family.id);db.add(sub);db.flush()
            item=MaterialProductType(code=f'TIP-INTERNAL-{index}',name=name,subfamily_id=sub.id);db.add(item);db.flush()
            records.append((item.id,sub.id,family.id,area.id))
        db.commit()
    yield [row[0] for row in records]
    with SessionLocal() as db:
        saved=db.get(ProductTypeNameSynonyms,'machon')
        if saved:db.delete(saved)
        for row in records:
            old=db.get(ProductTypeSynonyms,row[0])
            if old:db.delete(old)
        db.flush()
        for row in records:
            for model,pk in zip([MaterialProductType,MaterialSubfamily,MaterialFamily,MaterialArea],row):
                db.delete(db.get(model,pk));db.flush()
        db.commit()


def group(client):return next(row for row in client.get(PREFIX).json() if row['key']=='machon')
def save(client,words,version=None):
    return client.put(PREFIX+'/group',json={'type_name':'Machón','synonyms':words,**({'version':version} if version else {})})
def xlsx(rows):
    book=Workbook();sheet=book.active;sheet.title='Sinonimos';sheet.append(HEADERS)
    for name,words in rows:sheet.append([name,'Informativo']+words+['']*(10-len(words)))
    output=io.BytesIO();book.save(output);return output.getvalue()
def upload(client,content,apply=False,mode='merge'):
    return client.post(PREFIX+'/import',files={'file':('sinonimos.xlsx',content)},data={'apply':str(apply).lower(),'mode':mode})


def test_name_group_has_three_explicit_paths_and_one_shared_save(types):
    client=login();item=group(client)
    assert item['name']=='MACHÓN' and len(item['paths'])==3 and item['synonyms']==[]
    assert [p['area'] for p in item['paths']]==[f'Área prueba {i}' for i in range(3)]
    assert item['paths'][0]['category_family']=='Familia 0' and item['paths'][0]['subfamily']=='Subfamilia 0'
    assert len([row for row in client.get(PREFIX).json() if row['key']=='machon'])==1
    response=save(client,['niple','machones'],item['version'])
    assert response.status_code==200 and response.json()['synonyms']==['niple','machones']
    assert save(client,['otro'],item['version']).status_code==409
    with SessionLocal() as db:
        assert db.get(ProductTypeNameSynonyms,'machon').synonyms==['niple','machones']
        assert all(db.get(ProductTypeSynonyms,pk) is None for pk in types)
    assert save(client,[]).json()['synonyms']==[]
    assert client.put(PREFIX+'/group',json={'type_name':'No existe','synonyms':[]}).status_code==404
    assert client.put(PREFIX+'/99999999',json={'synonyms':['niple']}).status_code==404


def test_limits_validation_and_old_path_identifier_updates_common_group(types):
    client=login()
    for words in [['a']*11,['Válvula','valvula'],[''],['*'],['hola%'],['a'*101]]:
        assert save(client,words).status_code==422
    response=client.put(f'{PREFIX}/{types[1]}',json={'synonyms':['niple']})
    assert response.status_code==200 and len(response.json()['paths'])==3
    assert group(client)['synonyms']==['niple']


def test_legacy_words_are_combined_without_loss_and_can_be_replaced(types):
    with SessionLocal() as db:
        db.add(ProductTypeSynonyms(product_type_id=types[0],synonyms=['Niple'],version=1))
        db.add(ProductTypeSynonyms(product_type_id=types[1],synonyms=['niple','Manguito'],version=2));db.commit()
    client=login();item=group(client)
    assert item['synonyms']==['Niple','Manguito']
    assert save(client,['conector'],item['version']).status_code==200
    assert group(client)['synonyms']==['conector']
    with SessionLocal() as db:assert db.get(ProductTypeSynonyms,types[0]).synonyms==['Niple']


def test_legacy_overflow_is_preserved_for_review(types):
    with SessionLocal() as db:
        db.add(ProductTypeSynonyms(product_type_id=types[0],synonyms=[f'palabra{i}' for i in range(10)],version=1))
        db.add(ProductTypeSynonyms(product_type_id=types[1],synonyms=['once'],version=1));db.commit()
    client=login();item=group(client)
    assert item['needs_review'] is True and len(item['synonyms'])==11
    assert client.get(PREFIX+'/export.xlsx').status_code==409
    assert save(client,['niple'],item['version']).status_code==200
    assert not group(client)['needs_review']


def test_excel_is_one_row_per_name_with_path_sheet_and_preview_does_not_write(types):
    client=login();content=xlsx([('MACHÓN',['niple'])])
    preview=upload(client,content).json()
    assert preview['changed']==1 and preview['applied'] is False and len(preview['items'][0]['paths'])==3
    with SessionLocal() as db:assert db.get(ProductTypeNameSynonyms,'machon') is None
    assert upload(client,content,True).json()['applied'] is True
    response=client.get(PREFIX+'/export.xlsx');assert response.status_code==200
    book=load_workbook(io.BytesIO(response.content));sheet=book['Sinonimos']
    rows=[row for row in sheet if row[0].value=='MACHÓN']
    assert len(rows)==1 and rows[0][2].value=='niple'
    assert 'Área: Área prueba 0' in rows[0][1].value
    assert [cell.value for cell in book['Cadenas'][1]]==['TipoProducto','Area','Categoria_Familia','Subfamilia']
    assert len([row for row in book['Cadenas'] if row[0].value=='MACHÓN'])==3
    assert upload(client,response.content).json()['changed']==0


def test_bulk_is_atomic_and_add_replace_apply_to_whole_name(types):
    client=login();save(client,['niple'])
    content=xlsx([('Machón',['nuevo']),('Desconocido',['otro'])])
    assert upload(client,content).json()['errors'][0]['name']=='Desconocido'
    assert upload(client,content,True).status_code==422 and group(client)['synonyms']==['niple']
    assert upload(client,xlsx([('Machon',['NIPLE','nuevo'])]),True).json()['changed']==1
    assert group(client)['synonyms']==['niple','nuevo']
    assert upload(client,xlsx([('Machón',[])]),True).json()['changed']==0
    assert upload(client,xlsx([('Machón',[])]),True,'replace').json()['changed']==1
    assert group(client)['synonyms']==[]
    assert upload(client,xlsx([('MACHÓN',['a']),('machon',['b'])])).json()['errors']
    save(client,[f'palabra{i}' for i in range(10)])
    assert upload(client,xlsx([('MACHÓN',['once'])]),True).status_code==422
    assert upload(client,xlsx([('MACHÓN',['=SUM(1,2)'])])).status_code==422
    assert upload(client,b'invalid zip').status_code==422


def test_search_includes_all_paths_and_future_same_name_paths(types):
    client=login();save(client,['niple','niple de conexión'])
    with SessionLocal() as db:
        products=list(db.scalars(select(Product).order_by(Product.id).limit(3)));old=[p.material_product_type_id for p in products]
        for product,pk in zip(products,types):product.material_product_type_id=pk
        db.commit()
        try:
            config=catalog_search_config(db,'NIPLE de conexión latón 1/2')
            assert set(config['type_synonym']['codes'])=={p.sku for p in products}
            assert config['type_synonym']['query']=='laton 1/2'
            assert 'type_synonym' not in catalog_search_config(db,'niplero')
        finally:
            for product,pk in zip(products,old):product.material_product_type_id=pk
            db.commit()


@pytest.mark.parametrize('path',[PREFIX,PREFIX+'/export.xlsx'])
def test_permissions(path):
    assert TestClient(app).get(path).status_code==401
    assert login('compras001@cliente.test').get(path).status_code==403


def test_exit_synonyms_preserve_visibility_filters_and_pagination(monkeypatch):
    from app import erp_db
    calls=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,parameters=()):calls.append((sql,parameters))
        def fetchone(self):return {'total':2}
        def fetchall(self):return []
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return Cursor()
    monkeypatch.setattr(erp_db,'connect_sqlserver',Connection)
    monkeypatch.setattr(erp_db,'_brand_columns',lambda cn:{'code':'Marca','name':None,'internet_b2b':'InternetB2B','company':None})
    monkeypatch.setattr(erp_db,'_article_columns',lambda cn:{'code':'CodigoArticulo','description':'DescripcionArticulo','manufacturer_reference':None,'ean':None,'brand_name':None,'brand_code':'Marca','unit':None,'price_with_tax':None,'price_without_tax':None,'inactive':'Inactivo'})
    from app.search import default_search_config
    config=default_search_config();config['type_synonym']={'codes':[f'{i:05}' for i in range(1001)],'query':'laton 1/2'}
    erp_db.fetch_catalog_articles('llave de paso laton 1/2',page=2,article_codes=['00001'],excluded_codes=['00002'],search_config=config)
    inserts=[params for sql,params in calls if sql.startswith('INSERT INTO #SynonymArticles')]
    assert list(map(len,inserts))==[1000,1]
    sql,params=next((sql,params) for sql,params in calls if sql.startswith('SELECT COUNT_BIG'))
    assert '#EligibleArticles' in sql and '#HiddenArticles' in sql and '[Inactivo]' in sql
    assert ' OR (EXISTS (SELECT 1 FROM #SynonymArticles' in sql
    assert params.count('%laton%')==4 and params.count('%1/2%')==4
    assert params.count('%llave%')==2
    assert sql.count(' LIKE %s')==len(params)
    page_sql,page_params=calls[-1]
    assert page_params[:-2]==params and page_params[-2:]==(24,24)




def test_catalogue_and_suggestions_use_all_shared_type_paths(monkeypatch,types):
    operator=login();save(operator,['niple'])
    with SessionLocal() as db:
        products=list(db.scalars(select(Product).order_by(Product.id).limit(3)));old=[p.material_product_type_id for p in products]
        for product,pk in zip(products,types):product.material_product_type_id=pk
        db.commit();skus={p.sku for p in products};ids=[p.id for p in products]
    calls=[]
    def source(*args,**kwargs):calls.append((args,kwargs));return [],0
    monkeypatch.setattr('app.main.fetch_catalog_articles',source)
    try:
        client=login('compras001@cliente.test')
        assert client.get('/api/v1/products',params={'q':'niple'}).status_code==200
        assert client.get('/api/v1/search/suggestions',params={'q':'niple'}).status_code==200
        assert len(calls)==2 and all(set(item[1]['search_config']['type_synonym']['codes'])==skus for item in calls)
        assert all('excluded_codes' in item[1] for item in calls)
    finally:
        with SessionLocal() as db:
            for pk,old_type in zip(ids,old):db.get(Product,pk).material_product_type_id=old_type
            db.commit()


def test_new_path_automatically_inherits_list_and_invalidates_editor_version(types):
    client=login();saved=save(client,['niple']).json()
    with SessionLocal() as db:
        parent=db.get(MaterialProductType,types[0])
        extra=MaterialProductType(code='TIP-NEW-SHARED',name='MACHON',subfamily_id=parent.subfamily_id);db.add(extra);db.commit();pk=extra.id
    try:
        item=group(client)
        assert len(item['paths'])==4 and item['synonyms']==['niple']
        assert save(client,['otro'],saved['version']).status_code==409
    finally:
        with SessionLocal() as db:db.delete(db.get(MaterialProductType,pk));db.commit()


def test_operator_requires_settings_option(types):
    from app.models import OperatorAccess, User
    client=login()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        db.add(OperatorAccess(user_id=user.id,exit_code='SYN-PERMISSION-TEST',permissions={'settings':False}));db.commit();pk=user.id
    try:
        assert client.get(PREFIX).status_code==403
        assert save(client,['niple']).status_code==403
        assert upload(client,xlsx([('MACHÓN',['niple'])]),True).status_code==403
    finally:
        with SessionLocal() as db:db.delete(db.get(OperatorAccess,pk));db.commit()
