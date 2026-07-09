from __future__ import annotations

from app.config import Settings
from app.models import ErrorDetail, ProductResult
from app.scrapers.parsers import MYNTRA_BASE_URL, parse_product_page
from app.utils.retry import FetchError, fetch_text


def scrape_product(product_id: str, settings: Settings) -> ProductResult:
    result = ProductResult(product_id=product_id, product_url=f"{MYNTRA_BASE_URL}/{product_id}")
    try:
        response = fetch_text(result.product_url, settings)
        result.product_url = response.final_url
    except FetchError as exc:
        result.errors.append(
            ErrorDetail("product_fetch", exc.code, exc.message, retryable=exc.retryable, attempts=exc.attempts)
        )
        result.status = "failed"
        return result

    try:
        parsed = parse_product_page(response.text)
    except Exception as exc:
        result.errors.append(ErrorDetail("product_parse", "PARSE_ERROR", str(exc), retryable=False, attempts=1))
        result.status = "failed"
        return result

    result.title = parsed.title
    result.description = parsed.description
    result.images = parsed.images
    result.rating = parsed.rating
    result.total_ratings_count = parsed.total_ratings_count
    result.category = parsed.category
    result.category_raw = parsed.category_raw
    result.category_url = parsed.category_url
    result.status = "partial"

    for field_name in ["title", "description", "rating", "total_ratings_count", "category"]:
        if getattr(result, field_name) is None:
            result.warnings.append(f"Missing {field_name}.")
    if not result.images:
        result.warnings.append("Missing images.")

    return result
