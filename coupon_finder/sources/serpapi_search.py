from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import requests

from coupon_finder.config import settings
from coupon_finder.domain_util import is_simplycodes_domain_url
from coupon_finder.models import CouponSource, RawCoupon, SearchRequest
from coupon_finder.sources.base import CouponCollector
from coupon_finder.sources.code_extract import build_external_search_query, extract_candidate_codes, host_label


class SerpAPICollector(CouponCollector):
    """Dùng SerpAPI (Google organic) để tìm trang + snippet có mã — cần COUPON_FINDER_SERPAPI_KEY."""

    name = "serpapi_google"

    async def collect(self, req: SearchRequest) -> list[RawCoupon]:
        key = (settings.serpapi_key or "").strip()
        if not key:
            return []

        q = build_external_search_query(req)
        if not q.strip():
            return []

        def _fetch() -> dict[str, Any]:
            r = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": q,
                    "api_key": key,
                    "num": min(10, max(1, settings.external_search_max_results)),
                },
                headers={"User-Agent": settings.user_agent},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()

        try:
            data = await asyncio.to_thread(_fetch)
        except Exception:  # noqa: BLE001
            return []

        organic = data.get("organic_results") or []
        out: list[RawCoupon] = []
        for item in organic:
            link = item.get("link") or ""
            title = item.get("title") or ""
            snippet = item.get("snippet") or ""
            if is_simplycodes_domain_url(link):
                continue
            blob = f"{title}\n{snippet}"
            for code in extract_candidate_codes(blob):
                out.append(
                    RawCoupon(
                        code=code,
                        description=f"{title[:200]} — {host_label(link)}",
                        source=CouponSource.coupon_site,
                        source_url=link or None,
                        found_at=datetime.utcnow(),
                        metadata={"collector": self.name, "engine": "serpapi"},
                    )
                )
        return out
