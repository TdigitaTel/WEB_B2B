import pytest
from app.search import normalize_query


@pytest.mark.parametrize(('query','expected'), [
    ('machón de media', 'machon 1/2'),
    ('machon de 1/2', 'machon 1/2'),
    ('machón de media pulgada', 'machon 1/2'),
    ('válvula de tres cuartos', 'valvula 3/4'),
    ('racor de un cuarto', 'racor 1/4'),
    ('machón de ½', 'machon 1/2'),
    ('machón de 1 / 2', 'machon 1/2'),
    ('B2B000001', 'b2b000001'),
])
def test_professional_measure_aliases(query, expected):
    assert normalize_query(query) == expected


@pytest.mark.parametrize(("query", "terms", "accessories"), [
    ("accesorios de latón", ["laton"], True),
    ("piezas de latón", ["laton"], True),
    ("componentes de cobre", ["cobre"], True),
    ("conexiones PVC", ["pvc"], True),
    ("ACCESORIOS LATON 1/2", ["laton", "1/2"], True),
    ("accesorios de cobre", ["cobre"], True),
    ("accesorios inox", ["inox"], True),
    ("codo de latón", ["codo", "laton"], False),
    ("accesorios caldera", ["accesorios", "caldera"], False),
    ("accesorios", ["accesorios"], False),
    ("41904", ["41904"], False),
])
def test_material_accessory_intent(query, terms, accessories):
    from app.search import catalog_search_intent
    assert catalog_search_intent(query) == (terms, accessories)


def test_exit_generic_material_queries_match_direct_search_and_preserve_filters(monkeypatch):
    from app import erp_db
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, parameters=()): queries.append((sql, parameters))
        def fetchone(self): return {"total": 0}
        def fetchall(self): return []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
    monkeypatch.setattr(erp_db, "connect_sqlserver", Connection)
    monkeypatch.setattr(erp_db, "_article_columns", lambda cn: {
        "code":"CodigoArticulo", "description":"DescripcionArticulo", "manufacturer_reference":None,
        "ean":None, "brand_name":None, "brand_code":None, "unit":None,
        "price_with_tax":None, "price_without_tax":None, "inactive":"Inactivo",
    })
    assert erp_db.fetch_catalog_articles("accesorios de latón 1/2", page=2) == ([], 0)
    count_sql, count_params = queries[0]
    page_sql, page_params = queries[1]
    assert not any(word in count_params for word in ("% codo %", "% te %", "% racor %"))
    assert "REPLACE(" not in count_sql
    assert "%laton%" in count_params and "%1/2%" in count_params
    assert "%accesorios%" not in count_params
    assert count_sql.count(" LIKE %s") == len(count_params)
    assert "COLLATE Latin1_General_CI_AI" in count_sql
    assert "INNER JOIN" not in count_sql  # Una búsqueda no exige stock positivo.
    assert "[Inactivo]" in count_sql
    assert page_params[:-2] == count_params
    assert page_params[-2:] == (24, 24)
    assert "OFFSET %s ROWS FETCH NEXT %s ROWS ONLY" in page_sql

    expected = list(queries)
    for query in ("latón 1/2", "piezas de latón 1/2", "componentes de latón 1/2", "conexiones de latón 1/2"):
        queries.clear()
        erp_db.fetch_catalog_articles(query, page=2)
        assert queries == expected

    queries.clear()
    config = {"enabled":True, "accessory_terms":["componentes"], "piece_names":["racor"], "materials":["laton"]}
    erp_db.fetch_catalog_articles("componentes de latón", search_config=config)
    custom_params = queries[0][1]
    assert "% racor %" not in custom_params and "%laton%" in custom_params
    assert "% codo %" not in custom_params and "%componentes%" not in custom_params
    queries.clear()
    erp_db.fetch_catalog_articles("componentes de latón", search_config={**config,"enabled":False})
    assert "%componentes%" in queries[0][1] and "% racor %" not in queries[0][1]


def test_search_custom_configuration_and_disabled_mode():
    from app.search import catalog_search_intent, default_search_config
    config = default_search_config()
    config["accessory_terms"] = ["repuestos"]
    assert catalog_search_intent("repuestos de latón", config) == (["laton"], True)
    assert catalog_search_intent("piezas de latón", config) == (["piezas", "laton"], False)
    config["enabled"] = False
    assert catalog_search_intent("repuestos de latón", config) == (["repuestos", "laton"], False)
