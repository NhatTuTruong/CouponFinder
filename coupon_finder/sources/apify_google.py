from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from coupon_finder.config import settings
from coupon_finder.search_errors import SearchUserError, search_error_from_exception
from coupon_finder.domain_util import is_simplycodes_domain_url
from coupon_finder.models import CouponSource, RawCoupon, SearchRequest
from coupon_finder.sources.base import CouponCollector
from coupon_finder.sources.code_extract import extract_candidate_codes, host_label

logger = logging.getLogger(__name__)


def _apify_results_cap(explicit: int | None = None) -> int:
    if explicit is not None:
        return max(1, min(20, int(explicit)))
    return max(1, min(20, int(settings.apify_results_per_page)))


def _apify_max_pages(explicit: int | None = None) -> int:
    if explicit is not None:
        return max(1, min(20, int(explicit)))
    return max(1, min(20, int(settings.apify_max_pages_per_query)))


def _coupon_site_domains_or_clause() -> str:
    parts = [x.strip() for x in settings.apify_coupon_site_domains.split(",") if x.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return f"site:{parts[0]}"
    inner = " OR ".join(f"site:{d}" for d in parts)
    return f"({inner})"


def _build_queries(req: SearchRequest) -> str:
    """Một dòng query (mặc định) — 1 lần search trên Apify / run."""
    brand = (req.brand or "").strip()
    product = (req.product or "").strip()
    site = host_label(req.website or "")
    sites = _coupon_site_domains_or_clause()

    if brand and product and site:
        return f"site:{site} {brand} {product} coupon OR promo code"
    if brand and site:
        base = f"{brand} coupon OR promo code OR discount"
        return f"site:{site} {base}" if not sites else f"{base} {sites}"
    if brand:
        base = f"{brand} coupon code OR promo code"
        return f"{base} {sites}".strip() if sites else base
    if site:
        return f"site:{site} coupon OR promo code OR discount"
    return "retail coupon codes deals"


def _build_queries_multi(req: SearchRequest) -> str:
    """Nhiều dòng query (tốn Usage) — chỉ khi COUPON_FINDER_APIFY_MULTI_QUERY=true."""
    lines: list[str] = []
    brand = (req.brand or "").strip()
    product = (req.product or "").strip()
    site = host_label(req.website or "")

    if brand:
        lines.append(f"{brand} coupon code")
        lines.append(f"{brand} promo code OR discount code")
        lines.append(f'"{brand}" voucher OR sitewide')
    if site:
        lines.append(f"site:{site} coupon OR promo code OR discount")
    if brand and product:
        lines.append(f"{brand} {product} coupon OR promo code")

    for d in (x.strip() for x in settings.apify_coupon_site_domains.split(",") if x.strip()):
        if brand:
            lines.append(f"site:{d} {brand} coupon")
        elif site:
            lines.append(f"site:{d} {site} coupon")

    return "\n".join(lines) if lines else "retail coupon codes deals"


def build_apify_queries(req: SearchRequest) -> str:
    if settings.apify_multi_query:
        return _build_queries_multi(req)
    return _build_queries(req)


def _organic_rows(item: dict) -> list[dict]:
    """
    Output google-search-scraper: thường là { organicResults: [ {title, url, description}, ... ] }
    hoặc một dòng organic đã unwind.
    """
    org = item.get("organicResults") or item.get("organic_results")
    if isinstance(org, dict):
        org = [org]
    if isinstance(org, list) and org:
        return [x for x in org if isinstance(x, dict)]
    if isinstance(item.get("title"), str):
        if any(
            isinstance(item.get(k), str) and str(item[k]).startswith("http")
            for k in ("url", "link", "pageUrl")
        ):
            return [item]
        if item.get("description") or item.get("snippet"):
            return [item]
    return []


def _organic_url_title(o: dict) -> tuple[str | None, str]:
    title = str(o.get("title") or o.get("pageTitle") or o.get("htmlTitle") or "")
    for k in ("url", "link", "pageUrl"):
        v = o.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v, title
    return None, title


def _google_actor_base(
    queries: str,
    *,
    max_pages: int | None = None,
    results_per_page: int | None = None,
) -> dict[str, Any]:
    """Payload Actor Google (queries tùy ý, chưa gắn site merchant)."""
    mp = _apify_max_pages(max_pages)
    rpp = _apify_results_cap(results_per_page)
    base: dict[str, Any] = {
        "queries": queries,
        "maxPagesPerQuery": mp,
        "resultsPerPage": rpp,
        "disableGoogleSearchResults": False,
        "aiModeSearch": {"enableAiMode": settings.apify_enable_ai_mode},
        "perplexitySearch": {
            "enablePerplexity": settings.apify_enable_perplexity,
            "searchRecency": "month",
            "returnImages": False,
            "returnRelatedQuestions": False,
        },
        "chatGptSearch": {"enableChatGpt": settings.apify_enable_chatgpt},
        "copilotSearch": {
            "enableCopilot": settings.apify_enable_copilot,
            "copilotSearchMode": "chat",
        },
        "maximumLeadsEnrichmentRecords": 0,
        "verifyLeadsEnrichmentEmails": False,
        "focusOnPaidAds": settings.apify_focus_on_paid_ads,
        "countryCode": settings.apify_country_code,
        "searchLanguage": settings.apify_search_language,
        "languageCode": settings.apify_language_code,
        "forceExactMatch": False,
        "mobileResults": False,
        "includeUnfilteredResults": False,
        "saveHtml": False,
        "saveHtmlToKeyValueStore": False,
    }
    extra = settings.apify_run_input_extra_json
    if extra and extra.strip():
        try:
            merged = json.loads(extra)
            if isinstance(merged, dict):
                base.update(merged)
        except json.JSONDecodeError:
            pass
    return base


def _build_run_input(req: SearchRequest) -> dict[str, Any]:
    """Input tương thích Actor kiểu Google Search Scraper (tuỳ chỉnh theo Apify)."""
    base = _google_actor_base(build_apify_queries(req))
    site = host_label(req.website or "")
    if site:
        base["site"] = site
        base["relatedToSite"] = site
    return base


def _fetch_apify_organic_rows_sync(
    queries: str,
    *,
    max_pages: int | None = None,
    results_per_page: int | None = None,
) -> list[dict]:
    token = (settings.apify_token or "").strip()
    if not token:
        return []
    try:
        from apify_client import ApifyClient
    except ImportError:
        return []

    actor_id = settings.apify_actor_id.strip() or "nFJndFXA5zjCTuudP"
    run_input = _google_actor_base(queries, max_pages=max_pages, results_per_page=results_per_page)
    cap = _apify_results_cap(results_per_page)
    rows: list[dict] = []
    try:
        client = ApifyClient(token)
        run = client.actor(actor_id).call(run_input=run_input, wait_secs=300)
        ds_id = run.get("defaultDatasetId")
        if not ds_id:
            return []
        for item in client.dataset(ds_id).iterate_items():
            if not isinstance(item, dict):
                continue
            for o in _organic_rows(item):
                rows.append(o)
                if len(rows) >= cap:
                    return rows
    except Exception as e:  # noqa: BLE001
        logger.warning("Apify Google actor: %s", e)
        if settings.debug:
            import traceback

            traceback.print_exc()
        raise search_error_from_exception(e) from e
    return rows


def run_google_actor_queries_sync(
    queries: str,
    *,
    max_pages: int | None = None,
    results_per_page: int | None = None,
) -> list[tuple[str, str]]:
    """
    Chạy Actor một lần với chuỗi queries (thường một dòng).
    Trả về các cặp (url, title) organic, tối đa apify_results_per_page.
    """
    out: list[tuple[str, str]] = []
    for o in _fetch_apify_organic_rows_sync(
        queries, max_pages=max_pages, results_per_page=results_per_page
    ):
        url, title = _organic_url_title(o)
        if url:
            out.append((url, title))
    return out


class ApifyGoogleSearchCollector(CouponCollector):
    """
    Chạy Apify Actor (mặc định Google Search / scraper do bạn cấu hình),
    đọc dataset, trích mã coupon từ text các item.
    Mặc định: 1 query, 1 trang, tối đa 5 organic (xem apify_results_per_page).
    """

    name = "apify_google_search"

    async def collect(self, req: SearchRequest) -> list[RawCoupon]:
        if not (settings.apify_token or "").strip():
            return []

        actor_id = settings.apify_actor_id.strip() or "nFJndFXA5zjCTuudP"
        queries = build_apify_queries(req)

        def _run_sync() -> list[RawCoupon]:
            out: list[RawCoupon] = []
            for o in _fetch_apify_organic_rows_sync(queries):
                title = str(o.get("title") or o.get("pageTitle") or o.get("htmlTitle") or "")
                desc = str(
                    o.get("description")
                    or o.get("snippet")
                    or o.get("parsedSnippet")
                    or o.get("text")
                    or ""
                )
                url, _ = _organic_url_title(o)
                if is_simplycodes_domain_url(url):
                    continue
                blob = f"{title}\n{desc}"
                for code in extract_candidate_codes(blob):
                    out.append(
                        RawCoupon(
                            code=code,
                            description=(title[:240] + (f" — {host_label(url)}" if url else ""))[:500] or None,
                            source=CouponSource.coupon_site,
                            source_url=url,
                            found_at=datetime.utcnow(),
                            metadata={"collector": self.name, "apify_actor": actor_id, "apify_query": queries},
                        )
                    )
            return out

        try:
            return await asyncio.to_thread(_run_sync)
        except SearchUserError:
            raise
        except Exception as e:  # noqa: BLE001
            if settings.debug:
                import traceback

                traceback.print_exc()
            raise search_error_from_exception(e) from e
