from pathlib import Path

from app.utils.csv_reader import read_product_csv


def test_csv_reader_detects_duplicates_empty_and_malformed(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    path.write_text("product_id\n123\n\nabc\n123\n", encoding="utf-8")
    products, invalid = read_product_csv(path)
    assert [item.product_id for item in products] == ["123", "123"]
    assert all(item.duplicate for item in products)
    assert [item.errors[0].code for item in invalid] == ["EMPTY_PRODUCT_ID", "MALFORMED_PRODUCT_ID"]


def test_missing_product_id_column(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    path.write_text("id\n123\n", encoding="utf-8")
    products, invalid = read_product_csv(path)
    assert products == []
    assert invalid[0].errors[0].code == "MISSING_PRODUCT_ID_COLUMN"

