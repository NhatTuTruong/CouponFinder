from __future__ import annotations

import hashlib
import platform
import uuid
from pathlib import Path

from coupon_finder.config import project_root

_CACHE_FILE = "data/machine_id.txt"


def get_machine_id() -> str:
    """ID ổn định theo máy — dùng khi kích hoạt license."""
    root = project_root()
    cache = root / _CACHE_FILE
    if cache.is_file():
        cached = cache.read_text(encoding="utf-8").strip()
        if cached:
            return cached

    parts = [
        platform.node() or "unknown-host",
        platform.system(),
        platform.machine(),
        str(uuid.getnode()),
    ]
    machine_id = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:32]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(machine_id, encoding="utf-8")
    return machine_id
