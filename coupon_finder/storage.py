from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import inspect, text
from sqlmodel import Field, Session, SQLModel, create_engine, select

from coupon_finder.config import settings
from coupon_finder.models import CouponSource, CouponType


class CouponRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    brand: Optional[str] = None
    website: Optional[str] = None
    product: Optional[str] = None
    category: Optional[str] = None

    code: str = Field(index=True)
    fingerprint: str = Field(index=True)
    description: Optional[str] = None

    source: str
    source_url: Optional[str] = None
    # Giảm giá từ collector (Simply Codes `data-discount`), khác discount_text sau verify shop
    source_discount: Optional[str] = None
    # Mô tả từng mã (Simply Codes `data-description`)
    source_item_description: Optional[str] = None
    # Simply Codes `data-health-score` trên nút .btn-show-code
    source_health_score: Optional[str] = None

    found_at: datetime
    expires_at: Optional[datetime] = None

    # verification
    is_working: bool = False
    verified_at: Optional[datetime] = None
    discount_text: Optional[str] = None
    conditions_text: Optional[str] = None
    last_error: Optional[str] = None

    # scoring
    coupon_type: str = CouponType.unknown.value
    confidence: float = 0.0
    popularity: int = 0


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


engine = create_engine(f"sqlite:///{settings.sqlite_path}")


def _migrate_schema() -> None:
    """Thêm cột mới trên SQLite đã tồn tại (create_all không ALTER)."""
    insp = inspect(engine)
    if not insp.has_table(CouponRecord.__tablename__):
        return
    cols = {c["name"] for c in insp.get_columns(CouponRecord.__tablename__)}
    if "source_discount" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(f'ALTER TABLE {CouponRecord.__tablename__} ADD COLUMN source_discount TEXT')
            )
    cols = {c["name"] for c in insp.get_columns(CouponRecord.__tablename__)}
    if "source_item_description" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(f'ALTER TABLE {CouponRecord.__tablename__} ADD COLUMN source_item_description TEXT')
            )
    cols = {c["name"] for c in insp.get_columns(CouponRecord.__tablename__)}
    if "source_health_score" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(f'ALTER TABLE {CouponRecord.__tablename__} ADD COLUMN source_health_score TEXT')
            )


def init_db() -> None:
    _ensure_parent_dir(settings.sqlite_path)
    SQLModel.metadata.create_all(engine)
    _migrate_schema()


def upsert_many(records: Iterable[CouponRecord]) -> None:
    init_db()
    with Session(engine) as session:
        for r in records:
            existing = session.exec(select(CouponRecord).where(CouponRecord.fingerprint == r.fingerprint)).first()
            if existing:
                # keep best knowledge, refresh timestamps/source url
                existing.description = existing.description or r.description
                existing.source = existing.source or r.source
                existing.source_url = existing.source_url or r.source_url
                existing.source_discount = existing.source_discount or r.source_discount
                existing.source_item_description = existing.source_item_description or r.source_item_description
                existing.source_health_score = existing.source_health_score or r.source_health_score
                existing.found_at = max(existing.found_at, r.found_at)
                existing.expires_at = existing.expires_at or r.expires_at
            else:
                session.add(r)
        session.commit()


def mark_verification(fingerprint: str, *, is_working: bool, verified_at: datetime, discount_text: str | None, conditions_text: str | None, error: str | None) -> None:
    init_db()
    with Session(engine) as session:
        rec = session.exec(select(CouponRecord).where(CouponRecord.fingerprint == fingerprint)).first()
        if not rec:
            return
        rec.is_working = is_working
        rec.verified_at = verified_at
        rec.discount_text = discount_text
        rec.conditions_text = conditions_text
        rec.last_error = error
        session.add(rec)
        session.commit()


def update_scoring(fingerprint: str, *, coupon_type: CouponType, confidence: float, popularity_delta: int = 0) -> None:
    init_db()
    with Session(engine) as session:
        rec = session.exec(select(CouponRecord).where(CouponRecord.fingerprint == fingerprint)).first()
        if not rec:
            return
        rec.coupon_type = coupon_type.value
        rec.confidence = float(confidence)
        rec.popularity = int(rec.popularity or 0) + int(popularity_delta)
        session.add(rec)
        session.commit()


def list_results(
    *,
    brand: str | None = None,
    website: str | None = None,
    product: str | None = None,
    category: str | None = None,
    only_working: bool = True,
    min_confidence: float | None = None,
    limit: int = 50,
) -> list[CouponRecord]:
    init_db()
    with Session(engine) as session:
        stmt = select(CouponRecord)
        if brand:
            stmt = stmt.where(CouponRecord.brand == brand)
        if website:
            stmt = stmt.where(CouponRecord.website == website)
        if product:
            stmt = stmt.where(CouponRecord.product == product)
        if category:
            stmt = stmt.where(CouponRecord.category == category)
        if only_working:
            stmt = stmt.where(CouponRecord.is_working == True)  # noqa: E712
        if min_confidence is not None:
            stmt = stmt.where(CouponRecord.confidence >= float(min_confidence))
        stmt = stmt.order_by(CouponRecord.confidence.desc(), CouponRecord.verified_at.desc().nullslast(), CouponRecord.found_at.desc())
        stmt = stmt.limit(int(limit))
        return list(session.exec(stmt).all())

