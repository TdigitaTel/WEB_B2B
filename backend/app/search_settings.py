"""Configuración persistente de equivalencias del buscador de materiales."""
import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session
from .auth import audit, require_roles
from .db import get_db
from .models import SearchSettings, User
from .search import default_search_config, normalize_query
from .search_resolution import material_groups

router = APIRouter(prefix="/api/v1/store/search-settings", tags=["search"])


class MaterialGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    synonyms: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        value = " ".join(value.split())
        if not re.fullmatch(r"[a-zA-Z0-9 áéíóúüñÁÉÍÓÚÜÑ-]+",value) or not normalize_query(value):
            raise ValueError("Escribe el nombre del material sin comodines ni signos")
        return value

    @field_validator("synonyms")
    @classmethod
    def validate_aliases(cls, values):
        result = []
        for value in values:
            value = " ".join(value.split())
            if not value or len(value)>100 or not re.fullmatch(r"[a-zA-Z0-9 áéíóúüñÁÉÍÓÚÜÑ-]+",value) or not normalize_query(value):
                raise ValueError("Cada equivalencia debe tener de 1 a 100 caracteres, sin comodines")
            if normalize_query(value) not in [normalize_query(item) for item in result]:result.append(value)
        return result


class MeasureEquivalenceIn(BaseModel):
    value: str = Field(min_length=1, max_length=30)
    aliases: list[str] = Field(min_length=1, max_length=20)

    @field_validator("value")
    @classmethod
    def validate_value(cls, value):
        value = normalize_query(value)
        if not re.fullmatch(r"\d+(?:[.,]\d+)?(?: \d+)?(?:/\d+)?", value):
            raise ValueError("Escribe una medida numérica, por ejemplo 1/2, 3/4 o 20")
        if '/' in value and int(value.rsplit('/', 1)[1]) == 0:
            raise ValueError("La medida no puede dividirse entre cero")
        return value

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, values):
        result = []
        seen = set()
        for alias in values:
            alias = " ".join(alias.split())
            key = normalize_query(alias)
            if not key or len(alias) > 100 or not all(c.isalnum() or c in " /.,-'\"″" for c in alias):
                raise ValueError("Cada equivalencia debe tener de 1 a 100 caracteres, sin comodines")
            if key not in seen:
                result.append(alias)
                seen.add(key)
        return result


class SearchSettingsIn(BaseModel):
    enabled: bool = True
    measure_equivalences: list[MeasureEquivalenceIn] | None = Field(default=None, max_length=80)
    material_groups: list[MaterialGroupIn] | None = Field(default=None, max_length=80)
    accessory_terms: list[str] = Field(min_length=1, max_length=80)
    piece_names: list[str] = Field(min_length=1, max_length=80)
    materials: list[str] = Field(min_length=1, max_length=80)

    @field_validator("accessory_terms", "piece_names", "materials")
    @classmethod
    def validate_words(cls, words):
        result = []
        for word in words:
            value = normalize_query(word)
            if len(word) > 60 or not re.fullmatch(r"[a-z0-9]{1,40}", value):
                raise ValueError("Escribe palabras individuales, sin signos ni comodines")
            if value not in result:
                result.append(value)
        return result


    @model_validator(mode="after")
    def distinct_materials(self):
        if self.material_groups is None and set(self.accessory_terms).intersection(self.materials):
            raise ValueError("Un material no puede ser también una palabra general de accesorios")
        seen = {}
        names = set()
        for group in self.material_groups or []:
            name = normalize_query(group.name)
            if name in names:raise ValueError("Hay materiales repetidos")
            names.add(name)
            for alias in [group.name,*group.synonyms]:
                key = normalize_query(alias)
                if key in seen and seen[key] != group.name:
                    raise ValueError(f"El material o equivalencia «{alias}» aparece en más de un grupo")
                if key in self.accessory_terms:
                    raise ValueError("Un material no puede ser también una palabra general")
                seen[key] = group.name
        measures = {}
        targets = set()
        for group in self.measure_equivalences or []:
            if group.value in targets:
                raise ValueError("Hay medidas repetidas; utiliza una sola fila por medida")
            targets.add(group.value)
            for alias in [group.value, *group.aliases]:
                key = normalize_query(alias)
                if key in measures and measures[key] != group.value:
                    raise ValueError(f"La equivalencia «{alias}» pertenece a más de una medida")
                measures[key] = group.value
        return self


def get_search_config(db):
    row = db.get(SearchSettings, 1)
    result = SearchSettingsIn(**(row.config if row else default_search_config())).model_dump()
    result['material_groups'] = material_groups(result)
    result['measure_equivalences'] = result.get('measure_equivalences') or []
    return result


@router.get("")
def read_search_settings(user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    return get_search_config(db)


@router.patch("")
def update_search_settings(data: SearchSettingsIn, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    row = db.get(SearchSettings, 1)
    if row is None:
        row = SearchSettings(id=1)
        db.add(row)
    previous_measures = row.config.get('measure_equivalences', []) if row.config else []
    row.config = {**data.model_dump(), 'measure_equivalences': previous_measures if data.measure_equivalences is None else [group.model_dump() for group in data.measure_equivalences]}
    # Old integrations send only the legacy materials list; derive groups without losing it.
    row.config = {**row.config, 'material_groups': material_groups(row.config)}
    if data.material_groups is not None:
        words = list(dict.fromkeys(normalize_query(group.name).replace('-', ' ').split()[0] for group in data.material_groups))
        row.config = {**row.config, 'materials': words or list(data.materials)}
    audit(db, user, "SEARCH_SETTINGS_UPDATED", "SEARCH_SETTINGS", metadata=row.config)
    db.commit()
    return get_search_config(db)
