from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import to_dict
from app.services.batch_service import process_csv
from app.utils.logging import configure_logging

app = FastAPI(title="Myntra Product Scraper", version="1.0.0")
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"

if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scrape")
async def scrape(file: UploadFile = File(...), limit: int | None = None, include_delivery: bool = False) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file.")
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    try:
        run_settings = replace(settings, include_delivery=include_delivery)
        logger.info("scrape_request filename=%s bytes=%s limit=%s include_delivery=%s", file.filename, len(content), limit, include_delivery)
        result = process_csv(temp_path, limit=limit, settings=run_settings)
        result.source_file = file.filename
        return JSONResponse(json.loads(json.dumps(to_dict(result), ensure_ascii=False)))
    finally:
        temp_path.unlink(missing_ok=True)


@app.get("/", response_class=HTMLResponse)
def index():
    if not INDEX_HTML.is_file():
        return "<h1>Myntra Product Scraper</h1><p>POST a CSV file to /scrape.</p>"
    return FileResponse(INDEX_HTML)
