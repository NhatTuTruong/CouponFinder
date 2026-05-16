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


class GoogleCSECollector(CouponCollector):
    """Google Programmable Search Engine (JSON API) — cần API key + cx."""

    name = "google_cse"

    async def collect(self, req: SearchRequest) -> list[RawCoupon]:
        api_key = (settings.google_api_key or "").strip()
        cx = (settings.google_cse_id or "").strip()
        if not api_key or not cx:
            return []

        q = build_external_search_query(req)
        if not q.strip():
            return []

        def _fetch() -> dict[str, Any]:
            r = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": api_key,
                    "cx": cx,
                    "q": q,
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

        items = data.get("items") or []
        out: list[RawCoupon] = []
        for item in items:
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
                        metadata={"collector": self.name},
                    )
                )
        return out
