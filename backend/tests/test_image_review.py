from scripts.process_missing_product_images import read_input


def test_image_review_file_requires_explicit_approval(tmp_path):
    source = tmp_path / "imagenes.csv"
    source.write_text(
        "codigo_material,image_path,proveedor,aprobado\n"
        "00123,imagenes/00123.jpg,Proveedor oficial,NO\n"
        "00456,imagenes/00456.png,Proveedor oficial,SI\n",
        encoding="utf-8",
    )

    rows = read_input(source)

    assert [row.sku for row in rows] == ["00123", "00456"]
    assert rows[0].approved is False
    assert rows[1].approved is True

