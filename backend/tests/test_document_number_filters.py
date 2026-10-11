import pytest
from app.erp_db import _document_filters

@pytest.mark.parametrize('prefix',['Albaran','Factura'])
def test_document_lookup_accepts_number_or_complete_reference(prefix):
    sql, params = _document_filters('d',prefix,'12345')
    assert params == ['12345']
    assert f'd.Numero{prefix}' in sql
    assert f'd.Ejercicio{prefix}' not in sql
    for reference in ['2026-AL-12345','2026/AL/12345','2026~AL~12345']:
        sql, params = _document_filters('d',prefix,reference)
        assert params == ['2026','AL','12345']
        assert all(f'd.{field}{prefix}' in sql for field in ['Ejercicio','Serie','Numero'])
