from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.config import Settings, settings as default_settings
from app.models import BatchResult, BatchSummary, ErrorDetail, ProductInput, ProductResult, utc_now_iso
from app.scrapers.category_scraper import scrape_category_ads
from app.scrapers.product_scraper import scrape_product
from app.utils.csv_reader import read_product_csv

logger = logging.getLogger(__name__)


def process_csv(path: str | Path, limit: int | None = None, settings: Settings = default_settings) -> BatchResult:
    source_path = Path(path)
    inputs, invalid_results = read_product_csv(source_path)
    selected_inputs = inputs[:limit] if limit else inputs
    logger.info("batch_start source=%s rows=%s limit=%s", source_path, len(inputs), limit)

    results_by_row: dict[int, ProductResult] = {}
    for invalid in invalid_results:
        if invalid.row_number is not None:
            results_by_row[invalid.row_number] = invalid

    category_cache: dict[str, tuple] = {}
    max_workers = max(1, settings.concurrency)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_process_one, product, settings, category_cache): product for product in selected_inputs}
        for future in as_completed(future_map):
            product = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = ProductResult(product_id=product.product_id, row_number=product.row_number, status="failed")
                result.errors.append(ErrorDetail("product_parse", "UNHANDLED_ERROR", str(exc), False, 1))
            results_by_row[product.row_number] = result

    products = [results_by_row[key] for key in sorted(results_by_row)]
    summary = _summarize(products, selected_inputs, invalid_results)
    logger.info("batch_end success=%s partial=%s failed=%s", summary.successful, summary.partial, summary.failed)
    return BatchResult(utc_now_iso(), source_path.name, summary, products)


def _process_one(product: ProductInput, settings: Settings, category_cache: dict[str, tuple]) -> ProductResult:
    logger.info("product_start row=%s product_id=%s", product.row_number, product.product_id)
    result = scrape_product(product.product_id or "", settings)
    result.row_number = product.row_number
    if product.duplicate:
        result.warnings.append("Duplicate product_id row in input CSV.")

    if result.status != "failed" and result.category_url:
        if result.category_url not in category_cache:
            category_cache[result.category_url] = scrape_category_ads(result.category_url, settings)
        ads, errors, warnings = category_cache[result.category_url]
        result.category_ads = list(ads)
        result.errors.extend(errors)
        result.warnings.extend(warnings)
    elif result.status != "failed":
        result.errors.append(
            ErrorDetail(
                "category_resolution",
                "MISSING_CATEGORY_URL",
                "Could not resolve a public category URL from product breadcrumbs.",
                False,
                1,
            )
        )

    result.status = _status_for(result)
    logger.info("product_end row=%s product_id=%s status=%s", product.row_number, product.product_id, result.status)
    return result


def _status_for(result: ProductResult) -> str:
    if result.status == "failed" and not _has_meaningful_product_data(result):
        return "failed"
    if result.errors and not _has_meaningful_product_data(result):
        return "failed"
    core_complete = all(
        [
            result.title,
            result.description,
            result.images,
            result.rating is not None,
            result.total_ratings_count is not None,
            result.category,
            result.category_url,
        ]
    )
    category_step_ok = not any(error.stage in {"category_fetch", "sponsored_parse"} for error in result.errors)
    return "success" if core_complete and category_step_ok else "partial"


def _has_meaningful_product_data(result: ProductResult) -> bool:
    return any([result.title, result.description, result.images, result.rating is not None, result.category])


def _summarize(
    products: list[ProductResult], selected_inputs: list[ProductInput], invalid_results: list[ProductResult]
) -> BatchSummary:
    ids = [item.product_id for item in selected_inputs if item.product_id]
    summary = BatchSummary(
        total_rows=len(products),
        unique_products=len(set(ids)),
        duplicate_rows=sum(1 for item in selected_inputs if item.duplicate),
        malformed_rows=len(invalid_results),
    )
    for product in products:
        if product.status == "success":
            summary.successful += 1
        elif product.status == "partial":
            summary.partial += 1
        else:
            summary.failed += 1
    return summary
