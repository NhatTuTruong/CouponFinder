from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse


def parse_domain_input(raw: str) -> tuple[str, str | None]:
    """
    Chuan hoa domain / URL thanh website + brand goi y (tinh nhanh cho Apify / community).

    Vi du: nike.com, www.nike.com, https://shop.brand.com/path
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("Domain trong.")
    if "://" not in s:
        s = "https://" + s
    p = urlparse(s)
    host = (p.netloc or "").lower()
    if not host and p.path:
        host = p.path.strip("/").split("/")[0].lower()
    host = host.split("@")[-1].split(":")[0]
    if not host or "." not in host:
        raise ValueError("Domain khong hop le.")
    website = f"{p.scheme or 'https'}://{host}"
    bare = host.removeprefix("www.")
    brand = bare.split(".")[0].title() if bare else None
    return website, brand


_COUPON_LISTING_HOSTS = frozenset({"simplycodes.com", "tenereteam.com"})


def _url_host(url: str | None) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        return urlparse(raw).netloc.lower().split(":")[0].removeprefix("www.")
    except Exception:  # noqa: BLE001
        return None


def is_coupon_listing_site_url(url: str | None) -> bool:
    """Host trang liệt kê coupon (Simply Codes, TenereTeam, …)."""
    return is_simplycodes_domain_url(url) or is_tenereteam_domain_url(url)


def is_simplycodes_domain_url(url: str | None) -> bool:
    """Host simplycodes.com (mọi path). Dùng lọc pipeline và bỏ heuristic SERP trùng collector Playwright."""
    return _url_host(url) == "simplycodes.com"


def is_tenereteam_domain_url(url: str | None) -> bool:
    """Host tenereteam.com hoặc subdomain (vd. gaucho-ninja.tenereteam.com)."""
    host = _url_host(url)
    if not host:
        return False
    return host == "tenereteam.com" or host.endswith(".tenereteam.com")


def shop_host_from_simplycodes_store_url(url: str | None) -> str | None:
    """
    https://simplycodes.com/store/ramonalarue.com → ramonalarue.com
    (segment sau /store/ phải giống hostname: có dấu chấm).
    """
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        s = raw if "://" in raw else f"https://{raw}"
        p = urlparse(s)
        host = (p.netloc or "").lower().split(":")[0].removeprefix("www.")
        if host != "simplycodes.com":
            return None
        parts = [x for x in (p.path or "").split("/") if x]
        if len(parts) < 2 or parts[0].lower() != "store":
            return None
        slug = parts[1].strip().lower().rstrip(".")
        if not slug or "." not in slug:
            return None
        if "/" in slug or "?" in slug or slug.startswith("http"):
            return None
        return slug
    except Exception:  # noqa: BLE001
        return None


def infer_shop_website_from_coupon_source_urls(urls: Iterable[str | None]) -> str | None:
    """Lấy website https://{shop} từ URL store Simply Codes đầu tiên hợp lệ."""
    for u in urls:
        sh = shop_host_from_simplycodes_store_url(u)
        if sh:
            return f"https://{sh}"
    return None
