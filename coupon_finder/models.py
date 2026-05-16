from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CouponType(str, Enum):
    public = "public"
    new_customer = "new_customer"
    freeship = "freeship"
    limited_time = "limited_time"
    influencer = "influencer"
    exclusive = "exclusive"
    unknown = "unknown"


class CouponSource(str, Enum):
    coupon_site = "coupon_site"
    community = "community"
    social = "social"
    email = "email"
    public_promo = "public_promo"
    recent_share = "recent_share"
    unknown = "unknown"


class SearchRequest(BaseModel):
    brand: Optional[str] = None
    website: Optional[str] = None
    product: Optional[str] = None
    category: Optional[str] = None

    def query_text(self) -> str:
        parts = [self.brand, self.website, self.product, self.category]
        return " ".join([p.strip() for p in parts if p and p.strip()])


class RawCoupon(BaseModel):
    code: str
    description: Optional[str] = None
    source: CouponSource = CouponSource.unknown
    source_url: Optional[str] = None
    found_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    expires_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)


class NormalizedCoupon(BaseModel):
    code: str
    description: Optional[str] = None
    source: CouponSource
    source_url: Optional[str] = None
    found_at: datetime
    expires_at: Optional[datetime] = None
    fingerprint: str
    metadata: dict = Field(default_factory=dict)


class VerificationResult(BaseModel):
    checked_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    is_working: bool
    discount_text: Optional[str] = None
    conditions_text: Optional[str] = None
    error: Optional[str] = None


class CouponResult(BaseModel):
    code: str
    description: Optional[str] = None
    coupon_type: CouponType = CouponType.unknown
    source: CouponSource
    source_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    # Giảm giá ghi trên trang nguồn (vd Simply Codes `data-discount`) trước khi verify shop
    source_discount: Optional[str] = None
    # Mô tả từng mã trên nguồn (vd Simply Codes `data-description`), khác description (tiêu đề SERP/trang)
    source_item_description: Optional[str] = None
    # Simply Codes nút .btn-show-code — data-health-score
    source_health_score: Optional[str] = None
    discount_text: Optional[str] = None
    conditions_text: Optional[str] = None
    is_working: bool = False
    verified_at: Optional[datetime] = None
    # Lần thấy mã trên nguồn (chuẩn hoá); dùng hiển thị khi chưa có verified_at
    found_at: Optional[datetime] = None
    confidence: float = 0.0
    popularity: int = 0

