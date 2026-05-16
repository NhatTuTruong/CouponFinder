from __future__ import annotations

MSG_NOT_FOUND = "Không tìm thấy mã. Kiểm tra lại domain, URL shop hoặc tên brand."
MSG_APIFY_TOKEN = "Token chưa sẵn sàng hoặc đã hết hạn"
MSG_SYSTEM = "Có lỗi xảy ra, Vui lòng thử lại sau"


class SearchUserError(Exception):
    """Lỗi hiển thị cho người dùng (UI)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def not_found_error() -> SearchUserError:
    return SearchUserError("not_found", MSG_NOT_FOUND)


def apify_token_error() -> SearchUserError:
    return SearchUserError("apify_token", MSG_APIFY_TOKEN)


def system_error() -> SearchUserError:
    return SearchUserError("system", MSG_SYSTEM)


def is_apify_auth_failure(exc: BaseException) -> bool:
    try:
        from apify_client.errors import ApifyApiError

        if isinstance(exc, ApifyApiError):
            if getattr(exc, "status_code", None) in (401, 403):
                return True
            blob = " ".join(
                str(x or "")
                for x in (
                    getattr(exc, "message", None),
                    getattr(exc, "type", None),
                    exc,
                )
            ).lower()
            if any(
                k in blob
                for k in (
                    "unauthorized",
                    "authentication",
                    "invalid token",
                    "not authorized",
                    "expired",
                    "forbidden",
                    "api token",
                    "user not found",
                )
            ):
                return True
    except ImportError:
        pass
    s = str(exc).lower()
    return any(
        k in s
        for k in (
            "401",
            "403",
            "unauthorized",
            "authentication failed",
            "invalid token",
            "not authorized",
            "token is invalid",
            "token has expired",
        )
    )


def search_error_from_exception(exc: BaseException) -> SearchUserError:
    if isinstance(exc, SearchUserError):
        return exc
    if is_apify_auth_failure(exc):
        return apify_token_error()
    return system_error()
