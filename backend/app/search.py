"""Equivalencias del lenguaje habitual de compra de material."""
import re
import unicodedata


def normalize_query(query: str, measure_equivalences: list[dict] | None = None) -> str:
    """Normalize spelling, then apply only the measure aliases supplied by settings."""
    value = ''.join(c for c in unicodedata.normalize('NFD', query.lower()) if not unicodedata.combining(c))
    value = re.sub(r'(\d)\s*/\s*(\d)', r'\1/\2', value)
    value = re.sub(r'\b(?:de|del|la|el|pulgadas?)\b', ' ', value)
    value = value.replace('"', '').replace('″', '')
    value = ' '.join(value.split())
    aliases = {}
    for group in measure_equivalences or []:
        target = normalize_query(group['value'])
        for alias in group['aliases']:
            key = normalize_query(alias)
            if key:
                aliases[key] = target
    if aliases:
        # One substitution prevents chained/circular replacements. Longest phrase wins.
        pattern = r'(?<!\w)(?:' + '|'.join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True)) + r')(?!\w)'
        value = re.sub(pattern, lambda match: aliases[match.group()], value)
    return value


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


DEFAULT_ACCESSORY_TERMS = ("accesorio", "accesorios", "pieza", "piezas", "componente", "componentes", "conexion", "conexiones", "racoreria", "fitting", "fittings")


def default_search_config() -> dict:
    return {"enabled": True, "accessory_terms": list(DEFAULT_ACCESSORY_TERMS),
            "piece_names": list(ACCESSORY_NAMES), "materials": sorted(MATERIAL_TERMS)}


def catalog_search_intent(query: str, config: dict | None = None) -> tuple[list[str], bool]:
    """Devuelve palabras obligatorias y si se buscan accesorios por material."""
    config = config if config is not None else default_search_config()
    terms = normalize_query(query, config.get("measure_equivalences")).split()
    generic_terms = set(config["accessory_terms"])
    accessories = any(term in generic_terms for term in terms)
    by_material = config["enabled"] and accessories and any(term in config["materials"] for term in terms)
    if by_material:
        terms = [term for term in terms if term not in generic_terms]
    return terms, by_material
