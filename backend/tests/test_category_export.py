import csv
import io

from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import Product

bootstrap()


def test_export_includes_unclassified_inactive_and_restricts_access(monkeypatch):
    monkeypatch.setattr("app.category_import.fetch_all_catalog_articles_for_export", lambda: [])
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


def test_export_adds_exit_only_inactive_articles_and_retains_web_only(monkeypatch):
    with SessionLocal() as db:
        product = db.scalar(select(Product).order_by(Product.id))
        code = product.sku
    monkeypatch.setattr("app.category_import.fetch_all_catalog_articles_for_export", lambda: [
        {"code": code, "description": "Descripción actual EXIT", "inactive": "0", "situation": "17", "web": "0"},
        {"code": "41904", "description": "CALDERA MA-40", "inactive": "1", "situation": "0"},
        {"code": "85892", "description": "CLORADOR", "inactive": None, "b2b": "0"},
    ])
    client = TestClient(app)
    client.post("/api/v1/auth/login", json={"email":"operador@bermudez.test", "password":"123456"})
    response = client.get("/api/v1/store/catalog-categories/export.csv")
    assert response.status_code == 200
    rows = {row["CodigoArticulo"]:row for row in csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";")}
    assert rows[code]["Descripcion"] == "Descripción actual EXIT"
    assert rows[code]["ExisteEnEXIT"] == rows[code]["ExisteEnWeb"] == "Sí"
    assert rows[code]["SituacionEXIT"] == "17"
    assert rows[code]["ArticuloWEBEXIT"] == "0"
    assert rows["41904"]["ActivoEXIT"] == "No"
    assert rows["41904"]["Activo"] == ""
    assert rows["41904"]["ExisteEnWeb"] == "No"
    assert rows["41904"]["EstadoClasificacion"] == "SIN_CLASIFICAR"
    assert rows["85892"]["Activo"] == ""
    assert rows["85892"]["InactivoEXIT"] == ""
    assert rows["85892"]["InternetB2BEXIT"] == "0"
    assert any(row["ExisteEnEXIT"] == "No" for row in rows.values())


def test_export_fails_instead_of_returning_partial_postgres_data(monkeypatch):
    def fail():
        raise RuntimeError("ERP no disponible")
    monkeypatch.setattr("app.category_import.fetch_all_catalog_articles_for_export", fail)
    client = TestClient(app)
    client.post("/api/v1/auth/login", json={"email":"operador@bermudez.test", "password":"123456"})
    response = client.get("/api/v1/store/catalog-categories/export.csv")
    assert response.status_code == 503
    assert "parcial" in response.json()["detail"]


def test_total_exit_query_has_no_active_stock_visibility_or_pagination_filters(monkeypatch):
    from app import erp_db
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,sql): queries.append(sql)
        def fetchall(self): return [{"code":"41904", "inactive":"1"}]
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def cursor(self): return Cursor()
    monkeypatch.setattr(erp_db,"connect_sqlserver",Connection)
    monkeypatch.setattr(erp_db,"_article_columns",lambda cn:{"code":"CodigoArticulo", "inactive":"Inactivo", "situation":"Situacion"})
    assert erp_db.fetch_all_catalog_articles_for_export() == [{"code":"41904","inactive":"1"}]
    sql = queries[0]
    where = sql.split("WHERE")[1].split("ORDER BY")[0]
    assert "CodigoArticulo" in where and "<> ''" in where
    assert "Inactivo" not in where
    assert not any(word in sql.upper() for word in (" JOIN ", "OFFSET", "FETCH NEXT", " TOP ", "HAVING"))
    assert "NULL AS [web]" in sql
