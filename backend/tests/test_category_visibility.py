from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import Product, MaterialArea

bootstrap()

def test_hidden_category_filters_products_and_can_be_restored():
    client = TestClient(app)
    client.post('/api/v1/auth/login', json={'email':'operador@bermudez.test','password':'123456'})
    response = client.get('/api/v1/store/category-visibility')
    assert response.status_code == 200
    with SessionLocal() as db:
        area = MaterialArea(code="TEST-VIS", name="Categoría de prueba de visibilidad")
        db.add(area)
        db.flush()
        product = db.scalar(select(Product).order_by(Product.id))
        product.material_area_id = area.id
        db.commit()
        area_id, sku = area.id, product.sku
    assert client.patch(f'/api/v1/store/category-visibility/{area_id}', json={'visible':False}).status_code == 200
    try:
        client.post('/api/v1/auth/login', json={'email':'compras001@cliente.test','password':'123456'})
        assert client.get('/api/v1/store/category-visibility').status_code == 403
        assert client.get(f'/api/v1/products?q={sku}').json()['total'] == 0
        assert area_id not in [row['id'] for row in client.get('/api/v1/catalog/classification').json()]
    finally:
        client.post('/api/v1/auth/login', json={'email':'operador@bermudez.test','password':'123456'})
        assert client.patch(f'/api/v1/store/category-visibility/{area_id}', json={'visible':True}).status_code == 200
    client.post('/api/v1/auth/login', json={'email':'compras001@cliente.test','password':'123456'})
    assert client.get(f'/api/v1/products?q={sku}').json()['total'] > 0


def test_unclassified_hidden_by_default_and_managed_by_operator():
    from app.category_visibility import visible_catalog_codes, UNCLASSIFIED_CODE
    client=TestClient(app)
    client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        products=db.scalars(select(Product).order_by(Product.id).limit(2)).all()
        old=[row.material_area_id for row in products]
        classified=MaterialArea(code='TEST-CLASSIFIED',name='Categoría válida prueba')
        db.add(classified);db.flush()
        products[0].material_area_id=classified.id;products[1].material_area_id=None
        db.commit()
        codes=[row.sku for row in products]
        assert visible_catalog_codes(db,codes)==[codes[0]]
        assert visible_catalog_codes(db,['NOT-IN-POSTGRES'])==[]
    rows=client.get('/api/v1/store/category-visibility').json()
    control=next(row for row in rows if row['code']==UNCLASSIFIED_CODE)
    assert control['visible'] is False
    client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert client.get('/api/v1/products',params={'q':codes[1]}).json()['total']==0
    assert client.get('/api/v1/search/suggestions',params={'q':codes[1]}).json()==[]
    assert client.patch(f"/api/v1/store/category-visibility/{control['id']}",json={'visible':True}).status_code==403
    client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    assert client.patch(f"/api/v1/store/category-visibility/{control['id']}",json={'visible':True}).status_code==200
    with SessionLocal() as db:
        assert visible_catalog_codes(db,None) is None
    client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert client.get('/api/v1/products',params={'q':codes[1]}).json()['total']>0
    client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    client.patch(f"/api/v1/store/category-visibility/{control['id']}",json={'visible':False})
    with SessionLocal() as db:
        for code,area_id in zip(codes,old):db.scalar(select(Product).where(Product.sku==code)).material_area_id=area_id
        db.commit()
