# Myntra Backend / Tooling Assignment

## Overview

This repository contains a Python tool that accepts a CSV with Myntra `product_id` values, fetches public Myntra product pages, extracts structured product data, resolves each product category, and returns the first 3 sponsored/Ad-style listing results for that category.

The core works as both:

- a CLI: `python -m app.main --input ... --output ...`
- a FastAPI backend with a small upload/results frontend.

## Features

- CSV validation for `product_id`, empty rows, malformed IDs, and duplicate rows.
- Product ID resolution via public `https://www.myntra.com/{product_id}` pages.
- Extraction of title, description, images, rating, ratings count, category, and category URL.
- Sponsored result extraction from listing state using `plaProducts` entries with `isPLA == true`.
- Bounded retry policy, request timeout, conservative concurrency, and per-product isolation.
- Structured JSON output with `success`, `partial`, and `failed` statuses.
- Optional delivery estimate checks for 5 major Indian cities (disabled by default).
- Unit tests with local fixtures; live Myntra pages are not required for normal tests.

## Architecture

Data flow:

1. `app/utils/csv_reader.py` validates CSV rows into `ProductInput`.
2. `app/scrapers/product_scraper.py` fetches `https://www.myntra.com/{product_id}`.
3. `app/scrapers/parsers.py` extracts `window.__myx.pdpData` and JSON-LD breadcrumbs.
4. `app/scrapers/category_scraper.py` fetches the resolved category page.
5. `app/services/batch_service.py` coordinates the batch, caches category results, and builds the final `BatchResult`.

The code intentionally uses the standard library for the scraping core. FastAPI is only needed for the API/frontend layer.

## How To Run

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run tests:

```bash
.venv/bin/python -m pytest -q
```

Run the CLI on the provided CSV:

```bash
.venv/bin/python -m app.main \
  --input "/Users/ashwin/Downloads/Products list (1).csv" \
  --output data/sample_output.json \
  --concurrency 2 \
  --timeout 20
```

Quick validation run:

```bash
.venv/bin/python -m app.main \
  --input "/Users/ashwin/Downloads/Products list (1).csv" \
  --output data/sample_output_small.json \
  --limit 5
```

Run with delivery estimates (optional bonus feature):

```bash
.venv/bin/python -m app.main \
  --input "/Users/ashwin/Downloads/Products list (1).csv" \
  --output data/sample_output_small.json \
  --limit 1 \
  --include-delivery
```

Run the API and frontend:

```bash
.venv/bin/uvicorn app.api:app --reload --port 8000
```

Then open `http://localhost:8000`, upload a CSV, and download the JSON result.

Docker:

```bash
docker compose up --build
```

## Approach

I inspected the provided PDF and CSV before implementing. The PDF is a 3-page backend/tooling assignment asking for public Myntra product extraction, first 3 Ad-marked sponsored category results, robust error handling, structured output, a README, and a sample output. The delivery-estimate feature is explicitly optional.

CSV inspection:

- Columns: `product_id`
- Data rows: 100
- Unique non-empty product IDs: 84
- Empty rows: 0
- Malformed rows: 0
- Duplicate ID values: 11 values, covering 27 duplicate rows

Live Myntra investigation on real IDs showed:

- Direct URLs like `https://www.myntra.com/35512522` return product pages.
- Useful product data is present in raw HTML.
- Product pages contain `window.__myx.pdpData` with name, product details, media, and ratings.
- JSON-LD provides product fallback data and breadcrumbs.
- Category/listing pages contain `window.__myx.searchData.results`.
- Listing state includes `plaProducts`; each product has `isPLA: true`.
- Raw HTML did not expose a reliable literal `Ad` text marker in the downloaded source. The public state used to render product listing ads is the reliable source available without browser automation.

Because of those findings, the implementation uses HTTP + embedded JSON parsing instead of Playwright. This keeps the tool faster, easier to test, and less fragile than browser-only scraping.

## Product Resolution

Product IDs are resolved as:

```text
https://www.myntra.com/{product_id}
```

For sampled real IDs, this returned the relevant public product page without needing a slug. The final response URL is stored as `product_url`. If a page does not expose usable product state, the row is marked failed or partial with structured errors.

## Sponsored Result Detection

For the resolved category page, the scraper parses:

```text
window.__myx.searchData.results.plaProducts
```

Only products where `isPLA == true` are considered sponsored results. The tool returns the first 3 in `plaProducts` order and never pads with organic `products`.

This is documented as Myntra’s public listing-state signal for product listing ads. If Myntra changes that state or removes PLA data, the result becomes an empty list with a warning rather than fabricated ads.

## Delivery Estimate Bonus (Optional)

An optional delivery-estimate feature checks estimated delivery availability for each product across 5 major Indian cities. It is **disabled by default** to avoid slowing down the core scraping pipeline.

### Sample Pincodes

| City | Pincode |
|---|---|
| Bengaluru | 560001 |
| Mumbai | 400001 |
| Delhi | 110001 |
| Ahmedabad | 380001 |
| Kolkata | 700001 |

### Enabling Delivery Checks

**CLI:**
```bash
python -m app.main --input data.csv --output out.json --include-delivery
```

**API:** Add `include_delivery=true` as a query parameter to `POST /scrape`.

**Frontend:** Check the "Include delivery estimates" checkbox before running.

**Environment variable:**
```bash
export MYNTRA_INCLUDE_DELIVERY=true
```

### Output Format

Each product includes a `delivery_estimates` array (empty when disabled):

```json
{
  "delivery_estimates": [
    {
      "city": "Bengaluru",
      "pincode": "560001",
      "status": "success",
      "estimated_days": 3,
      "estimated_date": null,
      "message": null,
      "errors": []
    }
  ]
}
```

### Status Values

- `success` — delivery information was retrieved
- `unavailable` — delivery data could not be obtained (most common)
- `failed` — an error occurred during the check

### Error Codes

- `DELIVERY_UNAVAILABLE` — API returned no delivery data
- `DELIVERY_BLOCKED` — server returned 403 or anti-bot response
- `DELIVERY_PARSE_FAILED` — response could not be parsed
- `DELIVERY_TIMEOUT` — request timed out

### Limitations

Myntra's delivery estimate data is fetched via internal XHR calls on product pages. There is no publicly documented delivery API. The implementation makes a best-effort attempt to call a likely delivery endpoint. In most cases, this returns `unavailable` because Myntra's delivery APIs require session state or are rate-limited. This is expected behavior — the feature is designed to be resilient and never break core product extraction.

When delivery checks fail, the product's overall status remains unchanged (`success` or `partial`). Delivery failures are recorded as warnings, not errors.

## Error Handling

Every product produces a `ProductResult`. The batch does not crash on individual failures.

Implemented handling includes:

- missing or malformed CSV values
- duplicate rows
- fetch failures and transient HTTP status retries
- missing product fields
- unavailable/unparseable product state
- missing category URL
- category fetch or sponsored parse errors

Statuses:

- `success`: core fields are present and category sponsored extraction completed.
- `partial`: useful data was extracted but one or more fields or steps are missing.
- `failed`: no meaningful product data could be resolved or processed.

## Assumptions

- Public `window.__myx` page state is acceptable because it is embedded in the public HTML used to render Myntra pages.
- `plaProducts` + `isPLA == true` is the public sponsored/Ad signal in listing state.
- The third breadcrumb item is the product taxonomy category; later breadcrumb items are commonly brand links.
- Rating can be null for unrated products and should not be replaced with `0`.

## Scope In

- CLI
- FastAPI API
- simple hosted frontend served by FastAPI
- JSON output
- structured errors and warnings
- tests with local fixtures
- Dockerfile and Compose file
- full sample output from the provided CSV
- optional delivery estimate bonus (disabled by default)

## Scope Out

- Login, cookies, CAPTCHA handling, proxy rotation, or anti-bot bypass.
- Persistent async job queue.
- Playwright fallback. Current evidence showed raw public state was enough for the assignment fields.

## Known Limitations

- Myntra can change `window.__myx` or listing state fields.
- Sponsored results may vary by region, time, campaign availability, or request context.
- Raw HTML did not include a literal visible `Ad` label; the tool uses the public PLA state flag.
- Some numeric IDs in the provided file returned no usable product/category state and are reported as failed.
- The simple in-memory category cache is per run only.
- Delivery estimate checks are best-effort; Myntra has no public delivery API, so most results will be `unavailable`.

## What I Would Build Next

- Add a Playwright fallback only for categories where public state disappears.
- Persist category/product fetch cache with TTL.
- Add a background job model for large uploads.
- Add selector/state monitoring for early warning when Myntra markup changes.
- Add richer observability and structured JSON logs.

## Testing

Normal tests do not hit Myntra:

```bash
.venv/bin/python -m pytest -q
```

Covered areas include CSV parsing, missing column handling, empty rows, malformed IDs, duplicate IDs, product parsing, missing product fields, sponsored ordering, first-3-only logic, no sponsored results, malformed HTML, batch continuation, JSON serialization, and delivery estimate features.

Current result:

```text
18 passed
```

## Sample Output

Generated files:

- `data/sample_output_small.json`: first 5 valid rows.
- `data/sample_output.json`: full provided CSV.

Full run summary:

```json
{
  "total_rows": 100,
  "unique_products": 84,
  "duplicate_rows": 27,
  "malformed_rows": 0,
  "successful": 61,
  "partial": 35,
  "failed": 4
}
```

The 4 failed rows are preserved with structured errors rather than fabricated data.

## Ethical / Operational Considerations

This tool uses only public Myntra pages and public page state. It does not use credentials, private APIs, cookies, proxy rotation, CAPTCHA solving, or aggressive bypass techniques. Defaults are intentionally conservative: low concurrency, bounded retries, timeouts, and small request delay/jitter.

