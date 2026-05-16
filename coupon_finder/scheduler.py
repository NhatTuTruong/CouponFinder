from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from coupon_finder.config import settings
from coupon_finder.models import SearchRequest
from coupon_finder.pipeline import search
from coupon_finder.storage import CouponRecord, engine, init_db


async def _recheck_recent(limit: int = 30) -> None:
    init_db()
    with Session(engine) as session:
        stmt = (
            select(CouponRecord)
            .where(CouponRecord.verified_at.is_not(None))
            .order_by(CouponRecord.verified_at.desc())
            .limit(int(limit))
        )
        recs = list(session.exec(stmt).all())

    # group by (brand, website, product, category) and re-run pipeline with verify on
    # (MVP: recheck one-by-one using website + brand)
    for r in recs:
        req = SearchRequest(brand=r.brand, website=r.website, product=r.product, category=r.category)
        await search(req, verify=True, limit_verify=10)


def start_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler()
    # 7) cập nhật & theo dõi liên tục
    sched.add_job(lambda: asyncio.run(_recheck_recent()), "interval", minutes=30, next_run_time=datetime.utcnow() + timedelta(seconds=10))
    sched.start()
    return sched

