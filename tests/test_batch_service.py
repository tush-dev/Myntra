from pathlib import Path

from app.models import ProductResult, to_dict
from app.services import batch_service


def test_batch_continues_after_individual_failure(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n2\n", encoding="utf-8")

    def fake_scrape_product(product_id, settings):
        if product_id == "1":
            return ProductResult(product_id=product_id, title="Ok", images=["x"], category_url="https://x", category="Cat")
        return ProductResult(product_id=product_id, status="failed")

    monkeypatch.setattr(batch_service, "scrape_product", fake_scrape_product)
    monkeypatch.setattr(batch_service, "scrape_category_ads", lambda url, settings: ([], [], []))
    result = batch_service.process_csv(csv_path)
    assert result.summary.total_rows == 2
    assert result.summary.partial == 1
    assert result.summary.failed == 1
    assert to_dict(result)["products"][0]["product_id"] == "1"


def test_product_details_with_missing_category_url_is_partial(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n", encoding="utf-8")

    def fake_scrape_product(product_id, settings):
        return ProductResult(
            product_id=product_id,
            status="partial",
            title="Product",
            description="Description",
            images=["image"],
            rating=4.2,
            total_ratings_count=10,
            category="Handbags",
            category_url=None,
        )

    monkeypatch.setattr(batch_service, "scrape_product", fake_scrape_product)
    result = batch_service.process_csv(csv_path)
    product = result.products[0]
    assert product.status == "partial"
    assert product.title == "Product"
    assert product.errors[0].code == "MISSING_CATEGORY_URL"


def test_sponsored_stage_failure_preserves_product_fields(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n", encoding="utf-8")

    def fake_scrape_product(product_id, settings):
        return ProductResult(
            product_id=product_id,
            status="partial",
            title="Product",
            description="Description",
            images=["image"],
            rating=4.2,
            total_ratings_count=10,
            category="Handbags",
            category_url="https://www.myntra.com/handbags",
        )

    monkeypatch.setattr(batch_service, "scrape_product", fake_scrape_product)
    monkeypatch.setattr(
        batch_service,
        "scrape_category_ads",
        lambda url, settings: ([], [batch_service.ErrorDetail("category_fetch", "HTTP_500", "boom", True, 1)], []),
    )
    result = batch_service.process_csv(csv_path)
    product = result.products[0]
    assert product.status == "partial"
    assert product.title == "Product"
    assert product.errors[0].stage == "category_fetch"


def test_complete_product_failure_is_failed(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n", encoding="utf-8")
    monkeypatch.setattr(batch_service, "scrape_product", lambda product_id, settings: ProductResult(product_id=product_id, status="failed"))
    result = batch_service.process_csv(csv_path)
    assert result.products[0].status == "failed"
