from __future__ import annotations

import copy
import logging
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from app.config import Settings, settings as default_settings
from app.models import BatchResult, BatchSummary, ErrorDetail, ProductInput, ProductResult, utc_now_iso
from app.scrapers import category_scraper, delivery, product_scraper
from app.utils.csv_reader import read_product_csv

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 0.3


def process_csv(path: str | Path, limit: int | None = None, settings: Settings = default_settings) -> BatchResult:
    source_path = Path(path)
    inputs, invalid_results = read_product_csv(source_path)
    selected_inputs = inputs[:limit] if limit else inputs
    logger.info("batch_start source=%s rows=%s limit=%s", source_path, len(inputs), limit)

    results_by_row: dict[int, ProductResult] = {}
    for invalid in invalid_results:
        if invalid.row_number is not None:
            results_by_row[invalid.row_number] = invalid

    id_to_first_row: dict[str, int] = {}
    duplicate_rows: dict[str, list[int]] = {}
    unique_inputs: list[ProductInput] = []
    all_inputs_by_row: dict[int, ProductInput] = {}
    for product in selected_inputs:
        all_inputs_by_row[product.row_number] = product
        pid = product.product_id
        if not pid:
            unique_inputs.append(product)
            continue
        if pid in id_to_first_row:
            duplicate_rows.setdefault(pid, []).append(product.row_number)
            product.duplicate = True
        else:
            id_to_first_row[pid] = product.row_number
            unique_inputs.append(product)

    category_cache: dict[str, tuple] = {}
    category_lock = threading.Lock()
    max_workers = max(1, settings.concurrency)
    deadline = time.monotonic() + max(settings.batch_timeout, 0.001)
    completed = 0
    total = len(unique_inputs)
    completed_lock = threading.Lock()

    def _on_done(future, product):
        nonlocal completed
        try:
            result = future.result()
        except Exception as exc:
            result = ProductResult(product_id=product.product_id, row_number=product.row_number, status="failed")
            result.errors.append(ErrorDetail("product_parse", "UNHANDLED_ERROR", str(exc), False, 1))
        results_by_row[product.row_number] = result
        pid = product.product_id
        if pid and pid in duplicate_rows:
            for dup_row in duplicate_rows[pid]:
                dup_result = copy.deepcopy(result)
                dup_result.row_number = dup_row
                dup_result.warnings = list(result.warnings) + ["Duplicate product_id row in input CSV."]
                results_by_row[dup_row] = dup_result
        with completed_lock:
            completed += 1
            logger.info("progress %d/%d product_id=%s status=%s", completed, total, product.product_id, result.status)

    executor = ThreadPoolExecutor(max_workers=max_workers)
    future_map = {}
    for product in unique_inputs:
        future = executor.submit(_process_one, product, settings, category_cache, category_lock)
        future_map[future] = product
        future.add_done_callback(lambda f, p=product: _on_done(f, p))

    try:
        while future_map:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("batch_timeout pending_products=%s timeout=%ss", len(future_map), settings.batch_timeout)
                break
            done, _ = wait(
                future_map,
                timeout=min(POLL_INTERVAL_SECONDS, remaining),
                return_when=FIRST_COMPLETED,
            )
            for future in done:
                future_map.pop(future, None)
    finally:
        for future, product in list(future_map.items()):
            future.cancel()
            if product.row_number not in results_by_row:
                result = ProductResult(product_id=product.product_id, row_number=product.row_number, status="failed")
                result.errors.append(
                    ErrorDetail(
                        "product_processing",
                        "PRODUCT_TIMEOUT",
                        f"Product did not finish before the {settings.batch_timeout:g}s batch timeout.",
                        retryable=True,
                        attempts=1,
                    )
                )
                results_by_row[product.row_number] = result
        executor.shutdown(wait=False, cancel_futures=True)

    products = [results_by_row[key] for key in sorted(results_by_row)]
    summary = _summarize(products, selected_inputs, invalid_results)
    logger.info("batch_end success=%s partial=%s failed=%s", summary.successful, summary.partial, summary.failed)
    return BatchResult(utc_now_iso(), source_path.name, summary, products)


def _process_one(product: ProductInput, settings: Settings, category_cache: dict[str, tuple], category_lock: threading.Lock) -> ProductResult:
    logger.info("product_start row=%s product_id=%s", product.row_number, product.product_id)
    result = product_scraper.scrape_product(product.product_id or "", settings)
    result.row_number = product.row_number

    if result.status != "failed" and result.category_url:
        with category_lock:
            if result.category_url not in category_cache:
                category_cache[result.category_url] = category_scraper.scrape_category_ads(result.category_url, settings)
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

    if settings.include_delivery and result.status != "failed" and result.product_id:
        try:
            result.delivery_estimates = delivery.check_delivery_for_product(result.product_id, settings)
        except Exception as exc:
            result.warnings.append(f"Delivery check failed: {exc}")

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
