from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from coupon_finder.config import settings
from coupon_finder.models import CouponResult, SearchRequest
from coupon_finder.pipeline import search
from coupon_finder.storage import init_db, list_results
from coupon_finder.ui_api import router as ui_router, _require_license_searches

app = FastAPI(title="Coupon Finder", version="0.1.0")
app.include_router(ui_router)

def _resolve_web_dir() -> Path:
    pkg = Path(__file__).resolve().parent
    root = pkg.parent
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base = Path(meipass)
            candidates.extend(
                [
                    base / "coupon_finder" / "web_public",
                    base / "web_public",
                ]
            )
    candidates.extend([pkg / "web_public", root / "web" / "public"])
    for cand in candidates:
        if (cand / "index.html").is_file():
            return cand
    return pkg / "web_public"


_WEB_DIR = _resolve_web_dir()


@app.get("/", include_in_schema=False)
def serve_ui():
    idx = _WEB_DIR / "index.html"
    if idx.is_file():
        return FileResponse(idx)
    return RedirectResponse(url="/docs")


if _WEB_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.post("/search", response_model=list[CouponResult])
async def search_coupons(req: SearchRequest, verify: bool = True, limit_verify: int = 15) -> list[CouponResult]:
    _require_license_searches(1)
    report = await search(
        req,
        verify=verify and settings.verify_enabled,
        limit_verify=limit_verify,
    )
    return report.results


@app.get("/results")
def get_results(
    brand: str | None = None,
    website: str | None = None,
    product: str | None = None,
    category: str | None = None,
    only_working: bool = True,
    min_confidence: float | None = None,
    limit: int = 50,
):
    min_conf = min_confidence if min_confidence is not None else settings.min_confidence_to_show
    return list_results(
        brand=brand,
        website=website,
        product=product,
        category=category,
        only_working=only_working,
        min_confidence=min_conf,
        limit=limit,
    )

