"""Equivalencias del lenguaje habitual de compra de material."""
import re
import unicodedata


def normalize_query(query: str) -> str:
    value = ''.join(c for c in unicodedata.normalize('NFD', query.lower()) if not unicodedata.combining(c))
    value = value.replace('½', '1/2').replace('¼', '1/4').replace('¾', '3/4')
    for phrase, measure in (
        (r'tres\s+cuartos', '3/4'),
        (r'(?:un\s+)?cuarto', '1/4'),
        (r'(?:una\s+)?media(?:\s+pulgada)?', '1/2'),
        (r'medio(?:\s+pulgada)?', '1/2'),
    ):
        value = re.sub(r'\b' + phrase + r'\b', measure, value)
    value = re.sub(r'(\d)\s*/\s*(\d)', r'\1/\2', value)
    value = re.sub(r'\b(?:de|del|la|el|pulgadas?)\b', ' ', value)
    value = value.replace('"', '').replace('″', '')
    return ' '.join(value.split())
