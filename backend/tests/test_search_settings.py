import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.main import app
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import SearchSettings
from app.search import default_search_config
from app.search_settings import SearchSettingsIn, get_search_config

bootstrap()
PATH = "/api/v1/store/search-settings"


def test_operator_settings_persist_and_are_forwarded_to_products_and_suggestions(monkeypatch):
    client = TestClient(app)
    assert client.get(PATH).status_code == 401
    client.post("/api/v1/auth/login", json={"email":"operador@bermudez.test", "password":"123456"})
    before = client.get(PATH).json()
    config = {**default_search_config(), "accessory_terms":["Recambios", "recambios"], "piece_names":["Codo", "racor"], "materials":["Latón"]}
    seen = []
    def search(*args, **kwargs):
        seen.append(kwargs["search_config"])
        return [], 0
    monkeypatch.setattr("app.main.fetch_catalog_articles", search)
    try:
        result = client.patch(PATH, json=config)
        assert result.status_code == 200
        assert result.json()["accessory_terms"] == ["recambios"]
        assert result.json()["materials"] == ["laton"]
        with SessionLocal() as db:
            assert get_search_config(db) == result.json()
        # Usar un cliente autorizado para consultar el catálogo real de la API.
        client.post("/api/v1/auth/login", json={"email":"compras001@cliente.test", "password":"123456"})
        assert client.get(PATH).status_code == 403
        assert client.patch(PATH, json=config).status_code == 403
        assert client.get("/api/v1/products?q=recambios+laton").status_code == 200
        assert client.get("/api/v1/search/suggestions?q=recambios+laton").status_code == 200
        assert len(seen) == 2
        assert all(item["accessory_terms"] == ["recambios"] and item["piece_names"] == ["codo", "racor"] for item in seen)
    finally:
        client.post("/api/v1/auth/login", json={"email":"operador@bermudez.test", "password":"123456"})
        assert client.patch(PATH, json=before).status_code == 200


@pytest.mark.parametrize("words", [[], ["%"], ["dos palabras"], ["-"], ["x"] * 81])
def test_invalid_search_words_rejected(words):
    with pytest.raises(ValidationError):
        SearchSettingsIn(**{**default_search_config(), "accessory_terms":words})


def test_material_cannot_also_be_generic_term():
    with pytest.raises(ValidationError):
        SearchSettingsIn(**{**default_search_config(), "accessory_terms":["laton"]})
