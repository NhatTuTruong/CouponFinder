from __future__ import annotations

import re
from urllib.parse import urlparse

from coupon_finder.models import SearchRequest


def build_external_search_query(req: SearchRequest) -> str:
    parts: list[str] = []
    if req.brand:
        parts.append(req.brand.strip())
    if req.product:
        parts.append(req.product.strip())
    if req.category:
        parts.append(req.category.strip())
    parts.append("coupon OR promo code OR discount code")
    return " ".join(p for p in parts if p)

# Từ thường gặp trong snippet Google — không phải mã coupon
_STOPWORDS = frozenset(
    {
        "HTTP",
        "HTTPS",
        "HTML",
        "WWW",
        "COM",
        "ONLY",
        "OFF",
        "FREE",
        "SHIP",
        "SALE",
        "SHOP",
        "SITE",
        "CODE",
        "PROMO",
        "DEAL",
        "DEALS",
        "CLICK",
        "HERE",
        "VIEW",
        "MORE",
        "FROM",
        "WITH",
        "YOUR",
        "THIS",
        "THAT",
        "WHAT",
        "WHEN",
        "WILL",
        "JUST",
        "LIKE",
        "MAKE",
        "PAGE",
        "HOME",
        "MENU",
        "CART",
        "ITEM",
        "ITEMS",
        "DAYS",
        "YEAR",
        "YEARS",
        "TODAY",
        "NOW",
        "NEW",
        "GET",
        "USE",
        "THE",
        "AND",
        "FOR",
        "YOU",
        "OUR",
        "ALL",
        "OUT",
        "ONE",
        "TWO",
        "OFF",
        "GOOGLE",
        "SEARCH",
        "SHOPPING",
        "IMAGES",
        "MAPS",
        "YOUTUBE",
        "NEWS",
        "FILTER",
        "DESKTOP",
        "STORE",
        "FIND",
        "VIDEO",
        "VIDEOS",
        "RESULT",
        "RESULTS",
        "CHECKOUT",
        "AVERAGE",
        "PLUS",
        "TIME",
        "REAL",
        "TRACKED",
        "WORKING",
        "TESTED",
        "VERIFIED",
        "CODES",
        "SIMPLECODES",
    }
)

_TOKEN = re.compile(r"\b([A-Z0-9]{4,16})\b")


def extract_candidate_codes(text: str, *, limit: int = 40) -> list[str]:
    """Trích các chuỗi giống mã giảm giá từ title/snippet (heuristic)."""
    if not text:
        return []
    upper = text.upper()
    seen: set[str] = set()
    out: list[str] = []
    for m in _TOKEN.finditer(upper):
        code = m.group(1)
        if code in _STOPWORDS:
            continue
        if code.isdigit():
            continue
        if len(set(code)) <= 1:
            continue
        if code not in seen:
            seen.add(code)
            out.append(code)
        if len(out) >= limit:
            break
    return out


def host_label(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        if h.startswith("www."):
            h = h[4:]
        return h or url
    except Exception:  # noqa: BLE001
        return url
