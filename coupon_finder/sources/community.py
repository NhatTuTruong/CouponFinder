from __future__ import annotations

import json
import os
from datetime import datetime
from urllib.parse import urlparse

from dateutil.parser import isoparse

from coupon_finder.config import settings
from coupon_finder.models import CouponSource, RawCoupon, SearchRequest
from coupon_finder.sources.base import CouponCollector


def _site_host(url: str) -> str:
    """Chuẩn hoá host để so khớp website (bỏ path, bỏ www., không phân biệt hoa thường)."""
    u = (url or "").strip().lower()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    netloc = urlparse(u).netloc
    host = netloc.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


class CommunityFileCollector(CouponCollector):
    name = "community_file"

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(settings.data_dir, "community_coupons.json")

    async def collect(self, req: SearchRequest) -> list[RawCoupon]:
        if not os.path.exists(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(
                    [
                        {
                            "brand": "DemoBrand",
                            "website": "https://example.com",
                            "code": "WELCOME10",
                            "description": "10% off for new customers",
                            "expires_at": None,
                            "source_url": "local://community",
                        }
                    ],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)

        query = (req.brand or "").strip().lower()
        req_host = _site_host(req.website or "")

        out: list[RawCoupon] = []
        for item in data:
            if query and str(item.get("brand", "")).strip().lower() != query:
                continue
            if req_host and _site_host(str(item.get("website", ""))) != req_host:
                continue
            exp = item.get("expires_at")
            expires_at = isoparse(exp) if isinstance(exp, str) and exp else None
            out.append(
                RawCoupon(
                    code=str(item["code"]),
                    description=item.get("description"),
                    source=CouponSource.community,
                    source_url=item.get("source_url"),
                    found_at=datetime.utcnow(),
                    expires_at=expires_at,
                    metadata={"collector": self.name},
                )
            )
        return out

