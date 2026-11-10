from copy import deepcopy
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from app.main import app
from app.db import SessionLocal
from app.bootstrap import main as bootstrap
from app import manual_classification as manual, erp_db
from app.models import Product, MaterialArea, MaterialFamily, MaterialSubfamily, MaterialProductType, MaterialImportRow, OperatorAccess, User
from app.category_import import _apply_row
bootstrap()
BASE='/api/v1/store/catalog-categories/manual'


def login(email='operador@bermudez.test'):
    client=TestClient(app);assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


@pytest.fixture
def context(monkeypatch):
    suffix=uuid4().hex[:10]
    articles={code:{'article_code':code,'description':'Material '+code,'unit':'UD','brand_name':'TEST-MANUAL','manufacturer_reference':'REF-'+code,'ean':''} for code in ['00'+suffix+'1','00'+suffix+'2']}
    with SessionLocal() as db:
        area=MaterialArea(code='MA'+suffix,name='Área manual '+suffix);db.add(area);db.flush()
        family=MaterialFamily(code='MF'+suffix,name='Familia '+suffix,area_id=area.id);db.add(family);db.flush()
        sub=MaterialSubfamily(code='MS'+suffix,name='Subfamilia '+suffix,family_id=family.id);db.add(sub);db.flush()
        kind=MaterialProductType(code='MT'+suffix,name='Tipo '+suffix,subfamily_id=sub.id);db.add(kind);db.commit()
        ids={'area':area.id,'family':family.id,'subfamily':sub.id,'type':kind.id}
        first=next(iter(articles));_apply_row(db,{'code':first,'exit_article':articles[first],'normalized_name':'Nombre homologado conservado','area':area.name,'family':family.name,'subfamily':sub.name,'product_type':kind.name,'row':1,'raw':{}},'TEST/'+suffix,'Test');db.commit()
        product=db.scalar(select(Product).where(Product.sku==first));product.list_price=13;product.active=False;product.attributes={'dato':'conservar'};db.commit()
    calls=[]
    def fetch(q='',page=1,page_size=50,article_codes=None,excluded_codes=None,search_config=None,management=False):
        calls.append({'q':q,'codes':article_codes,'excluded':excluded_codes,'management':management,'search_config':search_config})
        rows=[dict(row) for code,row in articles.items() if (article_codes is None or code in article_codes) and code not in (excluded_codes or [])]
        if q:rows=[row for row in rows if q.casefold() in (' '.join(str(value) for value in row.values())).casefold()]
        return rows[(page-1)*page_size:page*page_size],len(rows)
    monkeypatch.setattr(manual,'fetch_catalog_articles',fetch)
    monkeypatch.setattr(manual,'fetch_catalog_articles_by_codes',lambda codes,active_only=True:{code:articles[code] for code in codes if code in articles})
    yield login(),ids,articles,calls
    with SessionLocal() as db:
        db.execute(delete(MaterialImportRow).where(MaterialImportRow.article_code.in_(articles)))
        db.execute(delete(Product).where(Product.sku.in_(articles)))
        subids=list(db.scalars(select(MaterialSubfamily.id).where(MaterialSubfamily.family_id==ids['family'])))
        db.execute(delete(MaterialProductType).where(MaterialProductType.subfamily_id.in_(subids)))
        db.execute(delete(MaterialSubfamily).where(MaterialSubfamily.id.in_(subids)))
        db.execute(delete(MaterialFamily).where(MaterialFamily.id==ids['family']))
        db.execute(delete(MaterialArea).where(MaterialArea.id==ids['area']))
        db.commit()


def test_search_filters_unclassified_including_material_without_local_record(context):
    client,ids,articles,calls=context
    result=client.get(BASE+'/materials').json();assert result['total']==2
    assert calls[-1]['management'] is True
    assert calls[-1]['codes'] is None
    assert client.get(BASE+'/materials',params={'product_type_id':ids['type']}).json()['total']==1
    assert client.get(BASE+'/materials',params={'unclassified':True}).json()['items'][0]['code']==list(articles)[1]
    assert client.get(BASE+'/materials',params={'q':list(articles)[1]}).json()['total']==1
    assert client.get(BASE+'/materials',params={'page_size':1,'page':2}).json()['items'][0]['code']==list(articles)[1]
    assert client.get(BASE+'/materials',params={'page':0}).status_code==422
    tree=client.get(BASE+'/tree').json();assert any(row['id']==ids['type'] for row in tree['product_types'])


def test_create_subfamily_and_type_then_assign_complete_batch_preserves_product_data(context):
    client,ids,articles,calls=context
    sub=client.post(BASE+'/subfamilies',json={'parent_id':ids['family'],'name':'Nueva subfamilia'})
    assert sub.status_code==201,sub.text
    subid=sub.json()['id']
    again=client.post(BASE+'/subfamilies',json={'parent_id':ids['family'],'name':'  NUEVA  SUBFAMILIA '}).json()
    assert again['id']==subid and again['created'] is False
    kind=client.post(BASE+'/product-types',json={'parent_id':subid,'name':'Nuevo tipo'}).json()
    with SessionLocal() as db:
        first=db.scalar(select(Product).where(Product.sku==next(iter(articles))))
        before={name:getattr(first,name) for name in ('public_id','short_description','brand_id','list_price','active','attributes','manufacturer_reference','unit','ean')}
    result=client.post(BASE+'/assign',json={'codes':list(articles),'product_type_id':kind['id']})
    assert result.status_code==200,result.text
    assert result.json()['assigned']==2 and result.json()['created_products']==1
    with SessionLocal() as db:
        first=db.scalar(select(Product).where(Product.sku==next(iter(articles))))
        assert {name:getattr(first,name) for name in before}==before
        for code in articles:
            product=db.scalar(select(Product).where(Product.sku==code))
            assert (product.material_area_id,product.material_family_id,product.material_subfamily_id,product.material_product_type_id)==(ids['area'],ids['family'],subid,kind['id'])
            assert product.classification_status=='CLASIFICADO_MANUAL'
            history=list(db.scalars(select(MaterialImportRow).where(MaterialImportRow.product_id==product.id,MaterialImportRow.source_sheet=='Manual')))
            assert len(history)==1 and history[0].raw_data['product_type_id']==kind['id']


def test_missing_material_rejects_entire_batch_without_moving_existing_product(context):
    client,ids,articles,_=context
    code=next(iter(articles))
    result=client.post(BASE+'/assign',json={'codes':[code,'DOES-NOT-EXIST'],'product_type_id':ids['type']})
    assert result.status_code==409,result.text
    with SessionLocal() as db:
        product=db.scalar(select(Product).where(Product.sku==code))
        assert product.source_system=='CATEGORY_UPLOAD'
        assert not list(db.scalars(select(MaterialImportRow).where(MaterialImportRow.product_id==product.id,MaterialImportRow.source_sheet=='Manual')))
    assert client.post(BASE+'/assign',json={'codes':[code],'product_type_id':ids['type'],'area_id':999}).status_code==422
    assert client.post(BASE+'/assign',json={'codes':[],'product_type_id':ids['type']}).status_code==422
    assert client.post(BASE+'/product-types',json={'parent_id':9999999,'name':'No padre'}).status_code==404
    assert client.post(BASE+'/subfamilies',json={'parent_id':ids['family'],'name':'  '}).status_code==422


def test_customer_and_operator_without_categories_cannot_manage_classification(context):
    client,ids,articles,_=context
    assert TestClient(app).get(BASE+'/tree').status_code==401
    customer=login('compras001@cliente.test');assert customer.get(BASE+'/tree').status_code==403
    assert customer.post(BASE+'/assign',json={'codes':list(articles),'product_type_id':ids['type']}).status_code==403
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        access=db.get(OperatorAccess,user.id);previous=deepcopy(access.permissions) if access else None
        if access:access.permissions={**access.permissions,'categories':False}
        else:db.add(OperatorAccess(user_id=user.id,exit_code='TEST-MANUAL',permissions={'categories':False}))
        db.commit();uid=user.id
    try:
        assert client.get(BASE+'/tree').status_code==403
        assert client.get(BASE+'/materials').status_code==403
        assert client.post(BASE+'/subfamilies',json={'parent_id':ids['family'],'name':'Prohibido'}).status_code==403
    finally:
        with SessionLocal() as db:
            access=db.get(OperatorAccess,uid)
            if previous is None:db.delete(access)
            else:access.permissions=previous
            db.commit()


def test_management_sql_is_paginated_and_has_no_stock_or_brand_gate(monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection
    cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value={'total':0};cursor.fetchall.return_value=[]
    monkeypatch.setattr(erp_db,'connect_sqlserver',lambda:connection)
    monkeypatch.setattr(erp_db,'_article_columns',lambda conn:{key:None for key in ['code','description','manufacturer_reference','ean','brand_name','brand_code','inactive','unit','price_with_tax','price_without_tax']}|{'code':'CodigoArticulo','inactive':'Inactivo'})
    monkeypatch.setattr(erp_db,'_brand_catalog_condition',lambda *args:pytest.fail('Management should include hidden brands'))
    assert erp_db.fetch_catalog_articles(management=True)==([],0)
    sql=' '.join(call.args[0] for call in cursor.execute.call_args_list)
    assert 'stock.available' not in sql and 'HAVING SUM' not in sql and 'Inactivo' not in sql
    assert 'OFFSET %s ROWS FETCH NEXT %s ROWS ONLY' in sql


def test_database_error_rolls_back_existing_assignment_and_audit(context,monkeypatch):
    from sqlalchemy.exc import IntegrityError
    client,ids,articles,_=context
    code=next(iter(articles))
    def fail_audit(*args,**kwargs):
        raise IntegrityError('test insert',{},Exception('forced'))
    monkeypatch.setattr(manual,'audit',fail_audit)
    result=client.post(BASE+'/assign',json={'codes':list(articles),'product_type_id':ids['type']})
    assert result.status_code==409
    with SessionLocal() as db:
        existing=db.scalar(select(Product).where(Product.sku==code))
        assert existing.source_system=='CATEGORY_UPLOAD'
        assert db.scalar(select(Product).where(Product.sku==list(articles)[1])) is None
        assert not list(db.scalars(select(MaterialImportRow).where(MaterialImportRow.product_id==existing.id,MaterialImportRow.source_sheet=='Manual')))


def test_description_lookup_does_not_infer_current_classification(context):
    client,ids,articles,calls=context
    code=next(iter(articles))
    articles[code]['description']='TORNILLO PLETINA M10 LLAVE ENTRADA CONTADOR'
    # It can still be found by a partial description, under its existing source filter.
    for q in (code,'TORNILLO PLETINA M10 LLAVE ENTRADA CONTADO'):
        result=client.get(BASE+'/materials',params={'q':q,'product_type_id':ids['type']})
        assert result.status_code==200,result.text
        assert [item['code'] for item in result.json()['items']]==[code]
        assert calls[-1]['codes']==[code]
        assert calls[-1]['management'] is True
        assert 'search_plan' not in calls[-1]['search_config']
        assert 'type_synonym' not in calls[-1]['search_config']


@pytest.mark.parametrize('query,terms',[
    ('TORNILLO PLETINA M10 LLAVE ENTRADA CONTADO',['tornillo','pletina','m10','llave','entrada','contado']),
    ('20254',['20254']),
    ('  plétina   TORNILLO  m10 ',['pletina','tornillo','m10']),
])
def test_management_description_sql_ignores_inferred_type_but_keeps_explicit_filters(monkeypatch,query,terms):
    from app.search import default_search_config
    connection=MagicMock();connection.__enter__.return_value=connection
    cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value={'total':1}
    cursor.fetchall.return_value=[{'article_code':'20254','description':'TORNILLO PLETINA M10 LLAVE ENTRADA CONTADOR'}]
    monkeypatch.setattr(erp_db,'connect_sqlserver',lambda:connection)
    monkeypatch.setattr(erp_db,'_article_columns',lambda conn:{key:None for key in ['code','description','manufacturer_reference','ean','brand_name','brand_code','inactive','unit','price_with_tax','price_without_tax']}|{'code':'CodigoArticulo','description':'DescripcionArticulo'})
    config={**default_search_config(),'search_plan':{'term_groups':[['ignored'] ]},'type_synonym':{'codes':[]}}
    rows,total=erp_db.fetch_catalog_articles(query,page=2,page_size=10,article_codes=['20254'],excluded_codes=['99999'],search_config=config,management=True)
    assert total==1 and rows[0]['article_code']=='20254'
    count=next(call for call in cursor.execute.call_args_list if 'COUNT_BIG' in call.args[0])
    page=next(call for call in cursor.execute.call_args_list if 'OFFSET %s' in call.args[0])
    for call in (count,page):
        sql=call.args[0]
        assert '#SynonymArticles' not in sql and '1=0' not in sql
        assert '#EligibleArticles' in sql and '#HiddenArticles' in sql
        assert 'DescripcionArticulo' in sql and 'COLLATE Latin1_General_CI_AI LIKE %s' in sql
        assert all('%'+term+'%' in call.args[1] for term in terms)
        assert '%ignored%' not in call.args[1]
    assert page.args[1][:-2]==count.args[1]
    assert page.args[1][-2:]==(10,10)
