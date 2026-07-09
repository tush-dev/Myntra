from __future__ import annotations

from app.config import Settings
from app.models import ErrorDetail, SponsoredResult
from app.scrapers.parsers import parse_category_ads
from app.utils.retry import FetchError, fetch_text


def scrape_category_ads(category_url: str, settings: Settings) -> tuple[list[SponsoredResult], list[ErrorDetail], list[str]]:
    warnings: list[str] = []
    try:
        response = fetch_text(category_url, settings)
    except FetchError as exc:
        return [], [ErrorDetail("category_fetch", exc.code, exc.message, exc.retryable, exc.attempts)], warnings

    try:
        ads = parse_category_ads(response.text, limit=3)
    except Exception as exc:
        return [], [ErrorDetail("sponsored_parse", "PARSE_ERROR", str(exc), False, 1)], warnings

    if not ads:
        warnings.append("No PLA/sponsored results were found in public listing state.")
    return ads, [], warnings

