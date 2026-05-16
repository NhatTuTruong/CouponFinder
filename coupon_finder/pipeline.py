from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from coupon_finder.classify_score import build_result
from coupon_finder.config import settings
from coupon_finder.models import CouponResult, NormalizedCoupon, RawCoupon, SearchRequest
from coupon_finder.normalize import normalize_and_dedupe
from coupon_finder.sources.base import CouponCollector
from coupon_finder.sources.apify_google import ApifyGoogleSearchCollector
from coupon_finder.sources.community import CommunityFileCollector
from coupon_finder.sources.google_cse import GoogleCSECollector
from coupon_finder.sources.serpapi_search import SerpAPICollector
from coupon_finder.domain_util import is_coupon_listing_site_url
from coupon_finder.sources.simply_codes import SimplyCodesCollector
from coupon_finder.storage import CouponRecord, mark_verification, update_scoring, upsert_many
from coupon_finder.search_errors import MSG_NOT_FOUND, SearchUserError, search_error_from_exception
from coupon_finder.search_progress import ProgressFn, bind_progress, report_progress, reset_progress
from coupon_finder.verifier import VerifyContext, verify_coupon


def _source_discount_from_meta(c: NormalizedCoupon) -> str | None:
    v = (c.metadata or {}).get("source_discount")
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _source_item_description_from_meta(c: NormalizedCoupon) -> str | None:
    v = (c.metadata or {}).get("source_item_description")
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _source_health_score_from_meta(c: NormalizedCoupon) -> str | None:
    v = (c.metadata or {}).get("source_health_score")
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _preview_coupons(normalized: list[NormalizedCoupon], *, limit: int) -> list[CouponResult]:
    out: list[CouponResult] = []
    for c in normalized[: int(limit)]:
        out.append(
            CouponResult(
                code=c.code,
                description=c.description,
                source=c.source,
                source_url=c.source_url,
                expires_at=c.expires_at,
                source_discount=_source_discount_from_meta(c),
                source_item_description=_source_item_description_from_meta(c),
                source_health_score=_source_health_score_from_meta(c),
                is_working=False,
                verified_at=None,
                found_at=c.found_at,
                confidence=0.2,
                popularity=0,
            )
        )
    return out


@dataclass(frozen=True)
class SearchReport:
    """Kết quả tìm kiếm + số liệu để CLI/API giải thích khi danh sách rỗng."""

    results: list[CouponResult]
    raw_count: int
    normalized_count: int
    # Một phần mã sau chuẩn hoá (để CLI luôn in được danh sách dù verify chưa chạy / lỗi)
    collected_preview: tuple[CouponResult, ...] = field(default_factory=tuple)
    # Dòng log quy trình (thu thập → chuẩn hoá) cho giao diện web
    trace: tuple[str, ...] = field(default_factory=tuple)
    user_message: str | None = None
    error_code: str | None = None


def _default_collectors() -> list[CouponCollector]:
    if settings.only_simplycodes:
        if (settings.apify_token or "").strip():
            return [SimplyCodesCollector()]
        return []

    collectors: list[CouponCollector] = [CommunityFileCollector()]
    if (settings.serpapi_key or "").strip():
        collectors.append(SerpAPICollector())
    if (settings.google_api_key or "").strip() and (settings.google_cse_id or "").strip():
        collectors.append(GoogleCSECollector())
    if (settings.apify_token or "").strip():
        collectors.append(ApifyGoogleSearchCollector())
        collectors.append(SimplyCodesCollector())
    return collectors


def _merge_collect_error(
    current: SearchUserError | None, new: SearchUserError
) -> SearchUserError:
    if current is None:
        return new
    priority = {"apify_token": 0, "system": 1, "not_found": 2}
    if priority.get(new.code, 9) < priority.get(current.code, 9):
        return new
    return current


async def collect_all(req: SearchRequest) -> tuple[list[RawCoupon], list[str], SearchUserError | None]:
    # 2) Thu thập: file cộng đồng + (tuỳ chọn) SerpAPI / Google CSE khi có env
    collectors = _default_collectors()
    trace: list[str] = []
    short = [type(c).__name__.replace("Collector", "") for c in collectors]
    trace.append(f"Thu thập: {len(collectors)} nguồn ({', '.join(short)}).")
    report_progress(12, f"Thu thập từ {len(collectors)} nguồn…")
    results = await asyncio.gather(*[c.collect(req) for c in collectors], return_exceptions=True)
    report_progress(78, "Hoàn tất thu thập mã thô")
    raw: list[RawCoupon] = []
    collect_error: SearchUserError | None = None
    for i, r in enumerate(results):
        name = type(collectors[i]).__name__
        if isinstance(r, SearchUserError):
            collect_error = _merge_collect_error(collect_error, r)
            trace.append(f"  • {name}: {r.message}")
            continue
        if isinstance(r, BaseException):
            collect_error = _merge_collect_error(collect_error, search_error_from_exception(r))
            trace.append(f"  • {name}: lỗi — {type(r).__name__}: {r}")
            continue
        trace.append(f"  • {name}: {len(r)} mã thô")
        raw.extend(r)
    before_filter = len(raw)
    if settings.filter_raw_to_simplycodes_domain:
        raw = [x for x in raw if is_coupon_listing_site_url(x.source_url)]
        trace.append(
            f"Lọc chỉ trang coupon (simplycodes.com / tenereteam.com): {before_filter} → {len(raw)} mã "
            f"(COUPON_FINDER_FILTER_RAW_TO_SIMPLYCODES_DOMAIN)."
        )
    else:
        trace.append(f"Tổng mã thô sau thu thập: {len(raw)}.")
    if raw and collect_error and collect_error.code == "not_found":
        collect_error = None
    return raw, trace, collect_error


async def verify_all(req: SearchRequest, coupons: list[NormalizedCoupon], *, concurrency: int | None = None) -> list[tuple[NormalizedCoupon, object]]:
    cc = max(1, int(concurrency) if concurrency is not None else int(settings.verify_all_concurrency))
    sem = asyncio.Semaphore(cc)
    ctx = VerifyContext(req=req)

    async def _run(c: NormalizedCoupon):
        async with sem:
            v = await verify_coupon(c, ctx)
            return c, v

    return await asyncio.gather(*[_run(c) for c in coupons])


async def search(
    req: SearchRequest,
    *,
    verify: bool = True,
    limit_verify: int = 15,
    on_progress: ProgressFn | None = None,
) -> SearchReport:
    # 1) Tiếp nhận yêu cầu tìm kiếm
    prog_token = bind_progress(on_progress) if on_progress else None
    try:
        return await _search_impl(req, verify=verify, limit_verify=limit_verify)
    finally:
        if prog_token is not None:
            reset_progress(prog_token)


async def _search_impl(
    req: SearchRequest,
    *,
    verify: bool,
    limit_verify: int,
) -> SearchReport:
    report_progress(5, "Chuẩn bị tìm kiếm…")
    trace: list[str] = [
        f"Brand: {req.brand!r} · Website: {req.website or '—'}",
    ]
    raw, collect_trace, collect_error = await collect_all(req)
    trace.extend(collect_trace)

    # 3) Làm sạch & chuẩn hoá
    report_progress(82, "Chuẩn hoá và gộp mã trùng…")
    normalized = normalize_and_dedupe(raw, website=req.website, brand=req.brand)
    trace.append(f"Chuẩn hoá & gộp trùng: {len(raw)} mã thô → {len(normalized)} mã duy nhất.")
    preview_limit = 100
    collected_preview = tuple(_preview_coupons(normalized, limit=preview_limit))

    # persist raw normalized (before verify)
    records = [
        CouponRecord(
            brand=req.brand,
            website=req.website,
            product=req.product,
            category=req.category,
            code=c.code,
            fingerprint=c.fingerprint,
            description=c.description,
            source=c.source.value,
            source_url=c.source_url,
            source_discount=_source_discount_from_meta(c),
            source_item_description=_source_item_description_from_meta(c),
            source_health_score=_source_health_score_from_meta(c),
            found_at=c.found_at,
            expires_at=c.expires_at,
        )
        for c in normalized
    ]
    report_progress(92, "Lưu kết quả…")
    upsert_many(records)
    trace.append(f"Lưu cơ sở dữ liệu: {len(records)} bản ghi (upsert).")

    effective_verify = bool(verify) and settings.verify_enabled
    if verify and not settings.verify_enabled:
        trace.append(
            "Verify: tắt trong cấu hình (đặt COUPON_FINDER_VERIFY_ENABLED=true trong .env để bật lại)."
        )

    if not effective_verify:
        # Trả danh sách coupon tiềm năng (giới hạn để terminal không bị tràn)
        max_rows = 250
        out: list[CouponResult] = []
        for c in normalized[: int(max_rows)]:
            out.append(
                CouponResult(
                    code=c.code,
                    description=c.description,
                    source=c.source,
                    source_url=c.source_url,
                    expires_at=c.expires_at,
                    source_discount=_source_discount_from_meta(c),
                    source_item_description=_source_item_description_from_meta(c),
                    source_health_score=_source_health_score_from_meta(c),
                    is_working=False,
                    verified_at=None,
                    found_at=c.found_at,
                    confidence=0.15,
                    popularity=0,
                )
            )
        out.sort(key=lambda x: (x.confidence, x.expires_at is None, x.expires_at or datetime.max), reverse=True)
        if not verify:
            trace.append("Verify: tắt (chỉ liệt kê mã tiềm năng).")
        trace.append(f"Trả về tối đa {max_rows} hàng; preview {len(collected_preview)} mã.")
        report_progress(100, "Hoàn tất")
        user_message, error_code = _report_user_error(collect_error, normalized, raw)
        return SearchReport(
            results=out,
            raw_count=len(raw),
            normalized_count=len(normalized),
            collected_preview=collected_preview,
            trace=tuple(trace),
            user_message=user_message,
            error_code=error_code,
        )

    # 4) Verify thực tế (giới hạn để nhanh)
    trace.append(f"Verify: bật — tối đa {int(limit_verify)} mã đầu danh sách.")
    report_progress(94, f"Đang verify tối đa {int(limit_verify)} mã…")
    to_verify = normalized[: int(limit_verify)]
    verified_pairs = await verify_all(req, to_verify)

    out: list[CouponResult] = []
    for c, v in verified_pairs:
        mark_verification(
            c.fingerprint,
            is_working=v.is_working,
            verified_at=v.checked_at,
            discount_text=v.discount_text,
            conditions_text=v.conditions_text,
            error=v.error,
        )
        res = build_result(c, v, popularity=0)
        update_scoring(c.fingerprint, coupon_type=res.coupon_type, confidence=res.confidence, popularity_delta=0)
        out.append(res)

    # 5-6) phân loại + chấm điểm nằm trong build_result()
    # 8-9) trả kết quả: ưu tiên coupon tốt nhất (confidence desc)
    out.sort(key=lambda x: (x.is_working, x.confidence, x.verified_at or datetime.min), reverse=True)
    trace.append(f"Đã verify {len(verified_pairs)} mã; trả {len(out)} kết quả xếp hạng.")
    report_progress(100, "Hoàn tất")
    user_message, error_code = _report_user_error(collect_error, normalized, raw)
    return SearchReport(
        results=out,
        raw_count=len(raw),
        normalized_count=len(normalized),
        collected_preview=collected_preview,
        trace=tuple(trace),
        user_message=user_message,
        error_code=error_code,
    )


def _report_user_error(
    collect_error: SearchUserError | None,
    normalized: list,
    raw: list,
) -> tuple[str | None, str | None]:
    if normalized:
        return None, None
    if collect_error is not None:
        return collect_error.message, collect_error.code
    if not raw:
        return MSG_NOT_FOUND, "not_found"
    return None, None

