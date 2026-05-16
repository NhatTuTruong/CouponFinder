from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Callable, Optional

ProgressFn = Callable[[int, str], None]

_progress_cb: ContextVar[Optional[ProgressFn]] = ContextVar("search_progress_cb", default=None)


def bind_progress(callback: Optional[ProgressFn]) -> Token:
    return _progress_cb.set(callback)


def reset_progress(token: Token) -> None:
    _progress_cb.reset(token)


def report_progress(percent: int, message: str) -> None:
    cb = _progress_cb.get()
    if cb is None:
        return
    pct = max(0, min(100, int(percent)))
    cb(pct, (message or "").strip())
