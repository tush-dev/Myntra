from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from app.models import SponsoredResult

MYNTRA_BASE_URL = "https://www.myntra.com"


@dataclass
class ParsedProduct:
    title: str | None
    description: str | None
    images: list[str]
    rating: float | None
    total_ratings_count: int | None
    category: str | None
    category_raw: str | None
    category_url: str | None
    category_source: str | None
    category_url_source: str | None
    page_type: str


def extract_window_state(html_text: str) -> dict[str, Any] | None:
    match = re.search(r"window\.__myx\s*=\s*", html_text)
    if not match:
        return None
    index = match.end()
    while index < len(html_text) and html_text[index].isspace():
        index += 1
    if index >= len(html_text) or html_text[index] != "{":
        return None
    blob = _balanced_json_object(html_text, index)
    if blob is None:
        return None
    return json.loads(blob)


def parse_json_ld(html_text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pattern = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
    for match in pattern.finditer(html_text):
        raw = html.unescape(match.group(1)).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            items.append(parsed)
        elif isinstance(parsed, list):
            items.extend(item for item in parsed if isinstance(item, dict))
    return items


def parse_product_page(html_text: str) -> ParsedProduct:
    state = extract_window_state(html_text) or {}
    pdp = state.get("pdpData") or {}
    json_ld = parse_json_ld(html_text)
    product_ld = next((item for item in json_ld if item.get("@type") == "Product"), {})
    breadcrumb_ld = next((item for item in json_ld if item.get("@type") == "BreadcrumbList"), {})
    page_type = detect_page_type(html_text, state, product_ld)

    title = _clean_text(pdp.get("name") or product_ld.get("name"))
    description = _description_from_pdp(pdp) or _clean_text(product_ld.get("description"))
    images = _images_from_pdp(pdp) or _images_from_ld(product_ld)
    rating, total = _ratings_from_pdp(pdp, product_ld)
    category, category_url, category_source, category_url_source = _resolve_category(pdp, breadcrumb_ld)

    if not category:
        category = _clean_text(pdp.get("analytics", {}).get("articleType") if isinstance(pdp.get("analytics"), dict) else None)
        category_source = "pdp.analytics.articleType" if category else None
    category_raw = category

    return ParsedProduct(
        title=title,
        description=description,
        images=images[:2],
        rating=rating,
        total_ratings_count=total,
        category=category,
        category_raw=category_raw,
        category_url=category_url,
        category_source=category_source,
        category_url_source=category_url_source,
        page_type=page_type,
    )


def detect_page_type(html_text: str, state: dict[str, Any] | None = None, product_ld: dict[str, Any] | None = None) -> str:
    state = state if state is not None else extract_window_state(html_text) or {}
    product_ld = product_ld if product_ld is not None else next(
        (item for item in parse_json_ld(html_text) if item.get("@type") == "Product"), {}
    )
    if isinstance(state.get("pdpData"), dict) and (state["pdpData"].get("id") or state["pdpData"].get("name")):
        return "product"
    if product_ld.get("name") or product_ld.get("sku"):
        return "product"
    if ((state.get("searchData") or {}).get("results")):
        return "listing"

    title = _page_title(html_text)
    visible = visible_text_preview(html_text, limit=500).lower()
    lower = html_text[:20000].lower()
    challenge_signals = [
        "access denied",
        "verify you are human",
        "are you a human",
        "captcha",
        "unusual traffic",
        "request blocked",
        "akamai",
    ]
    if (title and any(signal in title.lower() for signal in challenge_signals)) or (
        "window.__myx" not in html_text and any(signal in lower for signal in challenge_signals)
    ):
        return "challenge"
    if not html_text.strip() or (not title and len(visible) < 40):
        return "empty"
    if "window.__myx" not in html_text and title and "myntra" in title.lower():
        return "client_shell"
    if title and "search" in title.lower():
        return "search"
    if title and "myntra" in title.lower():
        return "home_or_shell"
    return "unknown"


def visible_text_preview(html_text: str, limit: int = 300) -> str:
    parser = _VisibleTextParser()
    parser.feed(html_text)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    return text[:limit]


def parse_category_ads(html_text: str, limit: int = 3) -> list[SponsoredResult]:
    state = extract_window_state(html_text) or {}
    results = (((state.get("searchData") or {}).get("results")) or {})
    pla_products = results.get("plaProducts") or []
    ads: list[SponsoredResult] = []
    for product in pla_products:
        if product.get("isPLA") is not True:
            continue
        ads.append(
            SponsoredResult(
                position=len(ads) + 1,
                title=_clean_text(product.get("productName") or product.get("product")),
                rating=_float_or_none(product.get("rating")),
                price=product.get("price") if product.get("price") not in ("", 0) else product.get("discountedPrice"),
                url=_absolute_url(product.get("landingPageUrl")),
            )
        )
        if len(ads) >= limit:
            break
    return ads


def _resolve_category(pdp: dict[str, Any], breadcrumb_ld: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    category, category_url = _category_from_breadcrumb(breadcrumb_ld)
    if category_url:
        return category, category_url, "json_ld.breadcrumb.position_3", "json_ld.breadcrumb.position_3"

    category, category_url = _category_from_cross_links(pdp)
    if category_url:
        return category, category_url, "pdp.crossLinks", "pdp.crossLinks"

    analytics = pdp.get("analytics") if isinstance(pdp.get("analytics"), dict) else {}
    article_type = _clean_text(analytics.get("articleType"))
    if article_type:
        return article_type, _absolute_url(_slugify_category(article_type)), "pdp.analytics.articleType", "derived_from_article_type_slug"

    return None, None, None, None


def _balanced_json_object(text: str, start: int) -> str | None:
    depth = 0
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
    return None


def _description_from_pdp(pdp: dict[str, Any]) -> str | None:
    details = pdp.get("productDetails") or []
    parts: list[str] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        description = _clean_html(item.get("description"))
        if description:
            parts.append(f"{title}: {description}" if title else description)
    return "\n".join(parts) if parts else None


def _images_from_pdp(pdp: dict[str, Any]) -> list[str]:
    media = pdp.get("media") or {}
    images: list[str] = []
    for album in media.get("albums") or []:
        for image_item in album.get("images") or []:
            url = image_item.get("imageURL") or image_item.get("secureSrc") or image_item.get("src")
            if url:
                images.append(_normalize_url(url))
    return _dedupe(images)


def _images_from_ld(product_ld: dict[str, Any]) -> list[str]:
    image = product_ld.get("image")
    if isinstance(image, str):
        return [_normalize_url(image)]
    if isinstance(image, list):
        return [_normalize_url(item) for item in image if isinstance(item, str)]
    return []


def _ratings_from_pdp(pdp: dict[str, Any], product_ld: dict[str, Any]) -> tuple[float | None, int | None]:
    ratings = pdp.get("ratings") or {}
    rating = _float_or_none(ratings.get("averageRating"))
    total = _int_or_none(ratings.get("totalCount"))
    if rating is None:
        aggregate = product_ld.get("aggregateRating") or {}
        rating = _float_or_none(aggregate.get("ratingValue"))
        total = _int_or_none(aggregate.get("ratingCount") or aggregate.get("reviewCount"))
    if rating == 0:
        rating = None
    if total == 0:
        total = None
    return rating, total


def _category_from_breadcrumb(breadcrumb_ld: dict[str, Any]) -> tuple[str | None, str | None]:
    elements = breadcrumb_ld.get("itemListElement") or []
    if not elements:
        return None, None
    # Myntra product breadcrumbs usually end with brand/collection links:
    # Accessories > Women > Handbags > Brand > More by Brand.
    # The assignment category is the product taxonomy level, which is position 3 when present.
    candidate = elements[2] if len(elements) >= 3 else elements[-1]
    item = candidate.get("item") if isinstance(candidate, dict) else None
    if not isinstance(item, dict):
        return None, None
    return _clean_text(item.get("name")), _absolute_url(item.get("@id"))


def _category_from_cross_links(pdp: dict[str, Any]) -> tuple[str | None, str | None]:
    analytics = pdp.get("analytics") if isinstance(pdp.get("analytics"), dict) else {}
    article_type = _clean_text(analytics.get("articleType"))
    cross_links = pdp.get("crossLinks") or []
    if not isinstance(cross_links, list):
        return article_type, None

    for link in cross_links:
        if not isinstance(link, dict):
            continue
        title = _clean_text(link.get("title")) or ""
        url = link.get("url")
        if not url:
            continue
        if article_type and title.lower().startswith(f"more {article_type.lower()}"):
            return article_type, _absolute_url(str(url).split("?", 1)[0])

    for link in cross_links:
        if not isinstance(link, dict):
            continue
        url = link.get("url")
        if url:
            title = _clean_text(link.get("title"))
            return article_type or _category_from_cross_link_title(title), _absolute_url(str(url).split("?", 1)[0])
    return article_type, None


def _category_from_cross_link_title(title: str | None) -> str | None:
    if not title:
        return None
    match = re.match(r"More\s+(.+?)(?:\s+by\s+.+)?$", title, flags=re.I)
    return _clean_text(match.group(1)) if match else None


def _clean_html(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<br\s*/?>", "\n", str(value), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean_text(html.unescape(text))


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"[ \t\r\f\v]+", " ", str(value))
    text = re.sub(r"\n\s+", "\n", text).strip()
    return text or None


def _page_title(html_text: str) -> str | None:
    match = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    return _clean_text(html.unescape(match.group(1))) if match else None


def _slugify_category(value: str) -> str:
    text = html.unescape(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and data.strip():
            self.parts.append(data.strip())


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _absolute_url(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return f"{MYNTRA_BASE_URL}/{text.lstrip('/')}"


def _normalize_url(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://"):
        return "https://" + value[len("http://") :]
    return value


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
