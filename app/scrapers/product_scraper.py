from __future__ import annotations

import logging
import re

from app.config import Settings
from app.models import ErrorDetail, ProductResult
from app.scrapers.parsers import MYNTRA_BASE_URL, parse_product_page, visible_text_preview
from app.utils.retry import FetchError, fetch_text

logger = logging.getLogger(__name__)


def scrape_product(product_id: str, settings: Settings) -> ProductResult:
    result = ProductResult(product_id=product_id, product_url=_product_url(product_id))
    try:
        response = fetch_text(result.product_url, settings)
        result.product_url = response.final_url
        result.fetch_status = response.status
        result.fetch_content_type = response.content_type
        result.fetch_bytes = response.byte_count
        result.html_title = _page_title(response.text)
        result.visible_text_preview = visible_text_preview(response.text)
        logger.info(
            "product_fetch product_id=%s status=%s final_url=%s content_type=%s bytes=%s title=%r",
            product_id,
            response.status,
            response.final_url,
            response.content_type,
            response.byte_count,
            result.html_title,
        )
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
    result.category_source = parsed.category_source
    result.category_url_source = parsed.category_url_source
    result.page_type = parsed.page_type

    logger.info(
        "product_parse product_id=%s page_type=%s fields=%s category=%r category_url=%r category_source=%s category_url_source=%s",
        product_id,
        result.page_type,
        {
            "title": bool(result.title),
            "description": bool(result.description),
            "images": len(result.images),
            "rating": result.rating is not None,
            "total_ratings_count": result.total_ratings_count is not None,
        },
        result.category,
        result.category_url,
        result.category_source,
        result.category_url_source,
    )

    if result.page_type == "challenge":
        result.errors.append(
            ErrorDetail(
                "product_fetch",
                "CHALLENGE_PAGE",
                "Remote server returned a challenge or bot-detection page instead of product HTML.",
                retryable=True,
                attempts=response.attempts,
            )
        )
        result.status = "failed"
        return result
    if result.page_type != "product" and not any([result.title, result.description, result.images]):
        code = _page_type_error_code(result.page_type)
        result.errors.append(
            ErrorDetail(
                "product_parse",
                code,
                (
                    "Fetched page did not contain recognizable Myntra product data. "
                    f"page_type={result.page_type}; status={result.fetch_status}; "
                    f"bytes={result.fetch_bytes}; title={result.html_title!r}; "
                    f"visible_text={result.visible_text_preview!r}"
                ),
                retryable=False,
                attempts=1,
            )
        )
        result.status = "failed"
        return result

    result.status = "partial"

    for field_name in ["title", "description", "rating", "total_ratings_count", "category"]:
        if getattr(result, field_name) is None:
            result.warnings.append(f"Missing {field_name}.")
    if not result.images:
        result.warnings.append("Missing images.")

    return result


def _page_title(html_text: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    return match.group(1).strip() if match else None


def _page_type_error_code(page_type: str | None) -> str:
    return {
        "empty": "EMPTY_PAGE",
        "client_shell": "CLIENT_RENDERED_SHELL",
        "home_or_shell": "NON_PRODUCT_MYNTRA_PAGE",
        "home": "NON_PRODUCT_MYNTRA_PAGE",
        "search": "SEARCH_PAGE_INSTEAD_OF_PRODUCT",
        "listing": "LISTING_PAGE_INSTEAD_OF_PRODUCT",
    }.get(page_type or "unknown", "UNKNOWN_NON_PRODUCT_PAGE")


def _product_url(product_id: str) -> str:
    return f"{MYNTRA_BASE_URL}/product/product/product/{product_id}/buy"
