"""Điểm vào bản .exe: server nội bộ + cửa sổ app (pywebview) hoặc trình duyệt."""
from __future__ import annotations

import multiprocessing
import os
import socket
import sys
import time
import traceback
import webbrowser
from datetime import datetime
from threading import Thread
from pathlib import Path

_BIND_HOST = "127.0.0.1"
_server_error: list[str] = []


def _frozen_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _startup_log_path() -> Path:
    return _frozen_root() / "data" / "coupon_finder_startup.log"


def _log(msg: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}\n"
    try:
        path = _startup_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _chdir_app_root() -> None:
    root = _frozen_root()
    os.chdir(root)
    _log(f"cwd={root}")


def _ensure_stdio() -> None:
    """PyInstaller windowed (.exe không console): stdout/stderr = None → uvicorn logging lỗi."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_path = _startup_log_path().parent / "coupon_finder_console.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stream = log_path.open("a", encoding="utf-8")
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def _pick_port(host: str, preferred: int) -> int:
    probe = _BIND_HOST if host in ("0.0.0.0", "::", "") else host
    for port in range(preferred, preferred + 30):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((probe, port))
            return port
        except OSError:
            continue
    return preferred


def _wait_server(url: str, server: Thread, timeout: float = 90.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_error:
            return False
        if not server.is_alive():
            return False
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)
    return False


def _run_uvicorn(port: int) -> None:
    try:
        _log(f"uvicorn import… port={port}")
        import uvicorn

        from coupon_finder.api import app

        _log("uvicorn run…")
        uvicorn.run(
            app,
            host=_BIND_HOST,
            port=port,
            log_level="warning",
            reload=False,
            access_log=False,
        )
    except Exception:
        err = traceback.format_exc()
        _server_error.append(err)
        _log(err)


def _chrome_edge_app_paths() -> list[Path]:
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pfx86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    return [
        Path(pf) / "Google/Chrome/Application/chrome.exe",
        Path(pfx86) / "Google/Chrome/Application/chrome.exe",
        Path(pf) / "Microsoft/Edge/Application/msedge.exe",
        Path(pfx86) / "Microsoft/Edge/Application/msedge.exe",
    ]


def _open_app_window(url: str) -> bool:
    """Chrome/Edge --app= cửa sổ không thanh tab (giống desktop app)."""
    import subprocess

    args = [
        f"--app={url}",
        "--new-window",
        "--disable-features=TranslateUI",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    for exe in _chrome_edge_app_paths():
        if exe.is_file():
            subprocess.Popen([str(exe), *args], close_fds=True)  # noqa: S603
            return True
    try:
        import webview

        webview.create_window("Coupon Finder", url, width=1180, height=820, min_size=(900, 600))
        webview.start()
        return True
    except ImportError:
        pass
    webbrowser.open(url)
    return False


def _fatal_message(msg: str) -> None:
    _log(f"FATAL: {msg[:500]}")
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "Coupon Finder", 0x10)
    except Exception:  # noqa: BLE001
        print(msg, file=sys.stderr)


def _startup_failure_message(url: str, server: Thread) -> str:
    log_hint = f"\n\nChi tiết: {_startup_log_path()}"
    if _server_error:
        detail = _server_error[0].strip()
        if len(detail) > 1800:
            detail = detail[:1800] + "\n…"
        return f"Server lỗi khi khởi động:\n\n{detail}{log_hint}"
    if not server.is_alive():
        return (
            f"Server dừng sớm (không lắng nghe tại {url}).\n"
            f"Kiểm tra cổng bị chiếm hoặc file .env cạnh file .exe.{log_hint}"
        )
    return (
        f"Không khởi động được server tại {url} (hết thời gian chờ).\n"
        f"Kiểm tra cổng bị chiếm hoặc chạy lại với quyền Administrator.{log_hint}"
    )


def main() -> None:
    multiprocessing.freeze_support()
    _chdir_app_root()
    _ensure_stdio()

    preferred = int(os.environ.get("COUPON_FINDER_PORT", "8765"))
    port = _pick_port(_BIND_HOST, preferred)
    url = f"http://{_BIND_HOST}:{port}/"
    _log(f"start preferred={preferred} port={port} frozen={getattr(sys, 'frozen', False)}")

    server = Thread(target=_run_uvicorn, args=(port,), daemon=True)
    server.start()

    if not _wait_server(url, server):
        _fatal_message(_startup_failure_message(url, server))
        raise SystemExit(1)

    _log(f"server ok {url}")
    used_app_mode = _open_app_window(url)
    if not used_app_mode:
        try:
            while server.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    else:
        try:
            while server.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        _log(traceback.format_exc())
        _fatal_message(f"Lỗi khởi động:\n{exc}\n\nChi tiết: {_startup_log_path()}")
        raise SystemExit(1) from exc
