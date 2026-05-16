from __future__ import annotations

from typing import Any

import requests

from coupon_finder.config import settings
from coupon_finder.machine_id import get_machine_id

_TIMEOUT = 12.0


class LicenseError(Exception):
    def __init__(self, message: str, *, code: str = "license", payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.payload = payload or {}


def _base_url() -> str:
    url = (settings.license_server_url or "").strip().rstrip("/")
    if not url:
        raise LicenseError(
            "Chưa cấu hình URL server license. Vào tab Cài đặt và nhập COUPON_FINDER_LICENSE_SERVER_URL.",
            code="license_server_missing",
        )
    return url


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    try:
        resp = requests.post(url, json=body, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise LicenseError(
            f"Không kết nối được server license ({settings.license_server_url}): {exc}",
            code="license_server_unreachable",
        ) from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise LicenseError("Phản hồi license server không hợp lệ.", code="license_bad_response") from exc

    if not isinstance(data, dict):
        raise LicenseError("Phản hồi license server không hợp lệ.", code="license_bad_response")

    if resp.status_code >= 400 or not data.get("ok"):
        raise LicenseError(
            str(data.get("message") or "License không hợp lệ."),
            code="license_denied",
            payload=data,
        )
    return data


def activate_license() -> dict[str, Any]:
    key = (settings.license_key or "").strip()
    if not key:
        raise LicenseError(
            "Chưa nhập mã license. Vào tab Cài đặt để nhập mã bản quyền.",
            code="license_key_missing",
        )
    return _post(
        "/api/v1/license/activate",
        {
            "license_key": key,
            "machine_id": get_machine_id(),
            "machine_label": platform_label(),
        },
    )


def license_status() -> dict[str, Any]:
    key = (settings.license_key or "").strip()
    if not key:
        return {
            "ok": False,
            "configured": False,
            "message": "Chưa nhập mã license.",
            "code": "license_key_missing",
        }
    if not (settings.license_server_url or "").strip():
        return {
            "ok": False,
            "configured": False,
            "message": "Chưa cấu hình URL server license.",
            "code": "license_server_missing",
        }
    try:
        data = _post(
            "/api/v1/license/status",
            {"license_key": key, "machine_id": get_machine_id()},
        )
        return {"ok": True, "configured": True, **data}
    except LicenseError as exc:
        return {
            "ok": False,
            "configured": True,
            "message": exc.message,
            "code": exc.code,
            **exc.payload,
        }


def consume_searches(count: int) -> dict[str, Any]:
    if count < 1:
        return {"ok": True, "consumed": 0}
    key = (settings.license_key or "").strip()
    if not key:
        raise LicenseError("Chưa nhập mã license.", code="license_key_missing")
    return _post(
        "/api/v1/license/consume",
        {
            "license_key": key,
            "machine_id": get_machine_id(),
            "count": count,
        },
    )


def platform_label() -> str:
    import platform

    return f"{platform.system()} {platform.node()}".strip()
