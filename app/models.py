from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Status = Literal["success", "partial", "failed"]


@dataclass
class ErrorDetail:
    stage: str
    code: str
    message: str
    retryable: bool = False
    attempts: int = 1


@dataclass
class ProductInput:
    row_number: int
    product_id: str | None
    duplicate: bool = False


@dataclass
class SponsoredResult:
    position: int
    title: str | None = None
    rating: float | None = None
    price: int | float | None = None
    url: str | None = None


@dataclass
class DeliveryEstimate:
    city: str
    pincode: str
    status: str = "unavailable"
    estimated_days: int | None = None
    estimated_date: str | None = None
    message: str | None = None
    errors: list[ErrorDetail] = field(default_factory=list)


@dataclass
class ProductResult:
    product_id: str | None
    row_number: int | None = None
    status: Status = "failed"
    product_url: str | None = None
    title: str | None = None
    description: str | None = None
    images: list[str] = field(default_factory=list)
    rating: float | None = None
    total_ratings_count: int | None = None
    category: str | None = None
    category_raw: str | None = None
    category_url: str | None = None
    category_source: str | None = None
    category_url_source: str | None = None
    page_type: str | None = None
    fetch_status: int | None = None
    fetch_content_type: str | None = None
    fetch_bytes: int | None = None
    html_title: str | None = None
    visible_text_preview: str | None = None
    category_ads: list[SponsoredResult] = field(default_factory=list)
    delivery_estimates: list[DeliveryEstimate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[ErrorDetail] = field(default_factory=list)


@dataclass
class BatchSummary:
    total_rows: int = 0
    unique_products: int = 0
    duplicate_rows: int = 0
    malformed_rows: int = 0
    successful: int = 0
    partial: int = 0
    failed: int = 0


@dataclass
class BatchResult:
    generated_at: str
    source_file: str
    summary: BatchSummary
    products: list[ProductResult]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_dict(value: Any) -> Any:
    return asdict(value)
