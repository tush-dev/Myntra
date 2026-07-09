from __future__ import annotations

import logging

from app.config import Settings
from app.models import ErrorDetail, SponsoredResult
from app.scrapers.parsers import parse_category_ads
from app.utils.retry import FetchError, fetch_text

logger = logging.getLogger(__name__)


def scrape_category_ads(category_url: str, settings: Settings) -> tuple[list[SponsoredResult], list[ErrorDetail], list[str]]:
    warnings: list[str] = []
    try:
        response = fetch_text(category_url, settings)
        logger.info(
            "category_fetch category_url=%s status=%s final_url=%s content_type=%s bytes=%s",
            category_url,
            response.status,
            response.final_url,
            response.content_type,
            response.byte_count,
        )
    except FetchError as exc:
        return [], [ErrorDetail("category_fetch", exc.code, exc.message, exc.retryable, exc.attempts)], warnings

    try:
        ads = parse_category_ads(response.text, limit=3)
        logger.info("sponsored_parse category_url=%s sponsored_count=%s", category_url, len(ads))
    except Exception as exc:
        return [], [ErrorDetail("sponsored_parse", "PARSE_ERROR", str(exc), False, 1)], warnings

    if not ads:
        warnings.append("No PLA/sponsored results were found in public listing state.")
    return ads, [], warnings
