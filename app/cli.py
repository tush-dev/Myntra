from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from app.config import settings
from app.models import to_dict
from app.services.batch_service import process_csv
from app.utils.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape public Myntra product details from a product_id CSV.")
    parser.add_argument("--input", required=True, help="CSV file containing a product_id column.")
    parser.add_argument("--output", required=True, help="Path to write JSON output.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N valid product rows.")
    parser.add_argument("--concurrency", type=int, default=settings.concurrency)
    parser.add_argument("--timeout", type=float, default=settings.request_timeout)
    parser.add_argument("--headless", action="store_true", default=settings.headless, help="Reserved for browser fallback.")
    parser.add_argument("--include-delivery", action="store_true", default=settings.include_delivery, help="Check delivery estimates for 5 sample pincodes.")
    parser.add_argument("--debug", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_logging("DEBUG" if args.debug else settings.log_level)
    run_settings = replace(settings, concurrency=args.concurrency, request_timeout=args.timeout, headless=args.headless, include_delivery=args.include_delivery)
    result = process_csv(args.input, limit=args.limit, settings=run_settings)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(to_dict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {output_path}")

