import time
import threading
from pathlib import Path

from app.config import Settings
from app.models import ErrorDetail, ProductResult
from app.services import batch_service
from app.scrapers import category_scraper, product_scraper


def test_concurrency_limit_respected(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n2\n3\n4\n5\n", encoding="utf-8")

    active = []
    max_active = []
    lock = threading.Lock()

    def slow_scrape(product_id, settings):
        with lock:
            active.append(product_id)
            max_active.append(len(active))
        time.sleep(0.15)
        with lock:
            active.remove(product_id)
        return ProductResult(
            product_id=product_id,
            title=f"Product {product_id}",
            images=["img"],
            category_url=f"https://example.com/{product_id}",
            category="Cat",
            rating=4.0,
            total_ratings_count=10,
            description="desc",
        )

    monkeypatch.setattr(product_scraper, "scrape_product", slow_scrape)
    monkeypatch.setattr(category_scraper, "scrape_category_ads", lambda url, s: ([], [], []))

    settings = Settings(concurrency=2, batch_timeout=30)
    result = batch_service.process_csv(csv_path, settings=settings)

    assert len(result.products) == 5
    assert max(max_active) <= 2


def test_result_order_matches_input_order(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n900\n800\n700\n", encoding="utf-8")

    def fake_scrape(product_id, settings):
        return ProductResult(
            product_id=product_id,
            title=f"P{product_id}",
            images=["img"],
            category_url="https://x",
            category="Cat",
            rating=4.0,
            total_ratings_count=10,
            description="desc",
        )

    monkeypatch.setattr(product_scraper, "scrape_product", fake_scrape)
    monkeypatch.setattr(category_scraper, "scrape_category_ads", lambda url, s: ([], [], []))

    result = batch_service.process_csv(csv_path)
    ids = [p.product_id for p in result.products]
    assert ids == ["900", "800", "700"]


def test_category_cache_shared_across_products(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n2\n3\n", encoding="utf-8")

    fetch_count = {"n": 0}

    def fake_scrape(product_id, settings):
        return ProductResult(
            product_id=product_id,
            status="partial",
            title=f"P{product_id}",
            images=["img"],
            category_url="https://same-category.com",
            category="Cat",
            rating=4.0,
            total_ratings_count=10,
            description="desc",
        )

    def counting_category(url, settings):
        fetch_count["n"] += 1
        time.sleep(0.05)
        return ([], [], [])

    monkeypatch.setattr(product_scraper, "scrape_product", fake_scrape)
    monkeypatch.setattr(category_scraper, "scrape_category_ads", counting_category)

    result = batch_service.process_csv(csv_path, settings=Settings(concurrency=1))
    assert len(result.products) == 3
    assert fetch_count["n"] == 1


def test_duplicate_product_ids_deduplicated(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n1\n1\n2\n", encoding="utf-8")

    call_count = {"n": 0}

    def counting_scrape(product_id, settings):
        call_count["n"] += 1
        return ProductResult(
            product_id=product_id,
            status="partial",
            title=f"P{product_id}",
            images=["img"],
            category_url="https://x",
            category="Cat",
            rating=4.0,
            total_ratings_count=10,
            description="desc",
        )

    monkeypatch.setattr(product_scraper, "scrape_product", counting_scrape)
    monkeypatch.setattr(category_scraper, "scrape_category_ads", lambda url, s: ([], [], []))

    result = batch_service.process_csv(csv_path)
    assert call_count["n"] == 2
    assert len(result.products) == 4
    dup_warns = [w for p in result.products for w in p.warnings if "Duplicate" in w]
    assert len(dup_warns) == 2
    assert result.summary.duplicate_rows == 3


def test_timeout_isolation_per_product(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n2\n", encoding="utf-8")

    def selective_slow(product_id, settings):
        if product_id == "1":
            time.sleep(0.5)
        return ProductResult(
            product_id=product_id,
            title=f"P{product_id}",
            images=["img"],
            category_url="https://x",
            category="Cat",
            rating=4.0,
            total_ratings_count=10,
            description="desc",
        )

    monkeypatch.setattr(product_scraper, "scrape_product", selective_slow)
    monkeypatch.setattr(category_scraper, "scrape_category_ads", lambda url, s: ([], [], []))

    result = batch_service.process_csv(csv_path, settings=Settings(batch_timeout=1.0, concurrency=1))

    assert len(result.products) == 2


def test_category_cache_failure_cached(monkeypatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("product_id\n1\n2\n", encoding="utf-8")

    call_count = {"n": 0}

    def fake_scrape(product_id, settings):
        return ProductResult(
            product_id=product_id,
            status="partial",
            title=f"P{product_id}",
            images=["img"],
            category_url="https://failing-category.com",
            category="Cat",
            rating=4.0,
            total_ratings_count=10,
            description="desc",
        )

    def failing_category(url, settings):
        call_count["n"] += 1
        return ([], [ErrorDetail("category_fetch", "HTTP_500", "boom", True, 1)], [])

    monkeypatch.setattr(product_scraper, "scrape_product", fake_scrape)
    monkeypatch.setattr(category_scraper, "scrape_category_ads", failing_category)

    result = batch_service.process_csv(csv_path, settings=Settings(concurrency=1))
    assert call_count["n"] == 1
    for p in result.products:
        assert any(e.code == "HTTP_500" for e in p.errors)


def test_session_reuse_across_requests() -> None:
    from app.utils.retry import _get_session, CurlSession
    if CurlSession is None:
        return
    s1 = _get_session()
    s2 = _get_session()
    assert s1 is s2
