from __future__ import annotations

import re
from datetime import datetime, timedelta

from coupon_finder.models import CouponResult, CouponType, NormalizedCoupon, VerificationResult


def classify(c: NormalizedCoupon, v: VerificationResult) -> CouponType:
    src_disc = (c.metadata or {}).get("source_discount") if c.metadata else None
    if isinstance(src_disc, str):
        src_disc = src_disc.strip() or None
    src_item = (c.metadata or {}).get("source_item_description") if c.metadata else None
    if isinstance(src_item, str):
        src_item = src_item.strip() or None
    text = " ".join(
        [
            c.description or "",
            v.discount_text or "",
            src_disc or "",
            src_item or "",
            v.conditions_text or "",
        ]
    ).lower()
    if "freeship" in text or "free ship" in text or "miễn phí vận chuyển" in text:
        return CouponType.freeship
    if "new customer" in text or "first order" in text or "khách mới" in text:
        return CouponType.new_customer
    if "exclusive" in text or "độc quyền" in text:
        return CouponType.exclusive
    if "influencer" in text or "creator" in text or "kols" in text:
        return CouponType.influencer
    if "today" in text or "ends" in text or "24h" in text or "hôm nay" in text:
        return CouponType.limited_time
    return CouponType.public if c.source.value in {"coupon_site", "public_promo"} else CouponType.unknown


def _recency_score(verified_at: datetime | None) -> float:
    if not verified_at:
        return 0.0
    age = datetime.utcnow() - verified_at
    if age <= timedelta(hours=6):
        return 1.0
    if age <= timedelta(days=1):
        return 0.85
    if age <= timedelta(days=3):
        return 0.7
    if age <= timedelta(days=7):
        return 0.55
    return 0.35


def _source_score(source: str) -> float:
    return {
        "community": 0.55,
        "coupon_site": 0.45,
        "recent_share": 0.5,
        "social": 0.35,
        "email": 0.6,
        "public_promo": 0.55,
    }.get(source, 0.4)


def _discount_hint_score(discount_text: str | None) -> float:
    if not discount_text:
        return 0.35
    t = discount_text.lower()
    if re.search(r"\b(\d{1,2})\s*%|\bpercent\b", t):
        return 0.75
    if "free ship" in t or "freeship" in t or "miễn phí vận chuyển" in t:
        return 0.65
    if re.search(r"\b\$|₫|vnd|đ\b", t):
        return 0.6
    return 0.5


def confidence(c: NormalizedCoupon, v: VerificationResult, popularity: int = 0) -> float:
    # 6) Chấm điểm tin cậy (0..1)
    # - ưu tiên verify thành công
    # - gần đây
    # - nguồn
    # - có tín hiệu giảm giá
    # - cộng thêm theo popularity
    base = 0.05
    working = 0.55 if v.is_working else 0.0
    rec = 0.2 * _recency_score(v.checked_at if v.checked_at else None)
    src = 0.15 * _source_score(c.source.value)
    src_disc = (c.metadata or {}).get("source_discount") if c.metadata else None
    if isinstance(src_disc, str):
        src_disc = src_disc.strip() or None
    disc_hint = v.discount_text or src_disc
    src_item = (c.metadata or {}).get("source_item_description") if c.metadata else None
    if isinstance(src_item, str):
        src_item = src_item.strip() or None
    if not disc_hint and src_item:
        disc_hint = src_item
    disc = 0.1 * _discount_hint_score(disc_hint)
    pop = min(0.15, 0.02 * max(0, popularity))
    return max(0.0, min(1.0, base + working + rec + src + disc + pop))


def build_result(c: NormalizedCoupon, v: VerificationResult, *, popularity: int = 0) -> CouponResult:
    ct = classify(c, v)
    conf = confidence(c, v, popularity=popularity)
    src_disc = (c.metadata or {}).get("source_discount") if c.metadata else None
    if isinstance(src_disc, str):
        src_disc = src_disc.strip() or None
    else:
        src_disc = None
    src_item = (c.metadata or {}).get("source_item_description") if c.metadata else None
    if isinstance(src_item, str):
        src_item = src_item.strip() or None
    else:
        src_item = None
    src_health = (c.metadata or {}).get("source_health_score") if c.metadata else None
    if isinstance(src_health, str):
        src_health = src_health.strip() or None
    else:
        src_health = None
    return CouponResult(
        code=c.code,
        description=c.description,
        coupon_type=ct,
        source=c.source,
        source_url=c.source_url,
        expires_at=c.expires_at,
        source_discount=src_disc,
        source_item_description=src_item,
        source_health_score=src_health,
        discount_text=v.discount_text,
        conditions_text=v.conditions_text,
        is_working=v.is_working,
        verified_at=v.checked_at,
        found_at=c.found_at,
        confidence=conf,
        popularity=popularity,
    )

