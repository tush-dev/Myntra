# Myntra Backend / Tooling Assignment

Python tooling and a FastAPI app for the Myntra backend assignment. The tool accepts a CSV with a `product_id` column, fetches public Myntra product pages, extracts structured product data, resolves the product category, and returns up to the first 3 sponsored listing results available in Myntra's public listing state.

## Current Status

- The CLI, FastAPI app, frontend, Docker setup, and tests are implemented.
- Local scraping and Docker-based scraping have worked for the tested product IDs in this environment.
- The Render-hosted app deploys and serves the frontend successfully, but outbound product requests from the current Render service have been observed returning Myntra `Site Maintenance` HTML instead of product pages. Hosted live extraction may therefore fail even when local/Docker extraction works. This is an observed environment-specific upstream response, not a claim that all Render IPs are blocked.

## Quick Start

Docker:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000
```

Useful routes:

- `GET /` - frontend
- `GET /health` - health check
- `POST /scrape` - CSV upload API
- `GET /docs` - FastAPI Swagger UI
- `GET /openapi.json` - OpenAPI schema

The Dockerfile exposes port `8000`, and `docker-compose.yml` maps `8000:8000`.

## Local Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.api:app --reload --port 8000
```

Then open `http://localhost:8000`.

## CLI Usage

Run the CLI against the provided CSV:

```bash
.venv/bin/python -m app.main \
  --input "/Users/ashwin/Downloads/Products list (1).csv" \
  --output data/sample_output.json \
  --concurrency 2 \
  --timeout 20
```

Small validation run:

```bash
.venv/bin/python -m app.main \
  --input "/Users/ashwin/Downloads/Products list (1).csv" \
  --output data/sample_output_small.json \
  --limit 5
```

Supported CLI flags:

```text
--input
--output
--limit
--concurrency
--timeout
--headless
--include-delivery
--debug
```

`--headless` is reserved for a browser fallback. A Playwright fallback is not currently implemented.

## API And Frontend

`POST /scrape` accepts multipart form data with a CSV file named `file`.

Optional query parameters:

- `limit` - process only the first N valid product rows.
- `include_delivery=true` - enable optional delivery checks.

The existing frontend in `frontend/` is served by FastAPI:

- `frontend/index.html` at `/`
- `frontend/styles.css` at `/static/styles.css`
- `frontend/app.js` at `/static/app.js`

The frontend uses same-origin API calls to `/scrape`.

## Architecture

```text
app/
  api.py                    FastAPI app and frontend/static serving
  cli.py                    CLI argument parsing
  main.py                   CLI entry point
  config.py                 Runtime settings and environment variables
  models.py                 Dataclasses for JSON output
  services/batch_service.py Batch orchestration and per-product isolation
  scrapers/product_scraper.py
  scrapers/category_scraper.py
  scrapers/delivery.py
  scrapers/parsers.py
  utils/csv_reader.py
  utils/retry.py
frontend/
  index.html
  app.js
  styles.css
data/
  sample_output.json
  sample_output_small.json
tests/
```

Workflow:

1. Read and validate CSV rows from `product_id`.
2. Resolve each product ID to a public Myntra product URL.
3. Fetch the product page with bounded retries and conservative delays.
4. Parse embedded public page state and JSON-LD for product fields.
5. Resolve a public category/listing URL from breadcrumbs, cross-links, or product analytics.
6. Fetch the category page.
7. Return the first 3 sponsored listing products from `searchData.results.plaProducts` where `isPLA == true`.
8. Build structured JSON for every input row, including partial and failed rows.

## Approach And Rationale

The assignment asks for public Myntra product extraction, first 3 explicitly Ad-marked sponsored category results, robust failures, structured JSON, a README, and sample output. The optional delivery check is treated as a bonus and is disabled by default.

Input findings from `Products list (1).csv`:

- Columns: `product_id`
- Data rows: 100
- Valid numeric product IDs: 100
- Unique product IDs: 84
- Empty rows: 0
- Malformed rows: 0
- Duplicate ID values: 11 values, involving 27 rows

Product resolution:

- Product pages are requested as `https://www.myntra.com/product/product/product/{product_id}/buy`.
- The final redirected URL is stored in each result as `product_url` when the fetch succeeds.

HTTP fetching:

- `app/utils/retry.py` uses `curl_cffi` with Chrome impersonation when available.
- It falls back to Python's standard `urllib` path if `curl_cffi` is unavailable.
- Retries are bounded and only transient status/network failures are retried.

Parsing strategy:

- Product data is parsed from public embedded `window.__myx.pdpData` where available.
- JSON-LD product and breadcrumb data is used as fallback.
- Category URL resolution checks JSON-LD breadcrumbs first, then PDP cross-links, then a derived article-type slug when present.
- The parser records compact diagnostics such as page type, HTTP status, response bytes, title, and a short visible-text preview.

Sponsored results:

- Category pages are parsed from `window.__myx.searchData.results.plaProducts`.
- Only entries with `isPLA == true` are returned.
- The tool returns at most 3 sponsored results and does not substitute organic results.
- If Myntra does not expose sponsored listing data, the product remains `partial` with a warning or structured category/sponsored error.

Per-product isolation:

- A bad product, missing field, category failure, or sponsored extraction failure does not crash the batch.
- Every row receives a structured result.

## Output Statuses

- `success` - meaningful product data was extracted and category sponsored extraction completed without category/sponsored errors.
- `partial` - product data was extracted, but one or more fields, category URL, sponsored results, or optional steps were missing or unavailable.
- `failed` - no useful product data could be resolved or extracted.

Product detail extraction and category/sponsored extraction are separate stages. Category or sponsored failures do not erase product fields.

## Optional Delivery Bonus

Delivery checks are implemented as an optional, best-effort feature and are disabled by default.

Sample pincodes:

| City | Pincode |
| --- | --- |
| Bengaluru | 560001 |
| Mumbai | 400001 |
| Delhi | 110001 |
| Ahmedabad | 380001 |
| Kolkata | 700001 |

Enable delivery from the CLI:

```bash
.venv/bin/python -m app.main \
  --input "/Users/ashwin/Downloads/Products list (1).csv" \
  --output data/sample_output_with_delivery.json \
  --limit 1 \
  --include-delivery
```

Enable delivery from the API/frontend:

- API: add `include_delivery=true` to `POST /scrape`.
- Frontend: check "Include delivery estimates".

Delivery output shape:

```json
{
  "delivery_estimates": [
    {
      "city": "Bengaluru",
      "pincode": "560001",
      "status": "success/unavailable/failed",
      "estimated_days": null,
      "estimated_date": null,
      "message": null,
      "errors": []
    }
  ]
}
```

Actual behavior:

- Myntra does not provide a documented public delivery-estimate API.
- `app/scrapers/delivery.py` makes a best-effort public request for each sample pincode.
- Most delivery checks should be expected to return `unavailable`.
- Delivery failures do not change an otherwise `success` or `partial` product to `failed`.

Delivery error codes:

- `DELIVERY_UNAVAILABLE`
- `DELIVERY_BLOCKED`
- `DELIVERY_PARSE_FAILED`
- `DELIVERY_TIMEOUT`

## Assumptions

- Only public Myntra pages and public page state are in scope.
- No login, personal cookies, private credentials, proxy rotation, CAPTCHA bypass, or auth bypass is used.
- Missing product fields are normal and should be represented as `null`, empty arrays, warnings, or structured errors.
- Sponsored results can vary by time, session, category, location, and upstream page state.
- `plaProducts` with `isPLA == true` is treated as Myntra's public sponsored listing signal.
- Unrated products can have `rating` and `total_ratings_count` as `null`.

## Scope

Implemented:

- CSV `product_id` ingestion and validation.
- CLI.
- FastAPI backend.
- Existing static frontend served by FastAPI.
- Docker and Render Blueprint configuration.
- Product URL resolution.
- Product field extraction.
- Category URL resolution.
- First 3 public sponsored/PLA results only.
- Structured JSON output.
- Per-product failure isolation.
- Optional delivery-estimate checks.
- Unit tests with local fixtures.

Partially implemented:

- Delivery estimates: best-effort only, usually `unavailable`.
- Hosted Render scraping: app deploys, but current Render outbound product fetches receive Myntra `Site Maintenance` content.

Intentionally not implemented:

- Playwright/browser fallback.
- Login or private session handling.
- CAPTCHA solving, proxy rotation, or block bypass.
- Persistent job queue or database.
- Fabricating sponsored results when public sponsored data is absent.

## Known Limitations

- Hosted extraction on the current Render service may fail because Myntra returns `Site Maintenance` HTML for outbound product requests from that environment.
- Myntra can change `window.__myx`, JSON-LD, or listing state fields.
- The downloaded listing HTML did not expose a reliable literal visible `Ad` label; this implementation uses the public `plaProducts` / `isPLA` listing-state signal and never pads with organic products.
- Sponsored results may be absent, fewer than 3, or vary by request context.
- Delivery estimates are optional and commonly unavailable because there is no documented public delivery endpoint.
- Category caching is in-memory and scoped to one run.

## Sample Output

Checked-in sample files generated from the provided product IDs:

- `data/sample_output_small.json` - first 5 valid rows.
- `data/sample_output.json` - full provided CSV.

Current checked-in full sample summary:

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

The sample files were generated with delivery disabled. New runs with the current model include `delivery_estimates` in each product result; it is empty unless delivery is enabled.

## Testing

Run:

```bash
.venv/bin/python -m pytest -q
```

The tests use local fixtures rather than live Myntra requests. Covered areas include CSV validation, duplicate handling, product parsing, missing fields, sponsored ordering, first-3-only sponsored results, malformed HTML, batch continuation, status semantics, JSON serialization, and delivery behavior.

Current result:

```text
18 passed
```

## Deployment

Render is configured as a Blueprint using `render.yaml`.

- Service type: web
- Runtime: Docker
- Health check: `/health`
- Port: Render supplies `PORT`; Docker defaults to `8000`
- Start command from Dockerfile: `uvicorn app.api:app --host 0.0.0.0 --port ${PORT:-8000}`

The deployed app can serve the frontend and API. Live scraping from the hosted service is limited by the observed Myntra `Site Maintenance` upstream response described above.

## Ethical And Operational Notes

This tool uses public pages and conservative requests only. It does not use credentials, private APIs, personal browser cookies, proxy rotation, CAPTCHA solving, auth bypass, or aggressive anti-bot techniques. Failures are recorded and processing continues.

## What I Would Build Next

1. Add a narrowly scoped Playwright fallback only for cases where verified public product data is present after browser rendering but absent in raw HTML.
2. Add persisted product/category fetch caching with TTL to reduce repeated upstream requests.
3. Add a background job model for larger uploads and progress polling.
4. Add structured production log export for fetch classification, page type, and category resolution diagnostics.
5. Add scheduled fixture refresh checks to detect Myntra page-state changes early.
