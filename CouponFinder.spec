# PyInstaller spec — chạy: pyinstaller CouponFinder.spec
# Hoặc: python -m coupon_finder.cli build-exe

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = Path(SPECPATH)

_coupon_finder_hidden = collect_submodules("coupon_finder")
_extra_hidden = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "starlette.routing",
    "starlette.responses",
    "pydantic",
    "pydantic_settings",
    "pydantic_core",
    "sqlmodel",
    "sqlalchemy",
    "sqlalchemy.dialects.sqlite",
    "apify_client",
    "playwright",
    "playwright.async_api",
    "playwright._impl",
    "requests",
    "urllib3",
    "certifi",
    "bs4",
    "dateutil",
    "dateutil.parser",
    "rapidfuzz",
    "anyio",
    "sniffio",
    "h11",
    "httptools",
    "websockets",
    "email_validator",
    "multipart",
]

a = Analysis(
    [str(root / "coupon_finder" / "frozen_launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "coupon_finder" / "web_public"), "coupon_finder/web_public"),
        (str(root / ".env.example"), "."),
    ],
    hiddenimports=_coupon_finder_hidden + _extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CouponFinder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
