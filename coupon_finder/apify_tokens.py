"""Apify token chính + dự phòng — tự failover khi key lỗi."""
from __future__ import annotations

import logging

from coupon_finder.config import settings
from coupon_finder.search_errors import is_apify_auth_failure

logger = logging.getLogger(__name__)


def apify_tokens_configured() -> list[str]:
    """Danh sách token theo thứ tự ưu tiên (không trùng, bỏ rỗng)."""
    out: list[str] = []
    for raw in (settings.apify_token, settings.apify_token_backup):
        t = (raw or "").strip()
        if t and t not in out:
            out.append(t)
    return out


def has_apify_token() -> bool:
    return bool(apify_tokens_configured())


def should_failover_to_backup_apify(exc: BaseException) -> bool:
    """Lỗi token / hết credit / quota — thử key dự phòng."""
    if is_apify_auth_failure(exc):
        return True
    s = str(exc).lower()
    return any(
        k in s
        for k in (
            "credit",
            "quota",
            "usage limit",
            "limit exceeded",
            "insufficient",
            "billing",
            "payment required",
            "not enough",
            "exceeded your",
            "402",
            "429",
            "plan",
            "subscription",
            "timeout",
            "timed out",
            "connection",
            "503",
            "502",
            "500",
            "504",
            "gateway",
            "temporarily unavailable",
            "service unavailable",
        )
    )
