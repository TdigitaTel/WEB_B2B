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
