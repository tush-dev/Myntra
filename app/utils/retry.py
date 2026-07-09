from __future__ import annotations

import random
import time
import urllib.error
import urllib.request
import gzip
import zlib
from dataclasses import dataclass

from app.config import Settings


@dataclass
class FetchResponse:
    url: str
    final_url: str
    status: int
    content_type: str | None
    byte_count: int
    text: str
    attempts: int


class FetchError(Exception):
    def __init__(self, code: str, message: str, retryable: bool, attempts: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.attempts = attempts


TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def fetch_text(url: str, settings: Settings) -> FetchResponse:
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    attempts = max(settings.retry_count, 0) + 1
    last_error: FetchError | None = None

    for attempt in range(1, attempts + 1):
        if settings.request_delay:
            time.sleep(settings.request_delay + random.uniform(0, settings.jitter))
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=settings.request_timeout) as response:
                raw = response.read()
                decoded = _decode_body(raw, response.headers.get("content-encoding"))
                charset = response.headers.get_content_charset() or "utf-8"
                return FetchResponse(
                    url=url,
                    final_url=response.geturl(),
                    status=response.status,
                    content_type=response.headers.get("content-type"),
                    byte_count=len(raw),
                    text=decoded.decode(charset, errors="replace"),
                    attempts=attempt,
                )
        except urllib.error.HTTPError as exc:
            retryable = exc.code in TRANSIENT_STATUSES
            last_error = FetchError(f"HTTP_{exc.code}", f"HTTP {exc.code} while fetching {url}", retryable, attempt)
            if not retryable or attempt >= attempts:
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = FetchError("NETWORK_ERROR", str(exc), True, attempt)
            if attempt >= attempts:
                break
        time.sleep(min(2**attempt, 8) + random.uniform(0, settings.jitter))

    assert last_error is not None
    raise last_error


def _decode_body(raw: bytes, content_encoding: str | None) -> bytes:
    encoding = (content_encoding or "").lower()
    if "gzip" in encoding:
        return gzip.decompress(raw)
    if "deflate" in encoding:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw
