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
    assert product.category_url_source == "json_ld.breadcrumb.position_3"


def test_product_parser_handles_missing_rating_images_description() -> None:
    product = parse_product_page('<script>window.__myx = {"pdpData":{"name":"Bare Product"}};</script>')
    assert product.title == "Bare Product"
    assert product.description is None
    assert product.images == []
    assert product.rating is None


def test_category_extracted_from_embedded_cross_links_without_breadcrumb() -> None:
    html = """
    <script>window.__myx = {"pdpData":{
      "name":"Crosslink Product",
      "analytics":{"articleType":"Handbags"},
      "crossLinks":[{"title":"More Handbags","url":"handbags?f=Gender:women&luxuryType=nonluxury"}]
    }};</script>
    """
    product = parse_product_page(html)
    assert product.category == "Handbags"
    assert product.category_url == "https://www.myntra.com/handbags"
    assert product.category_url_source == "pdp.crossLinks"


def test_blocked_challenge_page_detection() -> None:
    html = "<html><head><title>Access Denied</title></head><body>Verify you are human</body></html>"
    product = parse_product_page(html)
    assert product.page_type == "challenge"


def test_client_shell_page_detection() -> None:
    html = "<html><head><title>Myntra</title></head><body><div id=\"mountRoot\"></div><script src=\"app.js\"></script></body></html>"
    product = parse_product_page(html)
    assert product.page_type == "client_shell"
