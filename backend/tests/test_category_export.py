import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import Product

bootstrap()


def test_export_includes_unclassified_inactive_and_restricts_access():
    client = TestClient(app)
    path = "/api/v1/store/catalog-categories/export.csv"
    assert client.get(path).status_code == 401
    client.post("/api/v1/auth/login", json={"email": "operador@bermudez.test", "password": "123456"})
    with SessionLocal() as db:
        product = db.scalar(select(Product).order_by(Product.id))
        previous = (product.active, product.short_description, product.material_area_id)
        sku = product.sku
        product.active = False
        product.short_description = "=FORMULA; prueba"
        product.material_area_id = None
        count = db.scalar(select(func.count()).select_from(Product))
        db.commit()
    try:
        response = client.get(path)
        assert response.status_code == 200
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
        assert len(rows) == count
        row = next(row for row in rows if row["CodigoArticulo"] == sku)
        assert row["Activo"] == "No"
        assert row["Categoria"] == ""
        assert row["Descripcion"] == "'=FORMULA; prueba"
        assert "attachment" in response.headers["content-disposition"]
        client.post("/api/v1/auth/login", json={"email": "compras001@cliente.test", "password": "123456"})
        assert client.get(path).status_code == 403
    finally:
        with SessionLocal() as db:
            product = db.scalar(select(Product).where(Product.sku == sku))
            product.active, product.short_description, product.material_area_id = previous
            db.commit()
