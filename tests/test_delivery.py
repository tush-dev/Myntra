from pathlib import Path

from app.config import Settings
from app.models import DeliveryEstimate, ProductResult, to_dict
from app.scrapers.delivery import check_delivery_for_product
from app.services import batch_service


def test_delivery_disabled_by_default(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n", encoding="utf-8")

    def fake_scrape_product(product_id, settings):
        return ProductResult(
            product_id=product_id,
            status="partial",
            title="Product",
            description="Desc",
            images=["img"],
            rating=4.0,
            total_ratings_count=10,
            category="Cat",
            category_url="https://x",
        )

    monkeypatch.setattr(batch_service, "scrape_product", fake_scrape_product)
    monkeypatch.setattr(batch_service, "scrape_category_ads", lambda url, settings: ([], [], []))
    result = batch_service.process_csv(csv_path)
    product = result.products[0]
    assert product.delivery_estimates == []


def test_delivery_enabled_adds_five_city_entries(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n", encoding="utf-8")

    def fake_scrape_product(product_id, settings):
        return ProductResult(
            product_id=product_id,
            status="partial",
            title="Product",
            description="Desc",
            images=["img"],
            rating=4.0,
            total_ratings_count=10,
            category="Cat",
            category_url="https://x",
        )

    def fake_check_delivery(product_id, settings):
        return [
            DeliveryEstimate(city="Bengaluru", pincode="560001", status="unavailable"),
            DeliveryEstimate(city="Mumbai", pincode="400001", status="unavailable"),
            DeliveryEstimate(city="Delhi", pincode="110001", status="unavailable"),
            DeliveryEstimate(city="Ahmedabad", pincode="380001", status="unavailable"),
            DeliveryEstimate(city="Kolkata", pincode="700001", status="unavailable"),
        ]

    monkeypatch.setattr(batch_service, "scrape_product", fake_scrape_product)
    monkeypatch.setattr(batch_service, "scrape_category_ads", lambda url, settings: ([], [], []))
    monkeypatch.setattr(batch_service, "check_delivery_for_product", fake_check_delivery)

    settings = Settings(include_delivery=True)
    result = batch_service.process_csv(csv_path, settings=settings)
    product = result.products[0]
    assert len(product.delivery_estimates) == 5
    cities = [e.city for e in product.delivery_estimates]
    assert cities == ["Bengaluru", "Mumbai", "Delhi", "Ahmedabad", "Kolkata"]


def test_delivery_failure_preserves_product_status(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n", encoding="utf-8")

    def fake_scrape_product(product_id, settings):
        return ProductResult(
            product_id=product_id,
            status="partial",
            title="Product",
            description="Desc",
            images=["img"],
            rating=4.0,
            total_ratings_count=10,
            category="Cat",
            category_url="https://x",
        )

    def failing_check_delivery(product_id, settings):
        raise RuntimeError("Delivery API exploded")

    monkeypatch.setattr(batch_service, "scrape_product", fake_scrape_product)
    monkeypatch.setattr(batch_service, "scrape_category_ads", lambda url, settings: ([], [], []))
    monkeypatch.setattr(batch_service, "check_delivery_for_product", failing_check_delivery)

    settings = Settings(include_delivery=True)
    result = batch_service.process_csv(csv_path, settings=settings)
    product = result.products[0]
    assert product.status == "success"
    assert product.delivery_estimates == []
    assert any("Delivery check failed" in w for w in product.warnings)


def test_json_serialization_includes_delivery_estimates(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n", encoding="utf-8")

    def fake_scrape_product(product_id, settings):
        return ProductResult(
            product_id=product_id,
            status="partial",
            title="Product",
            description="Desc",
            images=["img"],
            rating=4.0,
            total_ratings_count=10,
            category="Cat",
            category_url="https://x",
        )

    def fake_check_delivery(product_id, settings):
        return [
            DeliveryEstimate(city="Bengaluru", pincode="560001", status="success", estimated_days=3),
        ]

    monkeypatch.setattr(batch_service, "scrape_product", fake_scrape_product)
    monkeypatch.setattr(batch_service, "scrape_category_ads", lambda url, settings: ([], [], []))
    monkeypatch.setattr(batch_service, "check_delivery_for_product", fake_check_delivery)

    settings = Settings(include_delivery=True)
    result = batch_service.process_csv(csv_path, settings=settings)
    serialized = to_dict(result)
    product = serialized["products"][0]
    assert "delivery_estimates" in product
    assert len(product["delivery_estimates"]) == 1
    est = product["delivery_estimates"][0]
    assert est["city"] == "Bengaluru"
    assert est["pincode"] == "560001"
    assert est["status"] == "success"
    assert est["estimated_days"] == 3
