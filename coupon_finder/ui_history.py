from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from coupon_finder.config import project_root, settings

_lock = asyncio.Lock()


def history_file_path() -> Path:
    raw = (settings.ui_history_json or "data/ui_search_history.json").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = project_root() / p
    return p


def _read_sessions_sync() -> list[dict[str, Any]]:
    path = history_file_path()
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get("sessions"), list):
        return [x for x in data["sessions"] if isinstance(x, dict)]
    return []


def _write_sessions_sync(sessions: list[dict[str, Any]]) -> None:
    path = history_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    max_n = max(1, int(settings.ui_history_max_sessions))
    trimmed = sessions[:max_n]
    payload = {"version": 1, "sessions": trimmed}
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


async def load_ui_history_sessions() -> list[dict[str, Any]]:
    async with _lock:
        return await asyncio.to_thread(_read_sessions_sync)


async def save_ui_history_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    async with _lock:
        max_n = max(1, int(settings.ui_history_max_sessions))
        trimmed = [s for s in sessions if isinstance(s, dict)][:max_n]
        await asyncio.to_thread(_write_sessions_sync, trimmed)
        return trimmed


async def append_ui_history_session(session: dict[str, Any]) -> list[dict[str, Any]]:
    async with _lock:
        sessions = await asyncio.to_thread(_read_sessions_sync)
        sid = str(session.get("id") or "").strip()
        if sid:
            sessions = [s for s in sessions if str(s.get("id") or "") != sid]
        sessions.insert(0, session)
        max_n = max(1, int(settings.ui_history_max_sessions))
        trimmed = sessions[:max_n]
        await asyncio.to_thread(_write_sessions_sync, trimmed)
        return trimmed


async def merge_ui_history_sessions(incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    async with _lock:
        existing = await asyncio.to_thread(_read_sessions_sync)
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for s in incoming + existing:
            if not isinstance(s, dict):
                continue
            sid = str(s.get("id") or "").strip()
            if sid:
                if sid in seen:
                    continue
                seen.add(sid)
            merged.append(s)
        max_n = max(1, int(settings.ui_history_max_sessions))
        trimmed = merged[:max_n]
        await asyncio.to_thread(_write_sessions_sync, trimmed)
        return trimmed
