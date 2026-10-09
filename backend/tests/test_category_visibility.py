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
