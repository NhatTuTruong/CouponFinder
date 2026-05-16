"""
Shopify storefront verify (phase 1): Cart Ajax API — không dùng browser.

Flow: detect /cart.js → products.json → variant_id → POST /cart/add.js
→ GET /discount/{code} (cookie session) → GET /cart.js so sánh discount/tổng.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import quote, urlparse

import requests

from coupon_finder.config import settings
from coupon_finder.models import VerificationResult

logger = logging.getLogger(__name__)


def _storefront_origin(website: str) -> str:
    w = (website or "").strip()
    if not w:
        raise ValueError("empty website")
    if "://" not in w:
        w = "https://" + w
    p = urlparse(w)
    if not p.netloc:
        raise ValueError("invalid website")
    scheme = p.scheme if p.scheme in ("http", "https") else "https"
    return f"{scheme}://{p.netloc}".rstrip("/")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": settings.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return s


def _is_shopify_cart_shape(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return "token" in data and "items" in data and isinstance(data.get("items"), list)


def detect_shopify_storefront(origin: str, session: requests.Session) -> bool:
    """
    Nhận diện Shopify: JSON /cart.js chuẩn Ajax Cart, hoặc HTML có dấu hiệu Shopify.
    """
    try:
        r = session.get(f"{origin}/cart.js", timeout=20)
        if r.status_code == 200:
            try:
                data = r.json()
            except Exception:  # noqa: BLE001
                data = None
            if _is_shopify_cart_shape(data):
                return True
    except Exception as e:  # noqa: BLE001
        logger.debug("Shopify detect cart.js: %s", e)

    try:
        r = session.get(origin, timeout=20)
        if r.status_code != 200:
            return False
        text = r.text[:120_000].lower()
        markers = (
            "cdn.shopify.com",
            "shopify.theme",
            "shopify.shop",
            "shopify.loadfeatures",
            "shopifyanalytics",
            'type="application/json" id="shopify',
        )
        return any(m in text for m in markers)
    except Exception as e:  # noqa: BLE001
        logger.debug("Shopify detect homepage: %s", e)
        return False


def _variant_available(v: dict) -> bool:
    if v.get("available") is True:
        return True
    if v.get("available") is False:
        return False
    # Một số theme/API cũ không gửi available — thử dùng
    return True


def variant_ids_from_products_payload(payload: Any, *, max_ids: int = 40) -> list[int]:
    """Danh sách variant_id có thể thêm giỏ từ JSON /products.json (thứ tự xuất hiện)."""
    cap = max(1, min(80, int(max_ids)))
    products = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(products, list):
        return []
    out: list[int] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        for v in product.get("variants") or []:
            if not isinstance(v, dict):
                continue
            vid = v.get("id")
            if vid is None:
                continue
            if not _variant_available(v):
                continue
            try:
                i = int(vid)
            except (TypeError, ValueError):
                continue
            if i not in out:
                out.append(i)
            if len(out) >= cap:
                return out
    return out


def first_variant_id_from_products_payload(payload: Any) -> int | None:
    """Đọc JSON /products.json (object có key `products`) — variant đầu tiên khả dụng."""
    ids = variant_ids_from_products_payload(payload, max_ids=1)
    return ids[0] if ids else None


def pick_first_variant_id(origin: str, session: requests.Session) -> int | None:
    lim = max(1, min(50, int(settings.verify_shopify_products_limit)))
    r = session.get(f"{origin}/products.json", params={"limit": str(lim)}, timeout=25)
    if r.status_code != 200:
        return None
    try:
        payload = r.json()
    except Exception:  # noqa: BLE001
        return None
    return first_variant_id_from_products_payload(payload)


def _discount_code_status(cart: dict, code: str) -> str:
    """'ok' | 'rejected' | 'absent'"""
    want = code.strip().upper()
    for d in cart.get("discount_codes") or []:
        if not isinstance(d, dict):
            continue
        c = (d.get("code") or "").strip().upper()
        if c != want:
            continue
        if d.get("applicable") is True:
            return "ok"
        return "rejected"
    return "absent"


def _money_int(val: Any) -> int:
    if val is None:
        return 0
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _discount_hint_from_cart(cart: dict) -> str | None:
    apps = cart.get("cart_level_discount_applications") or []
    if isinstance(apps, list) and apps and isinstance(apps[0], dict):
        t = (apps[0].get("title") or "").strip()
        if t:
            return t[:120]
    td = cart.get("total_discount")
    if td not in (None, 0, "0", "0.0", "0.00"):
        return str(td)
    return None


def _is_transient_shopify_error(message: str) -> bool:
    m = (message or "").lower()
    keys = (
        "expecting value",
        "jsondecode",
        "connection",
        "timed out",
        "timeout",
        "429",
        "502",
        "503",
        "504",
        "remote end closed",
        "ssl",
        "read timed out",
        "http 429",
        "http 502",
        "http 503",
        "temporarily unavailable",
        "bad gateway",
    )
    return any(k in m for k in keys)


def _merge_discount_verdict(
    cart_a: dict,
    cart_b: dict,
    raw_code: str,
    *,
    price_before: int,
    discount_before: int,
) -> VerificationResult:
    """Hai lần đọc cart sau discount — ưu tiên applicable rõ ràng, rồi so tổng."""
    st_a = _discount_code_status(cart_a, raw_code)
    st_b = _discount_code_status(cart_b, raw_code)
    hint = _discount_hint_from_cart(cart_b) or _discount_hint_from_cart(cart_a)
    if st_a == "ok" or st_b == "ok":
        return VerificationResult(is_working=True, discount_text=hint, conditions_text=None, error=None)
    if st_a == "rejected" or st_b == "rejected":
        return VerificationResult(
            is_working=False,
            discount_text=None,
            conditions_text=None,
            error="shopify: discount code not applicable",
        )
    d_after = max(_money_int(cart_a.get("total_discount")), _money_int(cart_b.get("total_discount")))
    pa = _money_int(cart_a.get("total_price"))
    pb = _money_int(cart_b.get("total_price"))
    p_after = min(pa, pb) if (pa > 0 and pb > 0) else max(pa, pb)
    if d_after > discount_before or (price_before > 0 and p_after < price_before):
        return VerificationResult(is_working=True, discount_text=hint, conditions_text=None, error=None)
    return VerificationResult(
        is_working=False,
        discount_text=None,
        conditions_text=None,
        error="shopify: no discount applied (cart unchanged)",
    )


def _shopify_verify_core(session: requests.Session, origin: str, raw_code: str) -> VerificationResult:
    """Một phiên requests: clear → add → discount → đọc cart (có settle + đọc kép)."""
    origin = origin.rstrip("/")
    settle = min(3.0, max(0.0, float(settings.verify_shopify_settle_ms) / 1000.0))

    try:
        session.post(f"{origin}/cart/clear.js", timeout=20)
    except Exception as e:  # noqa: BLE001
        logger.debug("cart/clear.js: %s", e)

    lim = max(1, min(50, int(settings.verify_shopify_products_limit)))
    try:
        r_pr = session.get(f"{origin}/products.json", params={"limit": str(lim)}, timeout=25)
        if r_pr.status_code != 200:
            return VerificationResult(
                is_working=False,
                error=f"shopify products.json: HTTP {r_pr.status_code}",
            )
        payload = r_pr.json()
    except Exception as e:  # noqa: BLE001
        return VerificationResult(is_working=False, error=f"shopify products.json: {e}")

    max_v = max(1, min(60, int(settings.verify_shopify_playwright_variant_attempts)))
    vids = variant_ids_from_products_payload(payload, max_ids=max_v)
    if not vids:
        return VerificationResult(
            is_working=False,
            error="shopify: no available product variant (products.json)",
        )

    cart0: dict | None = None
    last_add_err = ""
    for variant_id in vids:
        try:
            r_add = session.post(
                f"{origin}/cart/add.js",
                json={"items": [{"id": variant_id, "quantity": 1}]},
                headers={"Content-Type": "application/json"},
                timeout=25,
            )
        except Exception as e:  # noqa: BLE001
            last_add_err = str(e)
            continue
        if r_add.status_code not in (200, 201):
            last_add_err = f"HTTP {r_add.status_code}"
            continue
        try:
            errj = r_add.json()
            if isinstance(errj, dict) and (errj.get("errors") or errj.get("status") in (422, "422")):
                last_add_err = str(errj.get("description") or errj.get("message") or "add rejected")
                continue
        except Exception:  # noqa: BLE001
            pass
        time.sleep(settle)
        try:
            r_cart0 = session.get(f"{origin}/cart.js", timeout=20)
            if r_cart0.status_code != 200:
                last_add_err = f"cart.js HTTP {r_cart0.status_code}"
                continue
            cand = r_cart0.json()
        except Exception as e:  # noqa: BLE001
            last_add_err = str(e)
            continue
        if not _is_shopify_cart_shape(cand):
            last_add_err = "unexpected cart.js shape"
            continue
        items = cand.get("items") or []
        if not isinstance(items, list) or len(items) == 0:
            last_add_err = "cart empty after add"
            continue
        cart0 = cand
        break

    if cart0 is None:
        msg = (last_add_err or "").strip() or "could not add any product to cart"
        return VerificationResult(is_working=False, error=f"shopify: {msg}")

    price_before = _money_int(cart0.get("total_price"))
    discount_before = _money_int(cart0.get("total_discount"))

    disc_path = quote(raw_code, safe="")
    try:
        session.get(
            f"{origin}/discount/{disc_path}",
            allow_redirects=True,
            timeout=25,
        )
    except Exception as e:  # noqa: BLE001
        return VerificationResult(is_working=False, error=f"shopify discount url: {e}")

    time.sleep(settle)

    try:
        r1 = session.get(f"{origin}/cart.js", timeout=20)
        if r1.status_code != 200:
            return VerificationResult(
                is_working=False,
                error=f"shopify cart.js after discount: HTTP {r1.status_code}",
            )
        cart_a = r1.json()
    except Exception as e:  # noqa: BLE001
        return VerificationResult(is_working=False, error=f"shopify cart.js after discount: {e}")

    if not _is_shopify_cart_shape(cart_a):
        return VerificationResult(is_working=False, error="shopify: invalid cart.js after discount")

    time.sleep(min(0.8, settle + 0.15))

    try:
        r2 = session.get(f"{origin}/cart.js", timeout=20)
        if r2.status_code != 200:
            return _merge_discount_verdict(cart_a, cart_a, raw_code, price_before=price_before, discount_before=discount_before)
        cart_b = r2.json()
    except Exception:  # noqa: BLE001
        cart_b = cart_a

    if not _is_shopify_cart_shape(cart_b):
        cart_b = cart_a

    return _merge_discount_verdict(
        cart_a,
        cart_b,
        raw_code,
        price_before=price_before,
        discount_before=discount_before,
    )


def try_verify_shopify_coupon(website: str, code: str) -> VerificationResult | None:
    """
    Nếu là Shopify storefront: trả VerificationResult (có retry khi lỗi tạm).
    Nếu không nhận ra Shopify sau mọi lần thử: trả None (caller dùng Playwright generic).
    """
    raw_code = (code or "").strip()
    if not raw_code:
        return VerificationResult(is_working=False, error="empty coupon code")

    try:
        origin = _storefront_origin(website)
    except ValueError as e:
        return VerificationResult(is_working=False, error=str(e))

    retries = max(1, int(settings.verify_shopify_retries))
    saw_shopify = False
    last: VerificationResult | None = None

    for attempt in range(retries):
        session = _session()
        try:
            if not detect_shopify_storefront(origin, session):
                time.sleep(0.2 * (attempt + 1))
                continue
            saw_shopify = True
            res = _shopify_verify_core(session, origin, raw_code)
            err = (res.error or "").strip()
            if err and (_is_transient_shopify_error(err) or any(x in err for x in ("HTTP 429", "HTTP 502", "HTTP 503", "HTTP 504"))):
                last = res
                time.sleep(0.35 * (attempt + 1))
                continue
            return res
        except Exception as e:  # noqa: BLE001
            msg = f"shopify: {e}"
            last = VerificationResult(is_working=False, error=msg)
            if _is_transient_shopify_error(msg):
                time.sleep(0.35 * (attempt + 1))
                continue
            return last

    if not saw_shopify:
        return None
    return last or VerificationResult(is_working=False, error="shopify: verify failed after retries")
