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

