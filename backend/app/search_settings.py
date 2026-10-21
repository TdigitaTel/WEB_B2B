"""Configuración persistente de equivalencias del buscador de materiales."""
import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session
from .auth import audit, require_roles
from .db import get_db
from .models import SearchSettings, User
from .search import default_search_config, normalize_query

router = APIRouter(prefix="/api/v1/store/search-settings", tags=["search"])


class SearchSettingsIn(BaseModel):
    enabled: bool = True
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
        if set(self.accessory_terms).intersection(self.materials):
            raise ValueError("Un material no puede ser también una palabra general de accesorios")
        return self


def get_search_config(db):
    row = db.get(SearchSettings, 1)
    return SearchSettingsIn(**row.config).model_dump() if row else default_search_config()


@router.get("")
def read_search_settings(user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    return get_search_config(db)


@router.patch("")
def update_search_settings(data: SearchSettingsIn, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    row = db.get(SearchSettings, 1)
    if row is None:
        row = SearchSettings(id=1)
        db.add(row)
    row.config = data.model_dump()
    audit(db, user, "SEARCH_SETTINGS_UPDATED", "SEARCH_SETTINGS", metadata=row.config)
    db.commit()
    return row.config
