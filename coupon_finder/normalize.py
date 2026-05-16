from __future__ import annotations

import re
from datetime import datetime, timedelta

from rapidfuzz import fuzz

from coupon_finder.config import settings
from coupon_finder.models import NormalizedCoupon, RawCoupon


_CODE_RE = re.compile(r"[^A-Z0-9_-]+")


def normalize_code(code: str) -> str:
    code = (code or "").strip().upper()
    code = code.replace(" ", "")
    code = _CODE_RE.sub("", code)
    return code


def fingerprint(code: str, description: str | None, website: str | None, brand: str | None) -> str:
    c = normalize_code(code)
    d = (description or "").strip().lower()
    b = (brand or "").strip().lower()
    w = (website or "").strip().lower()
    key = "|".join([b, w, c, d[:80]])
    key = re.sub(r"\s+", " ", key)
    return key


def is_obviously_fake(code: str) -> bool:
    c = normalize_code(code)
    if len(c) < 4:
        return True
    if c in {"TEST", "EXAMPLE", "PROMO", "COUPON", "DISCOUNT"}:
        return True
    if re.fullmatch(r"[0-9]{4,}", c):
        return True
    return False


def is_too_old(found_at: datetime) -> bool:
    return found_at < (datetime.utcnow() - timedelta(days=int(settings.stale_days)))


def normalize_and_dedupe(raw: list[RawCoupon], *, website: str | None, brand: str | None) -> list[NormalizedCoupon]:
    # 3) Làm sạch / chuẩn hoá
    # - chuẩn hoá code
    # - lọc fake / quá cũ
    # - loại trùng & gộp gần giống (fuzzy theo mô tả)
    cleaned: list[NormalizedCoupon] = []
    for r in raw:
        code = normalize_code(r.code)
        if not code:
            continue
        if is_obviously_fake(code):
            continue
        if is_too_old(r.found_at):
            continue
        fp = fingerprint(code, r.description, website, brand)
        cleaned.append(
            NormalizedCoupon(
                code=code,
                description=(r.description or "").strip() or None,
                source=r.source,
                source_url=r.source_url,
                found_at=r.found_at,
                expires_at=r.expires_at,
                fingerprint=fp,
                metadata=r.metadata,
            )
        )

    # exact dedupe by fingerprint
    uniq: dict[str, NormalizedCoupon] = {}
    for c in cleaned:
        if c.fingerprint not in uniq:
            uniq[c.fingerprint] = c
        else:
            # keep richer description/source_url if present
            old = uniq[c.fingerprint]
            old.description = old.description or c.description
            old.source_url = old.source_url or c.source_url
            old.expires_at = old.expires_at or c.expires_at
            old.found_at = max(old.found_at, c.found_at)
            if (not (old.metadata or {}).get("source_discount")) and (c.metadata or {}).get("source_discount"):
                om = dict(old.metadata or {})
                om["source_discount"] = (c.metadata or {}).get("source_discount")
                old.metadata = om
            if (not (old.metadata or {}).get("source_item_description")) and (c.metadata or {}).get(
                "source_item_description"
            ):
                om = dict(old.metadata or {})
                om["source_item_description"] = (c.metadata or {}).get("source_item_description")
                old.metadata = om
            if (not (old.metadata or {}).get("source_health_score")) and (c.metadata or {}).get("source_health_score"):
                om = dict(old.metadata or {})
                om["source_health_score"] = (c.metadata or {}).get("source_health_score")
                old.metadata = om

    items = list(uniq.values())

    # fuzzy merge: same code but different descriptions that are ~similar
    merged: list[NormalizedCoupon] = []
    by_code: dict[str, list[NormalizedCoupon]] = {}
    for it in items:
        by_code.setdefault(it.code, []).append(it)
    for code, group in by_code.items():
        if len(group) == 1:
            merged.append(group[0])
            continue
        base = group[0]
        for g in group[1:]:
            s1, s2 = base.description or "", g.description or ""
            if fuzz.partial_ratio(s1, s2) >= 85:
                base.source_url = base.source_url or g.source_url
                base.expires_at = base.expires_at or g.expires_at
                base.found_at = max(base.found_at, g.found_at)
                if (not (base.metadata or {}).get("source_discount")) and (g.metadata or {}).get("source_discount"):
                    m = dict(base.metadata or {})
                    m["source_discount"] = (g.metadata or {}).get("source_discount")
                    base.metadata = m
                if (not (base.metadata or {}).get("source_item_description")) and (g.metadata or {}).get(
                    "source_item_description"
                ):
                    m = dict(base.metadata or {})
                    m["source_item_description"] = (g.metadata or {}).get("source_item_description")
                    base.metadata = m
                if (not (base.metadata or {}).get("source_health_score")) and (g.metadata or {}).get("source_health_score"):
                    m = dict(base.metadata or {})
                    m["source_health_score"] = (g.metadata or {}).get("source_health_score")
                    base.metadata = m
            else:
                merged.append(g)
        merged.append(base)

    # stable sort: newest first
    merged.sort(key=lambda x: (x.expires_at is None, x.expires_at or datetime.max, x.found_at), reverse=True)
    return merged

