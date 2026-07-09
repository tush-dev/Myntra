from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.config import Settings
from app.models import DeliveryEstimate, ErrorDetail
from app.utils.retry import FetchError, fetch_text

logger = logging.getLogger(__name__)

DELIVERY_PINCODES: list[dict[str, str]] = [
    {"city": "Bengaluru", "pincode": "560001"},
    {"city": "Mumbai", "pincode": "400001"},
    {"city": "Delhi", "pincode": "110001"},
    {"city": "Ahmedabad", "pincode": "380001"},
    {"city": "Kolkata", "pincode": "700001"},
]

MYNTRA_BASE_URL = "https://www.myntra.com"


def check_delivery_for_product(product_id: str, settings: Settings) -> list[DeliveryEstimate]:
    estimates: list[DeliveryEstimate] = []
    for entry in DELIVERY_PINCODES:
        estimate = _check_single_pincode(product_id, entry["city"], entry["pincode"], settings)
        estimates.append(estimate)
    return estimates


def _check_single_pincode(
    product_id: str, city: str, pincode: str, settings: Settings
) -> DeliveryEstimate:
    estimate = DeliveryEstimate(city=city, pincode=pincode)
    url = f"{MYNTRA_BASE_URL}/gw/v2/pincode/{pincode}/product/{product_id}"

    try:
        response = fetch_text(url, settings)
    except FetchError as exc:
        estimate.status = "unavailable"
        code = _error_code_for_fetch(exc)
        estimate.errors.append(
            ErrorDetail("delivery_fetch", code, exc.message, retryable=exc.retryable, attempts=exc.attempts)
        )
        estimate.message = exc.message
        logger.info("delivery_fetch_failed product_id=%s pincode=%s code=%s", product_id, pincode, code)
        return estimate

    if response.status == 403:
        estimate.status = "unavailable"
        estimate.errors.append(
            ErrorDetail("delivery_fetch", "DELIVERY_BLOCKED", "Delivery endpoint returned 403.", retryable=False, attempts=response.attempts)
        )
        estimate.message = "Blocked by server"
        return estimate

    if response.status >= 400:
        estimate.status = "unavailable"
        estimate.errors.append(
            ErrorDetail("delivery_fetch", "DELIVERY_UNAVAILABLE", f"HTTP {response.status}", retryable=False, attempts=response.attempts)
        )
        estimate.message = f"HTTP {response.status}"
        return estimate

    try:
        data = json.loads(response.text)
    except (json.JSONDecodeError, ValueError) as exc:
        estimate.status = "unavailable"
        estimate.errors.append(
            ErrorDetail("delivery_parse", "DELIVERY_PARSE_FAILED", str(exc), retryable=False, attempts=1)
        )
        estimate.message = "Could not parse delivery response"
        return estimate

    return _parse_delivery_response(estimate, data)


def _parse_delivery_response(estimate: DeliveryEstimate, data: dict) -> DeliveryEstimate:
    if not isinstance(data, dict):
        estimate.status = "unavailable"
        estimate.message = "Unexpected response structure"
        return estimate

    serviceable = data.get("isServiceable")
    delivery_info = data.get("deliveryInfo") or data.get("estimatedDeliveryDate")
    message = data.get("message") or data.get("statusMessage")

    if serviceable is False or serviceable == "false":
        estimate.status = "unavailable"
        estimate.message = message or "Not serviceable at this pincode"
        return estimate

    if delivery_info:
        if isinstance(delivery_info, dict):
            days = delivery_info.get("deliveryDays") or delivery_info.get("numberOfDays")
            date = delivery_info.get("deliveryDate") or delivery_info.get("estimatedDate")
        elif isinstance(delivery_info, str):
            date = delivery_info
            days = None
        else:
            date = None
            days = None

        estimate.status = "success"
        estimate.estimated_days = int(days) if days else None
        estimate.estimated_date = str(date) if date else None
        estimate.message = message
        return estimate

    if serviceable is True or serviceable == "true":
        estimate.status = "success"
        estimate.message = message or "Serviceable"
        return estimate

    estimate.status = "unavailable"
    estimate.message = message or "No delivery information available"
    return estimate


def _error_code_for_fetch(exc: FetchError) -> str:
    if exc.code.startswith("HTTP_"):
        status_part = exc.code.split("_", 1)[1]
        try:
            status = int(status_part)
            if status == 403:
                return "DELIVERY_BLOCKED"
            if status == 408 or status == 504:
                return "DELIVERY_TIMEOUT"
        except ValueError:
            pass
    if exc.code == "NETWORK_ERROR":
        if "timed out" in exc.message.lower() or "timeout" in exc.message.lower():
            return "DELIVERY_TIMEOUT"
        return "DELIVERY_BLOCKED"
    return "DELIVERY_UNAVAILABLE"
