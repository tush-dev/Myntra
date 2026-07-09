from pathlib import Path

from app.scrapers.parsers import parse_product_page


def test_product_parser_extracts_core_fields() -> None:
    html = Path("tests/fixtures/product_page.html").read_text(encoding="utf-8")
    product = parse_product_page(html)
    assert product.title == "Example Tee"
    assert "Soft cotton" in product.description
    assert product.images == ["https://assets.example/1.jpg", "https://assets.example/2.jpg"]
    assert product.rating == 4.5
    assert product.total_ratings_count == 12
    assert product.category == "Tshirts"
    assert product.category_url == "https://www.myntra.com/tshirts"


def test_product_parser_handles_missing_rating_images_description() -> None:
    product = parse_product_page('<script>window.__myx = {"pdpData":{"name":"Bare Product"}};</script>')
    assert product.title == "Bare Product"
    assert product.description is None
    assert product.images == []
    assert product.rating is None

