from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from app.models import ErrorDetail, ProductInput, ProductResult

PRODUCT_ID_RE = re.compile(r"^\d+$")


def read_product_csv(path: str | Path) -> tuple[list[ProductInput], list[ProductResult]]:
    csv_path = Path(path)
    products: list[ProductInput] = []
    invalid_results: list[ProductResult] = []

    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            header = []
        if "product_id" not in header:
            result = ProductResult(product_id=None, row_number=None, status="failed")
            result.errors.append(
                ErrorDetail(
                    stage="input_validation",
                    code="MISSING_PRODUCT_ID_COLUMN",
                    message="CSV must contain a product_id column.",
                    retryable=False,
                    attempts=1,
                )
            )
            return [], [result]

        product_id_index = header.index("product_id")
        raw_rows = list(reader)

    values = []
    for index, row in enumerate(raw_rows):
        value = row[product_id_index] if len(row) > product_id_index else ""
        values.append((index + 2, (value or "").strip()))
    counts = Counter(value for _, value in values if value)

    for row_number, product_id in values:
        if not product_id:
            invalid_results.append(_invalid_result(row_number, product_id, "EMPTY_PRODUCT_ID", "product_id is empty."))
            continue
        if not PRODUCT_ID_RE.fullmatch(product_id):
            invalid_results.append(
                _invalid_result(row_number, product_id, "MALFORMED_PRODUCT_ID", "product_id must contain digits only.")
            )
            continue
        products.append(ProductInput(row_number=row_number, product_id=product_id, duplicate=counts[product_id] > 1))

    return products, invalid_results


def _invalid_result(row_number: int, product_id: str | None, code: str, message: str) -> ProductResult:
    result = ProductResult(product_id=product_id, row_number=row_number, status="failed")
    result.errors.append(
        ErrorDetail(stage="input_validation", code=code, message=message, retryable=False, attempts=1)
    )
    return result
