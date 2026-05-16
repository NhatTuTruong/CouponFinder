from __future__ import annotations

from abc import ABC, abstractmethod

from coupon_finder.models import RawCoupon, SearchRequest


class CouponCollector(ABC):
    name: str

    @abstractmethod
    async def collect(self, req: SearchRequest) -> list[RawCoupon]:
        raise NotImplementedError

