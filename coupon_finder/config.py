from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Thư mục làm việc gốc: repo (pyproject.toml) hoặc thư mục chứa .exe khi đóng gói PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "pyproject.toml").is_file():
            return p
    return here.parents[1]


_PROJECT_ROOT = _find_project_root()
_DOTENV = _PROJECT_ROOT / ".env"

# Nạp .env trước Settings: ổn định hơn chỉ dùng env_file của pydantic (một số bản / cwd khác nhau).
if _DOTENV.is_file():
    load_dotenv(_DOTENV, encoding="utf-8")
else:
    load_dotenv(encoding="utf-8")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COUPON_FINDER_", extra="ignore")

    data_dir: str = "data"
    sqlite_path: str = "data/coupons.db"
    # Lịch sử tìm kiếm UI (JSON trên đĩa, không localStorage)
    ui_history_json: str = "data/ui_search_history.json"
    ui_history_max_sessions: int = 500
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # Playwright
    headless: bool = True
    # Dùng Chrome/Edge cài trên máy (vd: chrome, msedge) — đôi khi qua Cloudflare tốt hơn Chromium bundled
    playwright_channel: str | None = None
    verify_timeout_ms: int = 35_000
    # Verify coupon: mở URL sản phẩm cố định rồi thử «Add to cart» trước khi tìm ô mã (mỗi shop cần URL riêng)
    verify_seed_product_url: str | None = None
    # CSS nút thêm giỏ — để trống thì thử vài selector + nút theo chữ (Shopify/Woo/…)
    verify_seed_add_to_cart_css: str | None = None
    # Chờ sau khi bấm thêm giỏ (ms) rồi mới đi các trang cart/checkout
    verify_seed_wait_ms: int = 2000
    # Giai đoạn 1 Shopify: verify qua Cart Ajax API (/cart.js, add.js, /discount/…) trước Playwright
    verify_use_shopify_cart_api: bool = True
    verify_shopify_products_limit: int = 20
    # Ổn định verify Shopify (API): retry khi lỗi tạm; chờ giữa các bước; đọc cart.js 2 lần
    verify_shopify_retries: int = 3
    verify_shopify_settle_ms: int = 500
    # Playwright seed giỏ Shopify: thử tối đa bao nhiêu variant (add.js / cart/add) trước khi fallback collection
    verify_shopify_playwright_variant_attempts: int = 30
    # Playwright: chờ sau Apply; số lần đọc body để bỏ phiếu (giảm DOM đang render dở)
    verify_playwright_settle_ms: int = 900
    verify_playwright_body_polls: int = 3
    # Số verify chạy song song (1 = ít rate-limit / race trên cùng shop)
    verify_all_concurrency: int = 1
    # Bật verify mã trên shop (Playwright / Shopify API). Tắt mặc định; bật: COUPON_FINDER_VERIFY_ENABLED=true
    verify_enabled: bool = False

    # Scoring / freshness
    stale_days: int = 180
    min_confidence_to_show: float = 0.2

    # Tìm kiếm bên ngoài (tùy chọn — bật khi có ít nhất một key)
    serpapi_key: str | None = None
    google_api_key: str | None = None
    google_cse_id: str | None = None
    external_search_max_results: int = 10

    # Apify — Google Search Results / Actor tuỳ chỉnh (cần COUPON_FINDER_APIFY_TOKEN)
    apify_token: str | None = None
    apify_actor_id: str = "nFJndFXA5zjCTuudP"
    # Mỗi lần gọi Actor: 1 query, 1 trang Google, tối đa N organic (tiết kiệm Usage)
    apify_max_pages_per_query: int = 1
    apify_results_per_page: int = 5
    # True = nhiều dòng query (6+ lần search / run — tốn credit); False = gộp 1 câu
    apify_multi_query: bool = False
    apify_country_code: str = "us"
    apify_search_language: str = "en"
    apify_language_code: str = "en"
    # Mặc định tắt các mode AI (thường tốn credit); bật bằng env nếu Actor hỗ trợ và bạn cần
    apify_enable_ai_mode: bool = False
    apify_enable_perplexity: bool = False
    apify_enable_chatgpt: bool = False
    apify_enable_copilot: bool = False
    apify_focus_on_paid_ads: bool = False
    # Thêm truy vấn site:domain cho từng domain (phân tách bằng dấu phẩy)
    apify_coupon_site_domains: str = "retailmenot.com,coupons.com,offers.com"
    # JSON object merge đè lên run_input (Actor schema khác nhau — tuỳ chỉnh tại đây)
    apify_run_input_extra_json: str | None = None

    # In traceback khi collector Apify lỗi (không in token)
    debug: bool = False

    # True: sau thu thập, chỉ giữ mã có source_url thuộc domain simplycodes.com (bỏ voucher.discount, SerpAPI khác domain, …)
    filter_raw_to_simplycodes_domain: bool = True

    # True: chỉ chạy Simply Codes (Apify + simplycodes.com), không SerpAPI / Google CSE / community / Apify Google rộng
    only_simplycodes: bool = False

    # License server (Laravel) — bắt buộc để dùng tool
    license_server_url: str | None = None
    license_key: str | None = None


settings = Settings()


def project_root() -> Path:
    return _PROJECT_ROOT

