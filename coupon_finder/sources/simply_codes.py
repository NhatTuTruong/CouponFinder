from __future__ import annotations

import asyncio
import re
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from coupon_finder.config import settings
from coupon_finder.search_errors import (
    SearchUserError,
    apify_token_error,
    is_apify_auth_failure,
    not_found_error,
    search_error_from_exception,
    system_error,
)
from coupon_finder.domain_util import (
    is_simplycodes_domain_url,
    is_tenereteam_domain_url,
    parse_domain_input,
)
from coupon_finder.models import CouponSource, RawCoupon, SearchRequest
from coupon_finder.sources.apify_google import run_google_actor_queries_sync
from coupon_finder.sources.base import CouponCollector
from coupon_finder.search_progress import report_progress
from coupon_finder.sources.code_extract import host_label

_PLACEHOLDER_BTN = frozenset(
    {
        "show code",
        "get code",
        "copy code",
        "reveal",
        "reveal code",
        "click to copy",
        "show coupon",
        "view code",
        "see code",
        "tap to copy",
        "copy",
    }
)


def _resolve_brand(req: SearchRequest) -> str | None:
    b = (req.brand or "").strip()
    if b:
        return b
    if req.website:
        try:
            _, hint = parse_domain_input(req.website)
        except ValueError:
            return None
        return (hint or "").strip() or None
    return None


def _apify_search_query(brand: str) -> str:
    return f"{brand.strip()} coupon code simply codes"


def _apify_brand_only_google_query(brand: str) -> str:
    """Một khóa Google (Apify): coupon trên simplycodes.com hoặc tenereteam.com."""
    b = brand.strip()
    return f"{b} coupon (site:simplycodes.com OR site:tenereteam.com)"


def _brand_slug_for_tenereteam(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (brand or "").strip().lower()).strip("-")


def _tenereteam_host_from_url(url: str | None) -> str | None:
    if not is_tenereteam_domain_url(url):
        return None
    return (urlparse(url if "://" in (url or "") else f"https://{url}").netloc or "").lower().split(":")[
        0
    ].removeprefix("www.")


def _tenereteam_coupons_page_url(url: str | None) -> str | None:
    """Luôn scrape trang /coupons (dữ liệu mã & giảm giá chính xác hơn trang chủ)."""
    host = _tenereteam_host_from_url(url)
    if not host:
        return (url or "").strip() or None
    return f"https://{host}/coupons"


def _canonical_tenereteam_store_url(brand: str) -> str | None:
    slug = _brand_slug_for_tenereteam(brand)
    if not slug:
        return None
    return f"https://{slug}.tenereteam.com/coupons"


def _dedupe_links_by_url(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for u, t in links:
        url = (u or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append((url, str(t)))
    return out


def _pick_first_url_in_top_organic(
    links: list[tuple[str, str]],
    *,
    max_results: int = 5,
    host_ok,
) -> tuple[str | None, str | None]:
    """URL đầu tiên trong top organic thỏa host_ok(url)."""
    ordered = _dedupe_links_by_url(links)
    for url, title in ordered[: int(max_results)]:
        if host_ok(url):
            return url, title
    return None, None


def _pick_first_simplycodes_url_in_top_organic(
    links: list[tuple[str, str]],
    *,
    max_results: int = 5,
) -> tuple[str | None, str | None]:
    return _pick_first_url_in_top_organic(
        links, max_results=max_results, host_ok=is_simplycodes_domain_url
    )


def _tenereteam_pick_score(url: str, *, slug: str = "") -> int:
    if not is_tenereteam_domain_url(url):
        return -1
    host = _tenereteam_host_from_url(url) or ""
    path = (urlparse(url).path or "").lower()
    score = 0
    if "/coupons" in path:
        score += 80
    if slug and host == f"{slug}.tenereteam.com":
        score += 100
    elif slug and slug in host:
        score += 30
    return score


def _pick_first_tenereteam_url_in_top_organic(
    links: list[tuple[str, str]],
    *,
    max_results: int = 5,
    brand: str | None = None,
) -> tuple[str | None, str | None]:
    """Chỉ chấp nhận organic khi host khớp {slug}.tenereteam.com (score >= 100)."""
    slug = _brand_slug_for_tenereteam(brand or "")
    if not slug:
        return None, None
    ordered = _dedupe_links_by_url(links)
    best: tuple[int, str, str] | None = None
    for url, title in ordered:
        if not is_tenereteam_domain_url(url):
            continue
        sc = _tenereteam_pick_score(url, slug=slug)
        if sc < 100:
            continue
        if best is None or sc > best[0]:
            best = (sc, url, title)
    if best:
        u = _tenereteam_coupons_page_url(best[1]) or best[1]
        return u, best[2]
    return None, None


def is_simplycodes_store_page_url(url: str | None) -> bool:
    """
    URL kết quả phải liên quan trang store Simply Codes (chứa https://simplycodes.com/store
    hoặc https://www.simplycodes.com/store) và path /store/... hợp lệ.
    """
    raw = (url or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if "https://simplycodes.com/store" not in low and "https://www.simplycodes.com/store" not in low:
        return False
    try:
        p = urlparse(raw)
        host = (p.netloc or "").lower().split(":")[0]
        host = host.removeprefix("www.")
        if host != "simplycodes.com":
            return False
        return (p.path or "").lower().startswith("/store/")
    except Exception:  # noqa: BLE001
        return False


def _shop_slug_from_store_url(store_url: str) -> str | None:
    """Từ /store/babylonleather.com → babylonleather.com (dùng lọc data-merchant-url khi chỉ tìm brand)."""
    if not is_simplycodes_store_page_url(store_url):
        return None
    parts = [x for x in (urlparse(store_url).path or "").split("/") if x]
    if len(parts) >= 2 and parts[0].lower() == "store":
        return parts[1].lower()
    return None


def _bare_shop_host(website: str | None) -> str | None:
    """babylonleather.com từ https://www.babylonleather.com/..."""
    if not (website or "").strip():
        return None
    try:
        s = website.strip()
        if "://" not in s:
            s = "https://" + s
        p = urlparse(s)
        h = (p.netloc or "").lower()
        if not h and p.path:
            h = p.path.strip("/").split("/")[0].lower()
        h = h.split("@")[-1].split(":")[0]
        h = h.removeprefix("www.")
        if not h or "." not in h:
            return None
        return h
    except Exception:  # noqa: BLE001
        return None


def _canonical_simply_store_url(shop_host: str) -> str:
    return f"https://simplycodes.com/store/{shop_host.lstrip('.')}"


def _simply_page_score(url: str, *, shop_host: str | None = None) -> int:
    if not is_simplycodes_store_page_url(url):
        return -1
    path = (urlparse(url).path or "").lower().rstrip("/")
    score = 0
    if path.startswith("/store/"):
        score += 15
        sh = (shop_host or "").lower().rstrip("/")
        if sh and path == f"/store/{sh}":
            score += 60
    if any(x in path for x in ("promo", "coupon", "discount", "deal", "code")):
        score += 5
    return score


def _pick_simplycodes_store_url(links: list[tuple[str, str]], *, shop_host: str | None = None) -> str | None:
    scored: list[tuple[int, str]] = []
    for u, _t in links:
        if not is_simplycodes_store_page_url(u):
            continue
        s = _simply_page_score(u, shop_host=shop_host)
        if s >= 0:
            scored.append((s, u))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _clean_button_text(s: str) -> str:
    line = (s or "").split("\n")[0].strip()
    return " ".join(line.split())


def _is_placeholder_label(text: str) -> bool:
    t = text.strip().lower()
    if len(t) < 4:
        return True
    return t in _PLACEHOLDER_BTN


def _merchant_url_matches_shop(merchant_url: str | None, shop_host: str | None) -> bool:
    """Bỏ coupon của shop khác trên cùng trang (vd Macy's trong sidebar)."""
    if not shop_host:
        return True
    if not merchant_url:
        return True
    return shop_host.lower() in merchant_url.lower()


def _format_tenereteam_discount(disc: str | None) -> str | None:
    """Thêm % sau số giảm giá (vd. 10 → 10%)."""
    s = (disc or "").strip()
    if not s:
        return None
    if "%" in s:
        return s
    core = s.replace(",", "").replace(" ", "")
    if re.fullmatch(r"[\d.]+", core):
        return f"{s}%"
    return s


_TENERETEAM_BTN_SELECTOR = (
    '.btn-apply-coupon, .btn-apply-coupon-green, [class*="btn-apply-coupon"]'
)


async def _tenereteam_coupon_block_fields(btn) -> tuple[str | None, str | None]:
    """Giảm giá & mô tả từ khối coupon (layout Gaucho Ninja và Hampstead Tea)."""
    raw = await btn.evaluate(
        """el => {
            const pctFromText = (text) => {
                const t = (text || '').replace(/\\s+/g, ' ');
                const up = t.match(/up\\s+to\\s+(\\d+(?:\\.\\d+)?)\\s*%/i);
                if (up) return up[1];
                const m = t.match(/(\\d+(?:\\.\\d+)?)\\s*%/);
                return m ? m[1] : '';
            };
            const walkRoots = () => {
                const seen = new Set();
                const out = [];
                const add = (n) => {
                    if (n && !seen.has(n)) { seen.add(n); out.push(n); }
                };
                add(el.closest('[class*="coupon"]'));
                add(el.closest('article'));
                add(el.closest('li'));
                let node = el;
                for (let i = 0; i < 16 && node; i++) {
                    add(node);
                    node = node.parentElement;
                }
                return out;
            };
            let disc = '';
            let desc = '';
            for (const root of walkRoots()) {
                if (!disc) {
                    const sale = root.querySelector(
                        '.number-sale .number, .number-sale.number, .number-sale'
                    );
                    if (sale) {
                        const st = (sale.textContent || '').trim();
                        disc = pctFromText(st) || st.replace(/[^\\d.]/g, '');
                    }
                }
                if (!disc) {
                    const pct = pctFromText(root.innerText || '');
                    if (pct) disc = pct;
                }
                if (!desc) {
                    const box = root.querySelector('.content-items');
                    if (box) {
                        const ps = box.querySelectorAll(':scope > p, p');
                        if (ps.length) {
                            desc = Array.from(ps)
                                .map((p) => (p.textContent || '').trim())
                                .filter(Boolean)
                                .join(' ');
                        }
                    }
                }
                if (!desc) {
                    const h = root.querySelector('h3, h2');
                    if (h) {
                        const ht = (h.textContent || '').trim();
                        if (ht.length > 8) desc = ht;
                    }
                }
                if (!desc) {
                    const ps = root.querySelectorAll('p');
                    for (const p of ps) {
                        const pt = (p.textContent || '').trim();
                        if (pt.length > 24) {
                            desc = pt;
                            break;
                        }
                    }
                }
                if (disc && desc) break;
            }
            return { disc, desc };
        }"""
    )
    if not isinstance(raw, dict):
        raw = {}
    disc = _format_tenereteam_discount(str(raw.get("disc") or "").strip() or None)
    desc_s = str(raw.get("desc") or "").strip()
    return disc, desc_s or None


async def _scrape_tenereteam_codes(page_url: str) -> list[tuple[str, str | None, str | None, str | None]]:
    """TenereTeam: mã span.code; giảm giá .number-sale .number (+ %); mô tả .content-items > p."""
    page_url = _tenereteam_coupons_page_url(page_url) or page_url
    if not is_tenereteam_domain_url(page_url):
        return []
    out: list[tuple[str, str | None, str | None, str | None]] = []
    async with async_playwright() as p:
        launch_kw: dict = {
            "headless": settings.headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        ch = (settings.playwright_channel or "").strip()
        if ch:
            launch_kw["channel"] = ch
        browser = await p.chromium.launch(**launch_kw)
        context = await browser.new_context(
            user_agent=settings.user_agent,
            viewport={"width": 1365, "height": 900},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        page.set_default_timeout(settings.verify_timeout_ms)
        try:
            await page.goto(page_url, wait_until="domcontentloaded")
            try:
                await page.locator(_TENERETEAM_BTN_SELECTOR).first.wait_for(
                    state="attached", timeout=25_000
                )
            except Exception:  # noqa: BLE001
                pass
            for _ in range(8):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.35)
            btn_loc = page.locator(_TENERETEAM_BTN_SELECTOR)
            btn_count = await btn_loc.count()
            sale_texts: list[str] = []
            sale_loc = page.locator(".number-sale .number")
            sale_n = await sale_loc.count()
            for j in range(min(sale_n, 500)):
                t = await sale_loc.nth(j).evaluate("el => (el.textContent || '').trim()")
                if (t or "").strip():
                    sale_texts.append(t.strip())

            desc_texts: list[str] = []
            items_loc = page.locator(".content-items")
            items_n = await items_loc.count()
            for j in range(min(items_n, 500)):
                t = await items_loc.nth(j).evaluate(
                    """box => {
                        const ps = box.querySelectorAll(':scope > p');
                        if (!ps.length) {
                            const p = box.querySelector('p');
                            return p ? (p.textContent || '').trim() : '';
                        }
                        return Array.from(ps)
                            .map((p) => (p.textContent || '').trim())
                            .filter(Boolean)
                            .join(' ');
                    }"""
                )
                if (t or "").strip():
                    desc_texts.append(t.strip())
            if not desc_texts:
                h_loc = page.locator("h3")
                h_n = await h_loc.count()
                for j in range(min(h_n, 500)):
                    t = await h_loc.nth(j).evaluate("el => (el.textContent || '').trim()")
                    if len((t or "").strip()) > 8:
                        desc_texts.append(t.strip())

            for i in range(min(btn_count, 500)):
                btn = btn_loc.nth(i)
                code_el = btn.locator("span.code")
                if await code_el.count() == 0:
                    continue
                raw = await code_el.first.evaluate("el => (el.textContent || '').trim()")
                cleaned = _clean_button_text(raw)
                if not cleaned or _is_placeholder_label(cleaned):
                    continue
                disc, item_descr = await _tenereteam_coupon_block_fields(btn)
                if not disc and i < len(sale_texts):
                    disc = _format_tenereteam_discount(sale_texts[i])
                if not item_descr and i < len(desc_texts):
                    item_descr = desc_texts[i] or None
                out.append((cleaned, disc, item_descr, None))
        finally:
            await context.close()
            await browser.close()

    seen: set[str] = set()
    uniq: list[tuple[str, str | None, str | None, str | None]] = []
    for code, disc, item_descr, health in out:
        k = code.strip().upper()
        if k in seen:
            continue
        seen.add(k)
        uniq.append((code.strip(), disc, item_descr, health))
    return uniq


async def _scrape_btn_show_codes(
    page_url: str, *, shop_host: str | None = None
) -> list[tuple[str, str | None, str | None, str | None]]:
    """Chỉ simplycodes.com — nút .btn-show-code (data-code / inner_text)."""
    if not is_simplycodes_domain_url(page_url):
        return []
    out: list[tuple[str, str | None, str | None, str | None]] = []
    async with async_playwright() as p:
        launch_kw: dict = {
            "headless": settings.headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        ch = (settings.playwright_channel or "").strip()
        if ch:
            launch_kw["channel"] = ch
        browser = await p.chromium.launch(**launch_kw)
        context = await browser.new_context(
            user_agent=settings.user_agent,
            viewport={"width": 1365, "height": 900},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            },
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        page.set_default_timeout(settings.verify_timeout_ms)
        try:
            await page.goto(page_url, wait_until="domcontentloaded")
            prev = 0
            for _ in range(25):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.4)
                n = await page.locator(".btn-show-code").count()
                if n == prev and n > 0:
                    break
                prev = n

            loc = page.locator(".btn-show-code")
            try:
                await loc.first.wait_for(state="attached", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            count = await loc.count()
            for i in range(min(count, 800)):
                el = loc.nth(i)
                murl = await el.get_attribute("data-merchant-url")
                if not _merchant_url_matches_shop(murl, shop_host):
                    continue
                disc_raw = await el.get_attribute("data-discount")
                disc = (disc_raw or "").strip() or None
                descr_raw = await el.get_attribute("data-description")
                item_descr = (descr_raw or "").strip() or None
                health_raw = await el.get_attribute("data-health-score")
                health = (health_raw or "").strip() or None
                data_code = await el.get_attribute("data-code")
                if data_code and (dc := data_code.strip()):
                    out.append((dc, disc, item_descr, health))
                    continue
                raw = await el.inner_text()
                cleaned = _clean_button_text(raw)
                if not cleaned or _is_placeholder_label(cleaned):
                    continue
                out.append((cleaned, disc, item_descr, health))
        finally:
            await context.close()
            await browser.close()

    seen: set[str] = set()
    uniq: list[tuple[str, str | None, str | None, str | None]] = []
    for code, disc, item_descr, health in out:
        k = code.strip().upper()
        if k in seen:
            continue
        seen.add(k)
        uniq.append((code.strip(), disc, item_descr, health))
    return uniq


class SimplyCodesCollector(CouponCollector):
    """
    Chỉ dùng trang https://simplycodes.com/store/... (kể cả www). Không homepage /stores/ khác.
    Domain shop: Apify + URL canonical /store/{domain} → Playwright.
    Chỉ brand: Apify → Simply Codes; fallback TenereTeam tại /coupons (mã, giảm giá %, mô tả).
    Domain shop: chỉ Simply Codes (cấu trúc cũ).
    """

    name = "simply_codes"

    async def collect(self, req: SearchRequest) -> list[RawCoupon]:
        if not (settings.apify_token or "").strip():
            raise apify_token_error()

        brand = _resolve_brand(req)
        if not brand:
            raise not_found_error()

        shop_host = _bare_shop_host(req.website)
        title_hint = ""
        q = ""
        store_url: str | None = None
        pick_mode = "domain_canonical" if shop_host else "brand_simplycodes"
        codes: list[tuple[str, str | None, str | None, str | None]] = []
        tenereteam_url: str | None = None
        tenereteam_title = ""

        try:
            organic_cap = max(1, min(20, int(settings.apify_results_per_page)))

            def _run_apify(query: str) -> list[tuple[str, str]]:
                return run_google_actor_queries_sync(query)

            report_progress(18, "Tìm trang coupon trên Google (Apify)…")
            if shop_host:
                q = _apify_search_query(brand)
                links = await asyncio.to_thread(_run_apify, q)
                links = links[:organic_cap]
                canon = _canonical_simply_store_url(shop_host)
                links = [(canon, f"Simply Codes /store/{shop_host}")] + list(links)
                store_url = _pick_simplycodes_store_url(links, shop_host=shop_host)
                if not store_url:
                    store_url = canon
                for u, t in links:
                    if u == store_url:
                        title_hint = t
                        break
                report_progress(38, "Chọn trang Simply Codes…")
            else:
                q = _apify_brand_only_google_query(brand)
                links = await asyncio.to_thread(_run_apify, q)
                links = links[:organic_cap]
                if not links:
                    raise not_found_error()
                simply_url, simply_title = _pick_first_simplycodes_url_in_top_organic(
                    links, max_results=organic_cap
                )
                tenereteam_url, tenereteam_title = _pick_first_tenereteam_url_in_top_organic(
                    links, max_results=organic_cap, brand=brand
                )
                canon_tt = _canonical_tenereteam_store_url(brand)
                if tenereteam_url:
                    tenereteam_url = _tenereteam_coupons_page_url(tenereteam_url) or tenereteam_url
                elif canon_tt:
                    tenereteam_url = canon_tt
                    tenereteam_title = f"TenereTeam — {brand}"
                store_url = simply_url
                title_hint = simply_title or ""
                report_progress(38, "Chọn trang Simply Codes / TenereTeam…")
        except SearchUserError:
            raise
        except Exception as e:  # noqa: BLE001
            if settings.debug:
                import traceback

                traceback.print_exc()
            raise search_error_from_exception(e) from e

        filter_slug = shop_host or (_shop_slug_from_store_url(store_url) if store_url else None)

        try:
            if shop_host:
                if not store_url or not is_simplycodes_domain_url(store_url):
                    raise not_found_error()
                report_progress(48, "Lấy mã từ Simply Codes…")
                codes = await _scrape_btn_show_codes(store_url, shop_host=filter_slug)
            else:
                if store_url and is_simplycodes_domain_url(store_url):
                    report_progress(48, "Lấy mã từ Simply Codes…")
                    codes = await _scrape_btn_show_codes(store_url, shop_host=filter_slug)
                if not codes and tenereteam_url:
                    store_url = tenereteam_url
                    pick_mode = "brand_tenereteam_fallback"
                    title_hint = tenereteam_title or title_hint
                    report_progress(62, "Lấy mã từ TenereTeam…")
                    codes = await _scrape_tenereteam_codes(tenereteam_url)
                elif not codes and not store_url and not tenereteam_url:
                    raise not_found_error()
        except SearchUserError:
            raise
        except Exception as e:  # noqa: BLE001
            if settings.debug:
                import traceback

                traceback.print_exc()
            if is_apify_auth_failure(e):
                raise apify_token_error() from e
            raise system_error() from e

        if not codes or not store_url:
            raise not_found_error()

        report_progress(74, f"Đã thu thập {len(codes)} mã")
        now = datetime.utcnow()
        desc_base = (title_hint[:240] if title_hint else f"{host_label(store_url)}")[:500]
        raw_out: list[RawCoupon] = []
        for code, src_disc, src_item_desc, health_score in codes:
            meta: dict = {
                "collector": self.name,
                "apify_query": q,
                "simplycodes_page": store_url,
                "simply_pick_mode": pick_mode,
            }
            if src_disc:
                meta["source_discount"] = src_disc
            if src_item_desc:
                meta["source_item_description"] = src_item_desc
            if health_score:
                meta["source_health_score"] = health_score
            raw_out.append(
                RawCoupon(
                    code=code,
                    description=desc_base or None,
                    source=CouponSource.coupon_site,
                    source_url=store_url,
                    found_at=now,
                    metadata=meta,
                )
            )
        return raw_out
