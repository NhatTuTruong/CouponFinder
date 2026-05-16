from __future__ import annotations

import asyncio
import sys

import typer

from coupon_finder.config import settings
from coupon_finder.models import SearchRequest
from coupon_finder.pipeline import search

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def search_cmd(
    brand: str = typer.Option(None, "--brand"),
    website: str = typer.Option(None, "--website"),
    product: str = typer.Option(None, "--product"),
    category: str = typer.Option(None, "--category"),
    verify: bool = typer.Option(True, "--verify/--no-verify"),
    limit_verify: int = typer.Option(15, "--limit-verify"),
):
    """Tìm coupon theo pipeline; verify thật bằng Playwright (heuristic)."""
    req = SearchRequest(brand=brand, website=website, product=product, category=category)
    effective_verify = verify and settings.verify_enabled
    if verify and not settings.verify_enabled:
        typer.secho(
            "Verify is OFF in config (COUPON_FINDER_VERIFY_ENABLED=false); listing unverified codes.",
            fg=typer.colors.YELLOW,
        )
    report = asyncio.run(search(req, verify=verify, limit_verify=limit_verify))
    results = report.results

    def _print_table(title: str, rows: list, *, verified: bool) -> None:
        typer.echo(title)
        if verified:
            typer.echo("CODE\tDISCOUNT\tMO_TA\tSTATUS\tCONFIDENCE\tTYPE\tSOURCE")
            for r in rows:
                status = "WORKING" if r.is_working else "FAIL"
                disc = (r.discount_text or r.source_discount or "").strip()
                mo = ((r.source_item_description or "").replace("\t", " ").replace("\n", " "))[:72]
                typer.echo(
                    f"{r.code}\t{disc}\t{mo}\t{status}\t{r.confidence:.2f}\t{r.coupon_type}\t{r.source}"
                )
        else:
            typer.echo("CODE\tDISCOUNT\tMO_TA\tSOURCE\tURL\tDESCRIPTION")
            for r in rows:
                sdisc = ((r.source_discount or "").replace("\t", " ").replace("\n", " "))[:48]
                mo = ((r.source_item_description or "").replace("\t", " ").replace("\n", " "))[:72]
                desc = ((r.description or "").replace("\t", " ").replace("\n", " "))[:120]
                url = ((r.source_url or "").replace("\t", " "))[:80]
                typer.echo(f"{r.code}\t{sdisc}\t{mo}\t{r.source.value}\t{url}\t{desc}")

    if verify and report.collected_preview:
        n = report.normalized_count
        shown = len(report.collected_preview)
        _print_table(
            f"--- collected (normalized total={n}, showing first {shown}) ---",
            list(report.collected_preview),
            verified=False,
        )

    if not results:
        # ASCII-only: Windows consoles often use cp1252 and choke on Vietnamese.
        if not report.collected_preview:
            typer.secho("No coupons to show.", fg=typer.colors.YELLOW)
        elif effective_verify:
            typer.secho("No Playwright verify rows (see COLLECTED table above).", fg=typer.colors.YELLOW)
        if report.raw_count == 0:
            typer.echo(
                "No raw coupons collected. Do one of the following: "
                "(1) Add rows to data/community_coupons.json matching brand + website host. "
                "(2) Set COUPON_FINDER_APIFY_TOKEN and/or COUPON_FINDER_SERPAPI_KEY "
                "and/or COUPON_FINDER_GOOGLE_API_KEY + COUPON_FINDER_GOOGLE_CSE_ID in .env "
                "next to pyproject.toml. "
                "(3) If keys are set but still empty, check Apify billing / actor errors or API quotas."
            )
            if not (
                (settings.apify_token or "").strip()
                or (settings.serpapi_key or "").strip()
                or ((settings.google_api_key or "").strip() and (settings.google_cse_id or "").strip())
            ):
                typer.echo(
                    "Hint: external search is OFF (no Apify/SerpAPI/Google keys loaded from env)."
                )
        elif report.normalized_count == 0:
            typer.echo(
                "Some codes were collected but all were dropped after cleanup "
                "(duplicate/fake/too old). Check collectors output and community file."
            )
        typer.echo("Tip: `python -m coupon_finder.cli list-cmd --brand ... --all` reads SQLite; `--no-verify` returns more collected rows.")
        raise typer.Exit(code=0)

    if effective_verify:
        _print_table("--- after Playwright verify ---", results, verified=True)
    else:
        _print_table("--- collected (capped) ---", results, verified=False)


@app.command("list-cmd")
def list_cmd(
    brand: str = typer.Option(None, "--brand"),
    website: str = typer.Option(None, "--website"),
    only_working: bool = typer.Option(False, "--only-working/--all"),
    limit: int = typer.Option(80, "--limit"),
):
    """Print coupons stored in SQLite (data/coupons.db)."""
    from coupon_finder.storage import list_results

    rows = list_results(
        brand=brand,
        website=website,
        only_working=only_working,
        min_confidence=None,
        limit=limit,
    )
    if not rows:
        typer.echo("No rows in DB for this filter.")
        raise typer.Exit(0)
    typer.echo("CODE\tWORKING\tCONF\tDISCOUNT\tMO_TA\tSOURCE\tURL")
    for r in rows:
        u = (r.source_url or "")[:56]
        d = (r.discount_text or r.source_discount or "")[:32]
        mo = ((r.source_item_description or "").replace("\t", " ").replace("\n", " "))[:48]
        typer.echo(
            f"{r.code}\t{r.is_working}\t{r.confidence:.2f}\t{d}\t{mo}\t{r.source}\t{u}"
        )


@app.command()
def doctor():
    """Chẩn đoán: đường dẫn .env, key đã nạp (không in giá trị), số collector, thử collect Nike."""
    import os

    from coupon_finder.config import _DOTENV, _PROJECT_ROOT, settings
    from coupon_finder.models import SearchRequest
    from coupon_finder.pipeline import _default_collectors, collect_all

    typer.echo("=== coupon-finder doctor ===")
    typer.echo(f"project_root: {_PROJECT_ROOT}")
    typer.echo(f"dotenv_file: {_DOTENV} (exists={_DOTENV.is_file()})")
    typer.echo(f"cwd: {os.getcwd()}")
    typer.echo(f"apify_token_loaded: {bool((settings.apify_token or '').strip())}")
    typer.echo(f"serpapi_key_loaded: {bool((settings.serpapi_key or '').strip())}")
    typer.echo(
        "google_cse_loaded: "
        f"{bool((settings.google_api_key or '').strip() and (settings.google_cse_id or '').strip())}"
    )
    typer.echo(f"debug: {settings.debug}")
    cols = _default_collectors()
    typer.echo(f"collectors ({len(cols)}): {', '.join(type(c).__name__ for c in cols)}")
    req = SearchRequest(brand="Nike", website="https://www.nike.com", product="shoes")
    raw, _trace, _err = asyncio.run(collect_all(req))
    typer.echo(f"dry_run collect_all (Nike): raw_count={len(raw)}")
    if raw:
        sample = ", ".join(f"{r.code}@{r.source.value}" for r in raw[:12])
        typer.echo(f"sample: {sample}")


@app.command()
def api(host: str = "127.0.0.1", port: int = 8000):
    """Chạy FastAPI server."""
    import uvicorn

    uvicorn.run("coupon_finder.api:app", host=host, port=port, reload=False)


def _stop_running_coupon_finder_exe() -> None:
    """Đóng CouponFinder.exe đang chạy — tránh WinError 5 khi PyInstaller ghi đè dist/."""
    import subprocess

    if sys.platform != "win32":
        return
    try:
        r = subprocess.run(
            ["taskkill", "/IM", "CouponFinder.exe", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0:
            typer.echo("Đã đóng CouponFinder.exe đang chạy.")
    except OSError:
        pass


@app.command("build-exe")
def build_exe(
    clean: bool = typer.Option(True, "--clean/--no-clean", help="Xóa build/dist trước khi đóng gói"),
):
    """Đóng gói CouponFinder.exe (PyInstaller) — app desktop, không cần chạy lệnh api."""
    import shutil
    import subprocess
    from pathlib import Path

    _stop_running_coupon_finder_exe()

    root = Path(__file__).resolve().parents[1]
    spec = root / "CouponFinder.spec"
    if not spec.is_file():
        typer.secho(f"Không thấy {spec}", fg=typer.colors.RED)
        raise typer.Exit(1)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        typer.echo("Cài build-exe: pip install -e \".[build-exe]\"")
        raise typer.Exit(1) from None

    if clean:
        for name in ("build", "dist"):
            p = root / name
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        str(spec),
    ]
    typer.echo(" ".join(cmd))
    subprocess.check_call(cmd, cwd=str(root))
    exe = root / "dist" / "CouponFinder.exe"
    if exe.is_file():
        typer.secho(f"Xong: {exe}", fg=typer.colors.GREEN)
        typer.echo("Dat CouponFinder.exe va file .env cung thu muc, roi double-click de mo app.")
    else:
        typer.secho("Build xong nhưng không thấy dist/CouponFinder.exe", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()

