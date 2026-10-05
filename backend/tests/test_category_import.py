import io

from openpyxl import Workbook

from app.category_import import _canonical_rows, parse_category_file


def test_category_csv_accepts_operator_headers():
    content = (
        "Codigo material;Categoria;Familia;Subfamilia;Tipo producto;Marca;Nombre homologado;Criterios\n"
        "09551;FONTANERIA;VALVULAS;ESFERA;LATON;IVAR;VALVULA ESFERA 1/2;Material y medida\n"
    ).encode("utf-8")

    rows, sheet = parse_category_file("categorias.csv", content)
    valid, errors = _canonical_rows(rows)

    assert sheet == "CSV"
    assert errors == []
    assert valid[0]["code"] == "09551"
    assert valid[0]["area"] == "FONTANERIA"
    assert valid[0]["normalized_name"] == "VALVULA ESFERA 1/2"
    assert valid[0]["criteria"] == "Material y medida"


def test_category_xlsx_preserves_codes_formatted_with_leading_zeroes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([
        "CodigoArticulo", "Nivel1_Area", "Nivel2_Familia",
        "Nivel3_Subfamilia", "Nivel4_TipoProducto", "NombreHomologado",
    ])
    sheet.append([9551, "FONTANERIA", "VALVULAS", "ESFERA", "LATON", "VALVULA"])
    sheet["A2"].number_format = "00000"
    payload = io.BytesIO()
    workbook.save(payload)

    rows, _ = parse_category_file("categorias.xlsx", payload.getvalue())
    valid, errors = _canonical_rows(rows)

    assert errors == []
    assert valid[0]["code"] == "09551"


def test_category_file_reports_missing_values_and_duplicate_codes():
    rows = [
        {
            "CodigoArticulo": "100", "Nivel1_Area": "AREA", "Nivel2_Familia": "FAMILIA",
            "Nivel3_Subfamilia": "SUB", "Nivel4_TipoProducto": "TIPO",
        },
        {
            "CodigoArticulo": "100", "Nivel1_Area": "AREA", "Nivel2_Familia": "FAMILIA",
            "Nivel3_Subfamilia": "SUB", "Nivel4_TipoProducto": "TIPO",
        },
        {
            "CodigoArticulo": "200", "Nivel1_Area": "AREA", "Nivel2_Familia": "",
            "Nivel3_Subfamilia": "SUB", "Nivel4_TipoProducto": "TIPO",
        },
    ]

    valid, errors = _canonical_rows(rows)

    assert [row["code"] for row in valid] == ["100"]
    assert errors[0]["message"] == "Código duplicado en el archivo"
    assert "familia" in errors[1]["message"]
