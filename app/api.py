from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import to_dict
from app.services.batch_service import process_csv

app = FastAPI(title="Myntra Product Scraper", version="1.0.0")

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scrape")
async def scrape(file: UploadFile = File(...), limit: int | None = None) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file.")
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    try:
        result = process_csv(temp_path, limit=limit, settings=settings)
        result.source_file = file.filename
        return JSONResponse(json.loads(json.dumps(to_dict(result), ensure_ascii=False)))
    finally:
        temp_path.unlink(missing_ok=True)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    index_path = frontend_dir / "index.html"
    if not index_path.exists():
        return "<h1>Myntra Product Scraper</h1><p>POST a CSV file to /scrape.</p>"
    return index_path.read_text(encoding="utf-8")

