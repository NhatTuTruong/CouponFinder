from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal

from dotenv import load_dotenv

from coupon_finder.config import Settings, _DOTENV, settings

ENV_PREFIX = "COUPON_FINDER_"

FieldType = Literal["bool", "int", "float", "text", "secret", "textarea"]


@dataclass(frozen=True)
class EnvFieldSpec:
    key: str
    label: str
    group: str
    field_type: FieldType
    description: str = ""


# Các biến COUPON_FINDER_* chỉnh được từ tab Cài đặt (khớp Settings).
UI_ENV_FIELDS: tuple[EnvFieldSpec, ...] = (
    EnvFieldSpec(
        "license_server_url",
        "URL server license",
        "Bản quyền",
        "text",
        "",
    ),
    EnvFieldSpec(
        "license_key",
        "Mã license",
        "Bản quyền",
        "secret",
        "Bắt buộc. Để trống khi lưu = giữ mã hiện tại.",
    ),
    EnvFieldSpec(
        "apify_token",
        "Apify token",
        "Apify & tìm kiếm",
        "secret",
        "Token chính. Để trống khi lưu = giữ token hiện tại.",
    ),
    EnvFieldSpec(
        "apify_token_backup",
        "Apify token (dự phòng)",
        "Apify & tìm kiếm",
        "secret",
        "Tự dùng khi token chính lỗi hoặc hết quota. Để trống khi lưu = giữ giá trị hiện tại.",
    ),
    EnvFieldSpec(
        "only_simplycodes",
        "Chỉ Simply Codes",
        "Apify & tìm kiếm",
        "bool",
        "true: chỉ Apify + Simply Codes / TenereTeam, không SerpAPI / Google CSE.",
    ),
    EnvFieldSpec(
        "apify_results_per_page",
        "Số kết quả organic / lần",
        "Apify & tìm kiếm",
        "int",
        "Mặc định 5 — tiết kiệm credit Apify.",
    ),
    EnvFieldSpec(
        "apify_multi_query",
        "Nhiều query Apify",
        "Apify & tìm kiếm",
        "bool",
        "true: nhiều câu query (tốn credit hơn).",
    ),
    EnvFieldSpec(
        "filter_raw_to_simplycodes_domain",
        "Lọc chỉ trang coupon",
        "Apify & tìm kiếm",
        "bool",
        "Chỉ giữ mã từ simplycodes.com / tenereteam.com.",
    ),
    EnvFieldSpec(
        "headless",
        "Headless (ẩn trình duyệt)",
        "Playwright",
        "bool",
        "false + Chrome thường qua Cloudflare tốt hơn khi scrape.",
    ),
    EnvFieldSpec(
        "playwright_channel",
        "Playwright channel",
        "Playwright",
        "text",
        "Ví dụ: chrome, msedge — để trống = Chromium bundled.",
    ),
    EnvFieldSpec(
        "ui_history_json",
        "File lịch sử JSON",
        "Lịch sử",
        "text",
        "Đường dẫn file lưu lịch sử tìm kiếm.",
    ),
    EnvFieldSpec(
        "ui_history_max_sessions",
        "Số bản ghi lịch sử tối đa",
        "Lịch sử",
        "int",
        "",
    ),
    EnvFieldSpec(
        "debug",
        "Debug",
        "Nâng cao",
        "bool",
        "In traceback khi collector lỗi.",
    ),
)

_UI_KEYS = {f.key for f in UI_ENV_FIELDS}


def env_file_path() -> str:
    return str(_DOTENV)


def _env_line_key(line: str) -> str | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.lower().startswith("export "):
        s = s[7:].strip()
    if "=" not in s:
        return None
    k, _ = s.split("=", 1)
    k = k.strip()
    if not k.startswith(ENV_PREFIX):
        return None
    return k[len(ENV_PREFIX) :].lower()


def read_env_file_dict() -> dict[str, str]:
    out: dict[str, str] = {}
    path = _DOTENV
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            key = _env_line_key(line)
            if not key:
                continue
            raw = line.strip()
            if raw.lower().startswith("export "):
                raw = raw[7:].strip()
            _, val = raw.split("=", 1)
            out[key] = val.strip().strip('"').strip("'")
    return out


def _format_env_value(value: Any, field_type: FieldType) -> str:
    if field_type == "bool":
        return "true" if _coerce_bool(value) else "false"
    if field_type == "int":
        return str(int(value))
    if field_type == "float":
        return str(float(value))
    s = str(value or "").strip()
    if re.search(r"[\s#\"']", s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value or "").strip().lower()
    return s in ("1", "true", "yes", "on")


def write_env_updates(updates: dict[str, str]) -> None:
    """Ghi các key COUPON_FINDER_* vào .env; giữ comment và key không thuộc UI."""
    path = _DOTENV
    lines: list[str] = []
    seen: set[str] = set()
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            lines = f.readlines()

    new_lines: list[str] = []
    for line in lines:
        key = _env_line_key(line)
        if key and key in updates:
            new_lines.append(f"{ENV_PREFIX}{key.upper()}={updates[key]}\n")  # pydantic: COUPON_FINDER_{FIELD}
            seen.add(key)
        else:
            new_lines.append(line if line.endswith("\n") else line + "\n")

    missing = [k for k in updates if k not in seen]
    if missing:
        if new_lines and not new_lines[-1].endswith("\n\n"):
            if new_lines[-1].strip():
                new_lines.append("\n")
        new_lines.append("# Cap nhat tu tab Cai dat (Coupon Finder)\n")
        for key in sorted(missing):
            new_lines.append(f"{ENV_PREFIX}{key.upper()}={updates[key]}\n")  # pydantic: COUPON_FINDER_{FIELD}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.writelines(new_lines)


def reload_runtime_settings() -> None:
    load_dotenv(_DOTENV, override=True)
    fresh = Settings()
    for name in Settings.model_fields:
        object.__setattr__(settings, name, getattr(fresh, name))


def _settings_value(key: str) -> Any:
    return getattr(settings, key, None)


def _display_value(spec: EnvFieldSpec, raw: Any) -> tuple[str, bool]:
    """value for form, has_secret_value."""
    if spec.field_type == "secret":
        has = bool(str(raw or "").strip())
        return ("", has)
    if spec.field_type == "bool":
        return ("true" if _coerce_bool(raw) else "false", bool(raw))
    if raw is None:
        return ("", False)
    return (str(raw), bool(str(raw).strip()))


def get_env_settings_payload() -> dict[str, Any]:
    file_vals = read_env_file_dict()
    fields_out: list[dict[str, Any]] = []
    groups_order: list[str] = []
    for spec in UI_ENV_FIELDS:
        if spec.group not in groups_order:
            groups_order.append(spec.group)
        raw = file_vals.get(spec.key)
        if raw is None:
            raw = _settings_value(spec.key)
        disp, has_val = _display_value(spec, raw)
        entry: dict[str, Any] = {
            "key": spec.key,
            "label": spec.label,
            "group": spec.group,
            "type": spec.field_type,
            "description": spec.description,
            "value": disp,
        }
        if spec.field_type == "secret":
            entry["has_value"] = has_val
            entry["masked"] = "••••••••" if has_val else ""
        fields_out.append(entry)
    return {
        "env_path": env_file_path(),
        "groups": groups_order,
        "fields": fields_out,
    }


def apply_env_settings_from_ui(values: dict[str, Any]) -> dict[str, Any]:
    file_vals = read_env_file_dict()
    updates: dict[str, str] = {}

    for spec in UI_ENV_FIELDS:
        if spec.key not in values and spec.key not in _UI_KEYS:
            continue
        if spec.key not in values:
            continue
        incoming = values[spec.key]

        if spec.field_type == "secret":
            s = str(incoming or "").strip()
            if not s:
                cur = file_vals.get(spec.key) or _settings_value(spec.key)
                if cur:
                    updates[spec.key] = _format_env_value(cur, "text")
                continue
            updates[spec.key] = _format_env_value(s, "text")
            continue

        if spec.field_type == "bool":
            updates[spec.key] = _format_env_value(incoming, "bool")
        elif spec.field_type == "int":
            updates[spec.key] = _format_env_value(int(incoming or 0), "int")
        elif spec.field_type == "float":
            updates[spec.key] = _format_env_value(float(incoming or 0), "float")
        else:
            updates[spec.key] = _format_env_value(incoming, "text")

    if updates:
        write_env_updates(updates)
        reload_runtime_settings()

    return get_env_settings_payload()
