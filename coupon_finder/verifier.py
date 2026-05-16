from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import Locator, async_playwright

from coupon_finder.config import settings
from coupon_finder.models import NormalizedCoupon, SearchRequest, VerificationResult
from coupon_finder.shopify_verify import (
    _is_shopify_cart_shape,
    variant_ids_from_products_payload,
    try_verify_shopify_coupon,
)


@dataclass
class VerifyContext:
    req: SearchRequest


_COUPON_INPUT_HINTS = [
    "coupon",
    "promo",
    "promotion",
    "discount",
    "voucher",
    "mã giảm",
    "ma giam",
    "ưu đãi",
    "uu dai",
]

_APPLY_BUTTON_HINTS = [
    "apply",
    "add",
    "use",
    "ok",
    "áp dụng",
    "ap dung",
]


def _looks_like_coupon_field(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in _COUPON_INPUT_HINTS)


def _looks_like_apply_button(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in _APPLY_BUTTON_HINTS)


async def _find_coupon_input(page) -> Locator | None:
    inputs = page.locator("input, textarea")
    count = await inputs.count()
    for i in range(min(count, 80)):
        el = inputs.nth(i)
        attrs = [
            await el.get_attribute("name"),
            await el.get_attribute("id"),
            await el.get_attribute("placeholder"),
            await el.get_attribute("aria-label"),
            await el.get_attribute("data-testid"),
        ]
        if any(a and _looks_like_coupon_field(a) for a in attrs):
            return el
    return None


async def _find_page_with_coupon_input(
    page, candidate_urls: list[str]
) -> tuple[Locator | None, str | None]:
    """Lần lượt mở từng URL; trả về (ô coupon, None) hoặc (None, lỗi)."""
    last_err: str | None = None
    for u in candidate_urls:
        try:
            await page.goto(u, wait_until="domcontentloaded")
            last_err = None
        except Exception as e:  # noqa: BLE001
            last_err = f"goto failed: {e}"
            continue
        inp = await _find_coupon_input(page)
        if inp is not None:
            return inp, None
    return None, last_err or "coupon input not found"


_ADD_TO_CART_SELECTORS = [
    '[data-testid="add-to-cart-button"]',
    '[data-testid="add-to-cart"]',
    "button#add-to-cart-button",
    "#add-to-cart-button",
    "#add-to-cart",
    "button.single_add_to_cart_button",
    "button.product-form__submit",
    'button[id*="ProductSubmit"]',
    "button[name='add']",
    "input[type='submit'][name='add']",
    "form[action*='cart'] button[type='submit']",
    "[type='submit'][name='add']",
]


async def _try_click_add_to_cart(page) -> None:
    """Best-effort: không raise — nhiều theme khác nhau."""
    custom = (settings.verify_seed_add_to_cart_css or "").strip()
    order = ([custom] if custom else []) + [s for s in _ADD_TO_CART_SELECTORS if s != custom]
    for sel in order:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            await loc.click(timeout=4_000)
            return
        except Exception:  # noqa: BLE001
            continue
    for label in ("add to cart", "add to bag", "add to basket", "mua ngay", "buy now"):
        try:
            await page.get_by_role("button", name=re.compile(label, re.I)).first.click(timeout=2_500)
            return
        except Exception:  # noqa: BLE001
            continue


async def _try_seed_add_to_cart(page) -> None:
    """Nếu cấu hình COUPON_FINDER_VERIFY_SEED_PRODUCT_URL: mở PDP và thử thêm giỏ."""
    seed = (settings.verify_seed_product_url or "").strip()
    if not seed:
        return
    try:
        await page.goto(seed, wait_until="domcontentloaded")
    except Exception:  # noqa: BLE001
        return
    await _try_click_add_to_cart(page)
    wait_s = min(60.0, max(0.0, float(settings.verify_seed_wait_ms) / 1000.0))
    if wait_s > 0:
        await asyncio.sleep(wait_s)


async def _async_cart_line_count_shopify(page, origin: str) -> int:
    """Số dòng trong giỏ (Ajax cart.js)."""
    origin = origin.rstrip("/")
    try:
        r = await page.request.get(f"{origin}/cart.js", timeout=18_000)
        if r.status != 200:
            return 0
        data = await r.json()
    except Exception:  # noqa: BLE001
        return 0
    if not isinstance(data, dict):
        return 0
    items = data.get("items")
    if not isinstance(items, list):
        return 0
    return len(items)


async def _try_cart_add_js_playwright(page, origin: str, variant_id: int) -> bool:
    """POST /cart/add.js; True nếu sau đó cart có line."""
    origin = origin.rstrip("/")
    headers = {"Content-Type": "application/json"}
    try:
        r = await page.request.post(
            f"{origin}/cart/add.js",
            json={"items": [{"id": int(variant_id), "quantity": 1}]},
            headers=headers,
            timeout=25_000,
        )
    except TypeError:
        try:
            r = await page.request.post(
                f"{origin}/cart/add.js",
                data=json.dumps({"items": [{"id": int(variant_id), "quantity": 1}]}),
                headers=headers,
                timeout=25_000,
            )
        except Exception:  # noqa: BLE001
            return False
    except Exception:  # noqa: BLE001
        return False
    if r.status not in (200, 201):
        return False
    try:
        body = await r.json()
        if isinstance(body, dict):
            st = body.get("status")
            if st in (422, "422", "bad_request") or body.get("errors"):
                return False
    except Exception:  # noqa: BLE001
        pass
    await asyncio.sleep(0.15)
    return await _async_cart_line_count_shopify(page, origin) > 0


async def _try_cart_add_via_get_navigate(page, origin: str, variant_id: int) -> bool:
    """GET /cart/add?id=&quantity=1 trong tab (một số theme/chặn JSON vẫn nhận)."""
    origin = origin.rstrip("/")
    url = f"{origin}/cart/add?id={int(variant_id)}&quantity=1"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=min(55_000, settings.verify_timeout_ms))
        await asyncio.sleep(0.4)
    except Exception:  # noqa: BLE001
        return False
    return await _async_cart_line_count_shopify(page, origin) > 0


async def _try_seed_shopify_via_collection_pdp(page, origin: str) -> bool:
    """Mở collection / trang chủ → link PDP đầu tiên → thử Add to cart."""
    origin = origin.rstrip("/")
    candidates = (
        f"{origin}/collections/all",
        f"{origin}/collections/new-arrivals",
        f"{origin}/collections/sale",
        f"{origin}/collections/shop-all",
        f"{origin}/collections/shop",
        f"{origin}/",
    )
    for start_url in candidates:
        try:
            await page.goto(
                start_url,
                wait_until="domcontentloaded",
                timeout=min(55_000, settings.verify_timeout_ms),
            )
        except Exception:  # noqa: BLE001
            continue
        await asyncio.sleep(0.45)
        try:
            loc = page.locator('a[href*="/products/"]').first
            if await loc.count() == 0:
                continue
            href = await loc.get_attribute("href")
            if not href or "/products/" not in href.lower():
                continue
            pdp = urljoin(origin + "/", href)
            await page.goto(pdp, wait_until="domcontentloaded", timeout=min(55_000, settings.verify_timeout_ms))
            await asyncio.sleep(0.4)
            await _try_click_add_to_cart(page)
            await asyncio.sleep(0.55)
            if await _async_cart_line_count_shopify(page, origin) > 0:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


async def _try_seed_shopify_cart_via_playwright_request(page, origin: str) -> bool:
    """
    Shopify + Playwright: đảm bảo giỏ có line item trước khi tìm ô discount.
    Thử nhiều variant (add.js) → /cart/add GET → duyệt collection + PDP.
    Trả True nếu giỏ không rỗng.
    """
    origin = origin.rstrip("/")
    try:
        await page.goto(origin, wait_until="domcontentloaded", timeout=min(60_000, settings.verify_timeout_ms))
    except Exception:  # noqa: BLE001
        return False

    try:
        cj = await page.request.get(f"{origin}/cart.js", timeout=20_000)
        if cj.status == 200:
            data = await cj.json()
            if _is_shopify_cart_shape(data):
                try:
                    await page.request.post(f"{origin}/cart/clear.js", timeout=20_000)
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass

    lim = max(1, min(50, int(settings.verify_shopify_products_limit)))
    try:
        pr = await page.request.get(f"{origin}/products.json", params={"limit": str(lim)}, timeout=25_000)
        if pr.status != 200:
            ok = await _try_seed_shopify_via_collection_pdp(page, origin)
            if ok:
                settle_s = min(3.0, max(0.0, float(settings.verify_shopify_settle_ms) / 1000.0))
                await asyncio.sleep(max(0.35, settle_s * 0.6))
            return ok
        payload = await pr.json()
    except Exception:  # noqa: BLE001
        ok = await _try_seed_shopify_via_collection_pdp(page, origin)
        if ok:
            settle_s = min(3.0, max(0.0, float(settings.verify_shopify_settle_ms) / 1000.0))
            await asyncio.sleep(max(0.35, settle_s * 0.6))
        return ok

    max_try = max(1, min(60, int(settings.verify_shopify_playwright_variant_attempts)))
    vids = variant_ids_from_products_payload(payload, max_ids=max_try)
    if not vids:
        ok = await _try_seed_shopify_via_collection_pdp(page, origin)
        if ok:
            settle_s = min(3.0, max(0.0, float(settings.verify_shopify_settle_ms) / 1000.0))
            await asyncio.sleep(max(0.35, settle_s * 0.6))
        return ok

    settle_s = min(3.0, max(0.0, float(settings.verify_shopify_settle_ms) / 1000.0))
    settle_sleep = max(0.35, settle_s * 0.6)

    for vid in vids:
        if await _try_cart_add_js_playwright(page, origin, vid):
            await asyncio.sleep(settle_sleep)
            return True

    for vid in vids[: min(12, len(vids))]:
        if await _try_cart_add_via_get_navigate(page, origin, vid):
            await asyncio.sleep(settle_sleep)
            return True

    if await _try_seed_shopify_via_collection_pdp(page, origin):
        await asyncio.sleep(settle_sleep)
        return True

    return False


_INVALID_BODY_MARKERS = [
    "invalid",
    "not valid",
    "expired",
    "doesn't exist",
    "không hợp lệ",
    "het han",
    "hết hạn",
    "sai mã",
]
_SUCCESS_BODY_MARKERS = [
    "applied",
    "added",
    "success",
    "đã áp dụng",
    "áp dụng thành công",
]
_DISCOUNT_BODY_RE = re.compile(
    r"(\d{1,2}\s*%|\d{1,3}\s*(?:k|000)\b|freeship|free ship|miễn phí vận chuyển)",
    re.I,
)


async def _playwright_poll_discount_verdict(page) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Đọc body nhiều lần sau khi chờ settle — bỏ phiếu để giảm kết quả lật khi DOM đang render.
    Trả (is_working, discount_text, error).
    """
    settle_s = min(3.0, max(0.0, float(settings.verify_playwright_settle_ms) / 1000.0))
    polls = max(1, min(5, int(settings.verify_playwright_body_polls)))
    await asyncio.sleep(settle_s)

    samples: list[tuple[bool, bool, Optional[str]]] = []
    between = 0.35
    for pi in range(polls):
        if pi > 0:
            await asyncio.sleep(between)
        try:
            body_text = (await page.locator("body").inner_text())[:12_000]
        except Exception:  # noqa: BLE001
            body_text = ""
        lt = body_text.lower()
        is_invalid = any(m in lt for m in _INVALID_BODY_MARKERS)
        is_success = any(m in lt for m in _SUCCESS_BODY_MARKERS)
        m = _DISCOUNT_BODY_RE.search(lt)
        discount_text: Optional[str] = m.group(0) if m else None
        samples.append((is_invalid, is_success, discount_text))

    maj = (polls + 1) // 2
    reject_votes = sum(1 for inv, suc, disc in samples if inv and not suc and not disc)
    working_votes = sum(1 for _inv, suc, disc in samples if suc or disc)
    disc_first = next((d for _i, _s, d in samples if d), None)

    if reject_votes >= maj and working_votes == 0:
        return False, None, "coupon rejected by site text"
    if working_votes >= maj:
        return True, disc_first, None
    if working_votes >= 1 and reject_votes < maj:
        return True, disc_first, None
    if reject_votes >= maj:
        return False, None, "coupon rejected by site text"
    return False, None, "no confirmation detected"


async def verify_coupon(c: NormalizedCoupon, ctx: VerifyContext) -> VerificationResult:
    # 4) Kiểm tra coupon thực tế (heuristic, vì mỗi site checkout khác nhau)
    if not settings.verify_enabled:
        return VerificationResult(
            is_working=False,
            error="verify tạm tắt (COUPON_FINDER_VERIFY_ENABLED=false)",
        )
    if not ctx.req.website:
        return VerificationResult(is_working=False, error="missing website")

    if settings.verify_use_shopify_cart_api:
        shopify_res = await asyncio.to_thread(try_verify_shopify_coupon, ctx.req.website, c.code)
        if shopify_res is not None:
            return shopify_res

    url = ctx.req.website.rstrip("/")
    candidate_urls = [url, f"{url}/cart", f"{url}/checkout"]

    async with async_playwright() as p:
        launch_kw: dict = {"headless": settings.headless}
        if (ch := (settings.playwright_channel or "").strip()):
            launch_kw["channel"] = ch
        browser = await p.chromium.launch(**launch_kw)
        page = await browser.new_page(user_agent=settings.user_agent)
        page.set_default_timeout(settings.verify_timeout_ms)

        try:
            await _try_seed_add_to_cart(page)
            await _try_seed_shopify_cart_via_playwright_request(page, url)

            coupon_input, nav_err = await _find_page_with_coupon_input(page, candidate_urls)
            if coupon_input is None:
                return VerificationResult(is_working=False, error=nav_err or "coupon input not found")

            await coupon_input.click()
            await coupon_input.fill(c.code)

            try:
                await coupon_input.press("Enter")
            except Exception:  # noqa: BLE001
                pass

            buttons = page.locator("button, input[type='submit'], a[role='button']")
            bcount = await buttons.count()
            for i in range(min(bcount, 80)):
                b = buttons.nth(i)
                txt = (await b.inner_text()) if await b.count() else ""
                val = await b.get_attribute("value")
                aria = await b.get_attribute("aria-label")
                if _looks_like_apply_button(txt) or _looks_like_apply_button(val or "") or _looks_like_apply_button(aria or ""):
                    try:
                        await b.click(timeout=3000)
                        break
                    except Exception:  # noqa: BLE001
                        continue

            ok, discount_text, err = await _playwright_poll_discount_verdict(page)
            if ok:
                return VerificationResult(is_working=True, discount_text=discount_text, conditions_text=None, error=None)
            return VerificationResult(
                is_working=False,
                discount_text=None,
                conditions_text=None,
                error=err or "no confirmation detected",
            )
        except Exception as e:  # noqa: BLE001
            return VerificationResult(is_working=False, error=str(e))
        finally:
            await page.close()
            await browser.close()
