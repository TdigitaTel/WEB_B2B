from fastapi.testclient import TestClient

from app.bootstrap import main as bootstrap
from app.main import app


bootstrap()
client = TestClient(app)


def login(email="compras001@cliente.test"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "123456"})
    assert response.status_code == 200


def test_customer_can_search_add_and_order():
    login()
    stores = client.get("/api/v1/stores").json()
    products = client.get("/api/v1/products?q=machon&page_size=3").json()["items"]
    assert stores and products
    response = client.post("/api/v1/cart/items", json={"product_id": products[0]["id"], "quantity": 3})
    assert response.status_code == 201
    order = client.post("/api/v1/orders", json={"store_id": stores[0]["id"], "job_name": "Prueba automática"})
    assert order.status_code == 201
    assert order.json()["status"] == "ENVIADO"


def test_customer_cannot_open_another_customer_order():
    login("compras001@cliente.test")
    first_orders = client.get("/api/v1/orders").json()
    login("compras002@cliente.test")
    response = client.get(f"/api/v1/orders/{first_orders[0]['id']}")
    assert response.status_code == 404


def test_search_matches_separate_words():
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Product
    with SessionLocal() as db:
        product = db.scalar(select(Product).limit(1))
        product.short_description = 'Codo cobre 90° Ø22'
        product.normalized_search = 'codo cobre 90° ø22'
        product_id = product.public_id
        db.commit()
    login()
    response = client.get('/api/v1/products?q=codo%2022')
    assert response.status_code == 200
    products = response.json()['items']
    assert products
    assert any(item['id'] == product_id for item in products)


def test_store_operator_can_move_valid_status():
    login("operador@bermudez.test")
    orders = client.get("/api/v1/store/orders").json()
    sent = next((order for order in orders if order["status"] == "ENVIADO"), None)
    if sent:
        response = client.post(f"/api/v1/store/orders/{sent['id']}/transitions", json={"status": "RECIBIDO_POR_TIENDA"})
        assert response.status_code == 200
