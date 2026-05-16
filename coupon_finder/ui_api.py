from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from coupon_finder.classify_score import build_result
from coupon_finder.models import CouponResult, CouponSource, NormalizedCoupon, SearchRequest
from coupon_finder.domain_util import infer_shop_website_from_coupon_source_urls, parse_domain_input
from coupon_finder.config import settings
from coupon_finder.normalize import fingerprint, normalize_code
from coupon_finder.pipeline import SearchReport, search, verify_all
from coupon_finder.search_errors import MSG_SYSTEM, SearchUserError
from coupon_finder.storage import CouponRecord, mark_verification, update_scoring, upsert_many
from coupon_finder.env_settings import apply_env_settings_from_ui, get_env_settings_payload
from coupon_finder.license_client import LicenseError, activate_license, consume_searches, license_status
from coupon_finder.ui_history import (
    append_ui_history_session,
    load_ui_history_sessions,
    merge_ui_history_sessions,
)

router = APIRouter(prefix="/api/ui", tags=["ui"])

MAX_BATCH_DOMAINS = 5


def _license_http_error(exc: LicenseError) -> HTTPException:
    detail: dict = {"message": exc.message, "error_code": exc.code}
    detail.update(exc.payload)
    return HTTPException(status_code=403, detail=detail)


def _require_license_searches(count: int = 1) -> dict:
    try:
        return consume_searches(count)
    except LicenseError as exc:
        raise _license_http_error(exc) from exc


class DomainSearchIn(BaseModel):
    domain: str = Field(
        ...,
        description="Vi du: nike.com, https://www.nike.com, hoac ten brand (Nike) de tim Simply Codes / nguon khac.",
    )


class DomainsSearchIn(BaseModel):
    domains: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_BATCH_DOMAINS,
        description="Moi phan tu hoac dong: domain, URL shop, hoac ten brand (toi da 5).",
    )


class VerifyIn(BaseModel):
    domain: str
    codes: list[str] = Field(default_factory=list, description="Danh sach ma can verify")
    max_codes: int = Field(default=25, ge=1, le=40)


class HistorySessionIn(BaseModel):
    id: str
    at: int = Field(..., description="Unix ms")
    domainInput: str = ""
    website: str = ""
    brandHint: str = ""
    rawCount: int = 0
    normalizedCount: int = 0
    coupons: list[dict] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)
    userMessage: str | None = None
    errorCode: str | None = None


class HistoryMigrateIn(BaseModel):
    sessions: list[HistorySessionIn] = Field(default_factory=list)


class EnvSettingsUpdateIn(BaseModel):
    values: dict[str, str | bool | int | float | None] = Field(default_factory=dict)


def _serialize_coupon(c: CouponResult) -> dict:
    return c.model_dump(mode="json")


def _parse_search_line(raw: str) -> tuple[str | None, str]:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Nhap domain, URL shop, hoac ten brand.")
    website: str | None = None
    brand: str | None = None
    try:
        website, brand = parse_domain_input(raw)
    except ValueError:
        brand = raw
    if not brand:
        raise ValueError("Khong suy ra duoc ten brand. Nhap ro hon.")
    return website, brand


def _parse_search_input(raw: str) -> tuple[str | None, str]:
    try:
        return _parse_search_line(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _normalize_domain_lines(domains: list[str]) -> list[str]:
    """Moi dong 1 domain/brand, bo trong, gop trung, toi da 5."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in domains:
        for line in str(raw or "").replace("\r\n", "\n").split("\n"):
            s = line.strip()
            if not s:
                continue
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
            if len(out) >= MAX_BATCH_DOMAINS:
                return out
    return out


def _search_response_payload(
    *,
    website: str | None,
    brand: str,
    report: SearchReport,
) -> dict:
    coupons = [_serialize_coupon(c) for c in report.results]
    preview = [_serialize_coupon(c) for c in report.collected_preview]
    trace_list = list(report.trace)
    website_out: str | None = website
    if not website_out:
        urls = [x.get("source_url") for x in coupons] + [x.get("source_url") for x in preview]
        inferred = infer_shop_website_from_coupon_source_urls(urls)
        if inferred:
            website_out = inferred
            trace_list.append(
                f"Chỉ nhập brand: suy ra domain shop để verify từ Simply Codes (/store/...) → {inferred}"
            )
        else:
            trace_list.append(
                "Chỉ nhập brand: không tìm thấy URL dạng simplycodes.com/store/{domain} trong kết quả — "
                "cần nhập domain shop (vd. ramonalarue.com) để verify."
            )
    return {
        "website": website_out,
        "brand_hint": brand,
        "raw_count": report.raw_count,
        "normalized_count": report.normalized_count,
        "coupons": coupons,
        "collected_preview": preview,
        "trace": trace_list,
        "user_message": report.user_message,
        "error_code": report.error_code,
    }


@router.get("/settings")
def ui_settings() -> dict:
    return {
        "verify_enabled": bool(settings.verify_enabled),
        "history_path": str(settings.ui_history_json),
        "license": license_status(),
    }


@router.get("/license")
def ui_license_get() -> dict:
    return license_status()


@router.post("/license/activate")
def ui_license_activate() -> dict:
    try:
        return activate_license()
    except LicenseError as exc:
        raise _license_http_error(exc) from exc


@router.get("/env")
def ui_env_get() -> dict:
    """Đọc cấu hình COUPON_FINDER_* từ .env (secret được mask)."""
    return get_env_settings_payload()


@router.put("/env")
def ui_env_put(body: EnvSettingsUpdateIn) -> dict:
    """Ghi cấu hình vào file .env và nạp lại settings runtime."""
    try:
        payload = apply_env_settings_from_ui(body.values)
        payload["license"] = license_status()
        if payload.get("license", {}).get("configured") and (settings.license_key or "").strip():
            try:
                payload["license"] = activate_license()
            except LicenseError as exc:
                payload["license"] = {
                    "ok": False,
                    "configured": True,
                    "message": exc.message,
                    "error_code": exc.code,
                    **exc.payload,
                }
        return payload
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Không ghi được file .env: {e}") from e


@router.get("/history")
async def ui_history_list() -> dict:
    sessions = await load_ui_history_sessions()
    return {"sessions": sessions, "path": str(settings.ui_history_json)}


@router.post("/history")
async def ui_history_append(body: HistorySessionIn) -> dict:
    sessions = await append_ui_history_session(body.model_dump(mode="json"))
    return {"sessions": sessions}


@router.post("/history/migrate")
async def ui_history_migrate(body: HistoryMigrateIn) -> dict:
    """Gộp lịch sử từ localStorage (client) vào file JSON một lần."""
    incoming = [s.model_dump(mode="json") for s in body.sessions]
    sessions = await merge_ui_history_sessions(incoming)
    return {"sessions": sessions, "merged": len(incoming)}


@router.post("/search")
async def ui_search(body: DomainSearchIn) -> dict:
    _require_license_searches(1)
    website, brand = _parse_search_input(body.domain)
    req = SearchRequest(brand=brand, website=website)
    try:
        report = await search(req, verify=False, limit_verify=0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=MSG_SYSTEM) from e
    return _search_response_payload(website=website, brand=brand, report=report)


@router.post("/search/stream")
async def ui_search_stream(body: DomainSearchIn) -> StreamingResponse:
    _require_license_searches(1)
    website, brand = _parse_search_input(body.domain)
    req = SearchRequest(brand=brand, website=website)
    queue: asyncio.Queue[dict] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_progress(percent: int, message: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "progress", "percent": percent, "message": message},
        )

    async def run_search() -> None:
        try:
            report = await search(req, verify=False, limit_verify=0, on_progress=on_progress)
            payload = _search_response_payload(website=website, brand=brand, report=report)
            await queue.put({"type": "done", "payload": payload})
        except SearchUserError as e:
            await queue.put(
                {
                    "type": "error",
                    "message": e.message,
                    "error_code": e.code,
                    "http_status": 200,
                }
            )
        except Exception:
            await queue.put(
                {"type": "error", "message": MSG_SYSTEM, "error_code": "system", "http_status": 500}
            )

    task = asyncio.create_task(run_search())

    async def event_stream():
        try:
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get("type") in ("done", "error"):
                    break
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/search/batch/stream")
async def ui_search_batch_stream(body: DomainsSearchIn, request: Request) -> StreamingResponse:
    items = _normalize_domain_lines(body.domains)
    if not items:
        raise HTTPException(
            status_code=400,
            detail="Nhap it nhat 1 domain, URL shop, hoac ten brand (toi da 5 dong).",
        )

    queue: asyncio.Queue[dict] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    total = len(items)

    async def run_batch() -> None:
        ok_items: list[dict] = []
        err_items: list[dict] = []
        try:
            try:
                _require_license_searches(len(items))
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
                await queue.put(
                    {
                        "type": "error",
                        "message": detail.get("message", "License không hợp lệ."),
                        "error_code": detail.get("error_code", "license"),
                        "http_status": 403,
                    }
                )
                return

            for i, domain_input in enumerate(items):
                if await request.is_disconnected():
                    await queue.put(
                        {
                            "type": "stopped",
                            "total": total,
                            "ok_count": len(ok_items),
                            "error_count": len(err_items),
                            "items": ok_items,
                            "errors": err_items,
                        }
                    )
                    return

                base_pct = int(i * 100 / total)

                def on_progress(pct: int, message: str, *, _i: int = i, _base: int = base_pct) -> None:
                    span = max(1, 100 // total)
                    overall = min(99, _base + int(pct * span / 100))
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {
                            "type": "progress",
                            "percent": overall,
                            "message": f"[{_i + 1}/{total}] {domain_input}: {message}",
                            "index": _i,
                            "total": total,
                            "domain": domain_input,
                        },
                    )

                try:
                    website, brand = _parse_search_line(domain_input)
                except ValueError as e:
                    err_items.append(
                        {"domain_input": domain_input, "message": str(e), "error_code": "invalid_input"}
                    )
                    await queue.put(
                        {
                            "type": "item_error",
                            "domain_input": domain_input,
                            "message": str(e),
                            "error_code": "invalid_input",
                        }
                    )
                    continue

                req = SearchRequest(brand=brand, website=website)
                try:
                    report = await search(req, verify=False, limit_verify=0, on_progress=on_progress)
                    payload = _search_response_payload(website=website, brand=brand, report=report)
                    ok_items.append({"domain_input": domain_input, "payload": payload})
                    await queue.put(
                        {
                            "type": "item_done",
                            "domain_input": domain_input,
                            "payload": payload,
                        }
                    )
                except SearchUserError as e:
                    err_items.append(
                        {
                            "domain_input": domain_input,
                            "message": e.message,
                            "error_code": e.code,
                        }
                    )
                    await queue.put(
                        {
                            "type": "item_error",
                            "domain_input": domain_input,
                            "message": e.message,
                            "error_code": e.code,
                        }
                    )

            await queue.put(
                {
                    "type": "done",
                    "total": total,
                    "ok_count": len(ok_items),
                    "error_count": len(err_items),
                    "items": ok_items,
                    "errors": err_items,
                }
            )
        except Exception:
            await queue.put(
                {"type": "error", "message": MSG_SYSTEM, "error_code": "system", "http_status": 500}
            )

    task = asyncio.create_task(run_batch())

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    if not task.done():
                        task.cancel()
                    break
                item = await queue.get()
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get("type") in ("done", "error", "stopped"):
                    break
        finally:
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/verify")
async def ui_verify(body: VerifyIn) -> dict:
    if not settings.verify_enabled:
        raise HTTPException(
            status_code=403,
            detail="Verify đang tắt trong cấu hình. Đặt COUPON_FINDER_VERIFY_ENABLED=true trong .env để bật lại.",
        )
    try:
        website, brand = parse_domain_input(body.domain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    codes = [normalize_code(c) for c in body.codes if (c or "").strip()]
    codes = list(dict.fromkeys(codes))[: int(body.max_codes)]
    if not codes:
        raise HTTPException(status_code=400, detail="Khong co ma hop le.")

    req = SearchRequest(brand=brand, website=website)
    now = datetime.utcnow()
    normalized: list[NormalizedCoupon] = []
    for code in codes:
        fp = fingerprint(code, None, website, brand)
        normalized.append(
            NormalizedCoupon(
                code=code,
                description=None,
                source=CouponSource.unknown,
                source_url=None,
                found_at=now,
                expires_at=None,
                fingerprint=fp,
                metadata={"ui_verify": True},
            )
        )

    records = [
        CouponRecord(
            brand=brand,
            website=website,
            product=None,
            category=None,
            code=c.code,
            fingerprint=c.fingerprint,
            description=c.description,
            source=c.source.value,
            source_url=c.source_url,
            source_discount=None,
            source_item_description=None,
            source_health_score=None,
            found_at=c.found_at,
            expires_at=c.expires_at,
        )
        for c in normalized
    ]
    upsert_many(records)

    pairs = await verify_all(req, normalized, concurrency=1)
    out: list[dict] = []
    for c, v in pairs:
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
        out.append(_serialize_coupon(res))

    return {"website": website, "brand_hint": brand, "results": out}
