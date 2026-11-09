from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app import main as module
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import Product,MaterialArea,MaterialFamily,MaterialSubfamily,MaterialProductType
bootstrap()


def test_brand_search_and_suggestions_respect_all_selected_category_levels(monkeypatch):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    with SessionLocal() as db:
        products=db.scalars(select(Product).order_by(Product.id).limit(3)).all()
        keys=('material_area_id','material_family_id','material_subfamily_id','material_product_type_id')
        previous={p.id:{key:getattr(p,key) for key in keys} for p in products}
        ids=[];articles=[]
        for i,p in enumerate(products):
            area=MaterialArea(code=f'TEST-SCOPE-{i}',name=f'Scope area {i}');db.add(area);db.flush()
            family=MaterialFamily(code=f'TEST-SCOPE-{i}',name=f'Scope family {i}',area_id=area.id);db.add(family);db.flush()
            sub=MaterialSubfamily(code=f'TEST-SCOPE-{i}',name=f'Scope sub {i}',family_id=family.id);db.add(sub);db.flush()
            kind=MaterialProductType(code=f'TEST-SCOPE-{i}',name=f'Scope type {i}',subfamily_id=sub.id);db.add(kind);db.flush()
            for key,value in zip(keys,(area.id,family.id,sub.id,kind.id)):setattr(p,key,value)
            ids.append(dict(zip(('area_id','family_id','subfamily_id','product_type_id'),(area.id,family.id,sub.id,kind.id))))
            articles.append({'article_code':p.sku,'description':'ACME material','unit':'UD','manufacturer_reference':'','brand_code':'ACME','brand_name':'ACME','ean':p.ean,'price_with_tax':12.1,'price_without_tax':10})
        db.commit()
    calls=[]
    def fetch(q,page,page_size,article_codes=None,excluded_codes=None,search_config=None):
        calls.append((q,article_codes))
        rows=[a for a in articles if article_codes is None or a['article_code'] in article_codes]
        return rows[:page_size],len(rows)
    monkeypatch.setattr(module,'fetch_catalog_articles',fetch)
    try:
        for i,selected in enumerate(ids):
            for depth in range(1,5):
                filters={key:value for key,value in list(selected.items())[:depth]}
                response=client.get('/api/v1/products',params={'q':'ACME',**filters})
                assert response.status_code==200
                assert [p['sku'] for p in response.json()['items']]==[articles[i]['article_code']]
                suggestions=client.get('/api/v1/search/suggestions',params={'q':'ACME',**filters})
                assert suggestions.status_code==200
                assert [p['sku'] for p in suggestions.json()]==[articles[i]['article_code']]
                assert calls[-1][0]=='ACME' and articles[i]['article_code'] in calls[-1][1]
        assert client.get('/api/v1/search/suggestions',params={'q':'ACME','area_id':999999}).json()==[]
        assert len(client.get('/api/v1/search/suggestions',params={'q':'ACME'}).json())==3
    finally:
        with SessionLocal() as db:
            for pid,values in previous.items():
                for key,value in values.items():setattr(db.get(Product,pid),key,value)
            db.commit()
