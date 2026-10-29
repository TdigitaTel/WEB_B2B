"""Synonyms belong to a classification type, never to individual materials."""
import io
import re
import unicodedata
from zipfile import ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from openpyxl import load_workbook
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import audit, require_roles
from .db import get_db
from .excel_download import ExcelTable
from .models import (MaterialArea, MaterialFamily, MaterialSubfamily, MaterialProductType,
                     ProductTypeSynonyms, Product, User)
from .search import normalize_query
from .search_settings import get_search_config

router = APIRouter(prefix="/api/v1/store/product-type-synonyms", tags=["product-type-synonyms"])
HEADERS = ["CodigoTipoProducto", "TipoProducto", "Categoria", "Familia", "Subfamilia"] + [f"Sinonimo{i}" for i in range(1, 11)]
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10000
operator = require_roles("OPERADOR_TIENDA", "ADMIN")


def alias_key(value):
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)).split())


class SynonymsIn(BaseModel):
    synonyms: list[str] = Field(max_length=10)
    version: int | None = Field(default=None, ge=0)

    @field_validator("synonyms")
    @classmethod
    def validate_synonyms(cls, values):
        result, seen = [], set()
        for value in values:
            value = " ".join(value.split())
            if not value or len(value) > 100 or not any(c.isalnum() for c in value):
                raise ValueError("Cada sinónimo debe tener entre 1 y 100 caracteres y contener letras o números")
            if any(unicodedata.category(c).startswith("C") for c in value) or any(c in value for c in "%_*"):
                raise ValueError("Los sinónimos no admiten controles ni comodines %, _ o *")
            key = alias_key(value)
            if key in seen:
                raise ValueError("Hay sinónimos repetidos (se ignoran mayúsculas y acentos)")
            seen.add(key)
            result.append(value)
        return result


def type_rows(db):
    return db.execute(select(MaterialProductType, MaterialSubfamily.name, MaterialFamily.name, MaterialArea.name, ProductTypeSynonyms)
        .join(MaterialSubfamily, MaterialProductType.subfamily_id == MaterialSubfamily.id)
        .join(MaterialFamily, MaterialSubfamily.family_id == MaterialFamily.id)
        .join(MaterialArea, MaterialFamily.area_id == MaterialArea.id)
        .outerjoin(ProductTypeSynonyms, ProductTypeSynonyms.product_type_id == MaterialProductType.id)
        .order_by(MaterialArea.name, MaterialFamily.name, MaterialSubfamily.name, MaterialProductType.name)).all()


def type_view(row):
    product_type, subfamily, family, area, saved = row
    return {"id": product_type.id, "code": product_type.code, "name": product_type.name,
            "area": area, "family": family, "subfamily": subfamily,
            "synonyms": saved.synonyms if saved else [], "version": saved.version if saved else 0}


@router.get("")
def list_types(user: User = Depends(operator), db: Session = Depends(get_db)):
    return [type_view(row) for row in type_rows(db)]


@router.get("/export.xlsx")
def export_types(user: User = Depends(operator), db: Session = Depends(get_db)):
    table = ExcelTable("Sinonimos", [22, 32, 26, 28, 28] + [24] * 10)
    table.writerow(HEADERS)
    for row in type_rows(db):
        item = type_view(row)
        table.writerow([item[k] for k in ("code", "name", "area", "family", "subfamily")] + item["synonyms"] + [""] * (10 - len(item["synonyms"])))
    return table.response("sinonimos_tipos_producto.xlsx")


def save_aliases(db, product_type_id, synonyms, version=None):
    # Lock the existing parent even when the complementary row does not exist yet.
    parent = db.scalar(select(MaterialProductType).where(MaterialProductType.id == product_type_id).with_for_update())
    if parent is None:
        raise HTTPException(404, "Tipo de producto no encontrado")
    saved = db.get(ProductTypeSynonyms, product_type_id, populate_existing=True)
    current_version = saved.version if saved else 0
    if version is not None and version != current_version:
        raise HTTPException(409, "Los sinónimos cambiaron. Actualiza la lista antes de guardar")
    if saved is None:
        saved = ProductTypeSynonyms(product_type_id=product_type_id, version=0)
        db.add(saved)
    saved.synonyms = synonyms
    saved.version = current_version + 1
    return saved


@router.put("/{product_type_id}")
def update_type(product_type_id: int, data: SynonymsIn, user: User = Depends(operator), db: Session = Depends(get_db)):
    saved = save_aliases(db, product_type_id, data.synonyms, data.version)
    audit(db, user, "PRODUCT_TYPE_SYNONYMS_UPDATED", "MATERIAL_PRODUCT_TYPE", str(product_type_id), metadata={"synonyms": saved.synonyms})
    db.commit()
    return {"id": product_type_id, "synonyms": saved.synonyms, "version": saved.version}


def read_import(content):
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024:
                raise ValueError("El contenido descomprimido del Excel supera 50 MB")
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            sheet = book["Sinonimos"] if "Sinonimos" in book.sheetnames else book.active
            if sheet.max_column and sheet.max_column > 30:
                raise ValueError("El Excel contiene demasiadas columnas. Usa la plantilla descargada")
            rows = sheet.iter_rows()
            first = next(rows, ())
            headers = [str(cell.value or "").strip() for cell in first]
            required = ["CodigoTipoProducto"] + [f"Sinonimo{i}" for i in range(1, 11)]
            if any(headers.count(key) != 1 for key in required):
                raise ValueError("Usa el Excel descargado: código de tipo y columnas Sinonimo1 a Sinonimo10")
            result = []
            for number, cells in enumerate(rows, 2):
                if number > MAX_ROWS + 1:
                    raise ValueError(f"El archivo admite hasta {MAX_ROWS} filas de tipos")
                values = {header: cells[i].value if i < len(cells) else None for i, header in enumerate(headers)}
                if all(value is None or str(value).strip() == "" for value in values.values()):
                    continue
                if any(cell.data_type == "f" for cell in cells):
                    raise ValueError(f"Fila {number}: escribe valores, no fórmulas")
                result.append((number, values))
            return result
        finally:
            book.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else "No se pudo leer el Excel. Usa un archivo .xlsx válido") from exc


@router.post("/import")
def import_types(file: UploadFile = File(...), mode: str = Form("merge"), apply: bool = Form(False),
                       user: User = Depends(operator), db: Session = Depends(get_db)):
    if mode not in {"merge", "replace"}:
        raise HTTPException(422, "Elige añadir o reemplazar sinónimos")
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(422, "Carga un archivo Excel .xlsx")
    content = file.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "El archivo supera 5 MB")
    imported = read_import(content)
    if not imported:
        raise HTTPException(422, "El Excel no contiene tipos de producto")
    by_code = {row[0].code: row[0] for row in type_rows(db)}
    errors, seen, plan = [], set(), []
    # Same lock order as all imports; validate against current saved data before any write.
    ids = sorted({by_code[str(values.get("CodigoTipoProducto") or "").strip()].id for _, values in imported
                  if str(values.get("CodigoTipoProducto") or "").strip() in by_code})
    if apply and ids:
        list(db.scalars(select(MaterialProductType).where(MaterialProductType.id.in_(ids)).order_by(MaterialProductType.id).with_for_update()))
    saved = {row.product_type_id: row for row in db.scalars(select(ProductTypeSynonyms).execution_options(populate_existing=True)).all()}
    for number, values in imported:
        code = str(values.get("CodigoTipoProducto") or "").strip()
        if code in seen:
            errors.append({"row": number, "code": code, "message": "Tipo repetido en el archivo"})
            continue
        seen.add(code)
        product_type = by_code.get(code)
        if product_type is None:
            errors.append({"row": number, "code": code, "message": "Código de tipo de producto desconocido; conserva los ceros iniciales"})
            continue
        current = saved.get(product_type.id)
        incoming = [str(values[f"Sinonimo{i}"]).strip() for i in range(1, 11) if values.get(f"Sinonimo{i}") is not None and str(values[f"Sinonimo{i}"]).strip()]
        try:
            incoming = SynonymsIn(synonyms=incoming).synonyms
            combined = list(current.synonyms) if mode == "merge" and current else []
            for value in incoming:
                if alias_key(value) not in {alias_key(item) for item in combined}:
                    combined.append(value)
            combined = SynonymsIn(synonyms=combined).synonyms
            plan.append({"id": product_type.id, "code": code, "name": product_type.name, "synonyms": combined,
                         "changed": combined != (current.synonyms if current else [])})
        except ValueError:
            errors.append({"row": number, "code": code, "message": "Máximo 10 sinónimos, sin repetidos ni comodines; cada uno de 1 a 100 caracteres"})
    if apply and errors:
        raise HTTPException(422, {"message": "No se guardó ningún cambio. Corrige el Excel", "errors": errors})
    if apply:
        for item in plan:
            if item["changed"]:
                save_aliases(db, item["id"], item["synonyms"])
        audit(db, user, "PRODUCT_TYPE_SYNONYMS_IMPORTED", "MATERIAL_PRODUCT_TYPE", metadata={"mode": mode, "types": len(plan), "changed": sum(item["changed"] for item in plan)})
        db.commit()
    return {"applied": apply, "total": len(imported), "changed": sum(item["changed"] for item in plan), "errors": errors, "items": plan}


def catalog_search_config(db, query):
    """Expand the longest whole synonym phrase; retain extra words and measures."""
    config = get_search_config(db)
    normalized = normalize_query(query)
    if not normalized:
        return config
    matches = []
    for saved in db.scalars(select(ProductTypeSynonyms)).all():
        for alias in saved.synonyms:
            phrase = normalize_query(alias)
            match = re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", normalized) if phrase else None
            if match:
                matches.append((len(phrase), phrase, match.start(), match.end(), saved.product_type_id))
    if not matches:
        return config
    best = max(matches, key=lambda item: (item[0], -item[2]))
    ids = {item[4] for item in matches if item[1:4] == best[1:4]}
    codes = list(db.scalars(select(Product.sku).where(Product.material_product_type_id.in_(ids))).all())
    if codes:
        config["type_synonym"] = {"codes": codes, "query": (normalized[:best[2]] + " " + normalized[best[3]:]).strip()}
    return config
