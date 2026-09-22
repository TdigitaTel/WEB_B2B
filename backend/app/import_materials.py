import csv
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

from sqlalchemy import delete, select, update

from .bootstrap import main as bootstrap
from .db import SessionLocal
from .models import (
    Brand, Category, MaterialArea, MaterialFamily, MaterialImportRow,
    MaterialProductType, MaterialSubfamily, Product, SyncStatus,
)

SOURCE_FILE = "Lista_de_materiales_CLASIFICADA.xlsx"
SOURCE_SHEET = "Sheet1"


def clean(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def slug(value: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFD", value.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:100]


def fake_ean(code: str) -> str:
    number = int(hashlib.sha1(code.encode("utf-8")).hexdigest()[:14], 16) % 10**11
    return f"29{number:011d}"


def technical_attributes(row: dict[str, str]) -> dict[str, str]:
    mapping = {
        "serie_modelo": "Serie_Modelo", "sistema_aplicacion": "Sistema_Aplicacion",
        "material": "Material", "medida_diametro": "Medida_Diametro",
        "tipo_conexion": "TipoConexion", "potencia_capacidad": "Potencia_Capacidad",
        "formato_presentacion": "Formato_Presentacion", "atributos_tecnicos": "AtributosTecnicos",
        "observaciones": "Observaciones",
    }
    return {key: clean(row[source]) for key, source in mapping.items() if clean(row[source])}


def main(csv_path: str) -> None:
    bootstrap()
    with Path(csv_path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    unique_rows: dict[str, dict[str, str]] = {}
    for row in rows:
        unique_rows.setdefault(clean(row["CodigoArticulo"]), row)

    areas = sorted({clean(r["Nivel1_Area"]) or "SIN CLASIFICAR" for r in unique_rows.values()})
    families = sorted({(clean(r["Nivel1_Area"]) or "SIN CLASIFICAR", clean(r["Nivel2_Familia"]) or "SIN CLASIFICAR") for r in unique_rows.values()})
    subfamilies = sorted({(clean(r["Nivel1_Area"]) or "SIN CLASIFICAR", clean(r["Nivel2_Familia"]) or "SIN CLASIFICAR", clean(r["Nivel3_Subfamilia"]) or "SIN CLASIFICAR") for r in unique_rows.values()})
    product_types = sorted({(clean(r["Nivel1_Area"]) or "SIN CLASIFICAR", clean(r["Nivel2_Familia"]) or "SIN CLASIFICAR", clean(r["Nivel3_Subfamilia"]) or "SIN CLASIFICAR", clean(r["Nivel4_TipoProducto"]) or "SIN CLASIFICAR") for r in unique_rows.values()})

    with SessionLocal() as db:
        area_map = {}
        for index, name in enumerate(areas, 1):
            item = db.scalar(select(MaterialArea).where(MaterialArea.name == name))
            if not item:
                item = MaterialArea(code=f"ARE-{index:03d}", name=name); db.add(item); db.flush()
            area_map[name] = item
        family_map = {}
        for index, (area, name) in enumerate(families, 1):
            item = db.scalar(select(MaterialFamily).where(MaterialFamily.area_id == area_map[area].id, MaterialFamily.name == name))
            if not item:
                item = MaterialFamily(code=f"FAM-{index:03d}", name=name, area_id=area_map[area].id); db.add(item); db.flush()
            family_map[(area, name)] = item
        subfamily_map = {}
        for index, (area, family, name) in enumerate(subfamilies, 1):
            parent = family_map[(area, family)]
            item = db.scalar(select(MaterialSubfamily).where(MaterialSubfamily.family_id == parent.id, MaterialSubfamily.name == name))
            if not item:
                item = MaterialSubfamily(code=f"SUB-{index:03d}", name=name, family_id=parent.id); db.add(item); db.flush()
            subfamily_map[(area, family, name)] = item
        type_map = {}
        for index, (area, family, subfamily, name) in enumerate(product_types, 1):
            parent = subfamily_map[(area, family, subfamily)]
            item = db.scalar(select(MaterialProductType).where(MaterialProductType.subfamily_id == parent.id, MaterialProductType.name == name))
            if not item:
                item = MaterialProductType(code=f"TIP-{index:03d}", name=name, subfamily_id=parent.id); db.add(item); db.flush()
            type_map[(area, family, subfamily, name)] = item

        brand_map = {}
        for name in sorted({clean(r["Marca"]) or "SIN MARCA" for r in unique_rows.values()}):
            item = db.scalar(select(Brand).where(Brand.name == name))
            if not item:
                item = Brand(name=name); db.add(item); db.flush()
            brand_map[name] = item
        category_map = {}
        for _, family in families:
            if family not in category_map:
                item = db.scalar(select(Category).where(Category.name == family))
                if not item:
                    item = Category(name=family, slug=f"material-{slug(family)}"); db.add(item); db.flush()
                category_map[family] = item

        db.execute(update(Product).where(Product.source_system.is_(None)).values(active=False, source_system="SYNTHETIC_MVP"))
        db.execute(delete(MaterialImportRow).where(MaterialImportRow.source_file == SOURCE_FILE))
        existing = {p.sku: p for p in db.scalars(select(Product)).all()}
        imported = {}
        for code, row in unique_rows.items():
            area = clean(row["Nivel1_Area"]) or "SIN CLASIFICAR"
            family = clean(row["Nivel2_Familia"]) or "SIN CLASIFICAR"
            subfamily = clean(row["Nivel3_Subfamilia"]) or "SIN CLASIFICAR"
            product_type = clean(row["Nivel4_TipoProducto"]) or "SIN CLASIFICAR"
            name = clean(row["NombreNormalizado"]) or clean(row["DescripcionArticulo"])
            original = clean(row["DescripcionArticulo"])
            brand = clean(row["Marca"]) or "SIN MARCA"
            status = clean(row["EstadoClasificacion"])
            attrs = technical_attributes(row)
            product = existing.get(code)
            if not product:
                product = Product(sku=code, erp_id=code, ean=fake_ean(code), list_price=0, pack_size=1, tax_rate=21, sync_status=SyncStatus.pending)
                db.add(product); existing[code] = product
            product.manufacturer_reference = clean(row["ReferenciaFabricante"])
            product.brand_id = brand_map[brand].id
            product.category_id = category_map[family].id
            product.material_area_id = area_map[area].id
            product.material_family_id = family_map[(area, family)].id
            product.material_subfamily_id = subfamily_map[(area, family, subfamily)].id
            product.material_product_type_id = type_map[(area, family, subfamily, product_type)].id
            product.family, product.subfamily = family, subfamily
            product.original_description = original
            product.short_description = name[:240]
            product.commercial_description = name
            product.technical_description = clean(row["AtributosTecnicos"])
            product.unit = clean(row["UnidadMedida"]) or "UD"
            product.attributes = attrs
            product.normalized_search = " ".join(filter(None, [code, name, original, area, family, subfamily, product_type, brand, *attrs.values()])).lower()
            product.active = not status.startswith("EXCLUIDO")
            product.classification_status = status
            product.classification_reason = clean(row["MotivoRevision"])
            product.classification_confidence = clean(row["ConfianzaClasificacion"])
            product.source_system = "EXCEL_CLASIFICADO"
            imported[code] = product
        db.flush()
        for source_row, row in enumerate(rows, 2):
            code = clean(row["CodigoArticulo"])
            db.add(MaterialImportRow(source_file=SOURCE_FILE, source_sheet=SOURCE_SHEET, source_row=source_row, article_code=code, product_id=imported[code].id, raw_data=row))
        db.commit()
    print({"source_rows": len(rows), "unique_materials": len(unique_rows), "duplicate_rows_preserved": len(rows)-len(unique_rows), "areas": len(areas), "families": len(families), "subfamilies": len(subfamilies), "product_types": len(product_types)})


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/app/data/materials_classified.csv")
