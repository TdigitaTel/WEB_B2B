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


# Solo se amplía el término genérico cuando el cliente también indica material.
ACCESSORY_NAMES = (
    "accesorio", "accesorios", "codo", "codos", "te", "tes", "racor", "racores",
    "manguito", "manguitos", "machon", "machones", "entronque", "entronques",
    "reduccion", "reducciones", "tapon", "tapones", "union", "uniones",
    "enlace", "enlaces", "adaptador", "adaptadores", "curva", "curvas",
    "cruz", "cruces", "brida", "bridas", "casquillo", "casquillos",
    "tuerca", "tuercas", "collarin", "collarines", "colector", "colectores",
)
MATERIAL_TERMS = frozenset(("laton", "cobre", "inox", "inoxidable", "pvc", "ppr", "pex", "polietileno", "acero"))


def catalog_search_intent(query: str) -> tuple[list[str], bool]:
    """Devuelve palabras obligatorias y si se buscan accesorios por material."""
    terms = normalize_query(query).split()
    accessories = any(term in ("accesorio", "accesorios") for term in terms)
    by_material = accessories and any(term in MATERIAL_TERMS for term in terms)
    if by_material:
        terms = [term for term in terms if term not in ("accesorio", "accesorios")]
    return terms, by_material
