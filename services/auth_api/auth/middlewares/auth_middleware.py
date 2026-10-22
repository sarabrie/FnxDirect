import hashlib
import hmac
import secrets

from fastapi import Cookie, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from auth.config import get_settings
from auth.services.auth_service import verify_access_token

_ACCESS_COOKIE = "access_token"
_REFRESH_COOKIE = "refresh_token"
_CSRF_COOKIE = "csrf_token"
_CSRF_HEADER = "X-CSRF-Token"


# ─── Cookie helpers ──────────────────────────────────────────────────────────

def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    s = get_settings()
    csrf_token = secrets.token_urlsafe(32)
    _set(response, _ACCESS_COOKIE, access, max_age=s.ACCESS_TOKEN_TTL_SECONDS, path="/")
    _set(response, _REFRESH_COOKIE, refresh, max_age=s.REFRESH_TOKEN_TTL_DAYS * 86400, path="/auth/refresh")
    # CSRF token is readable by JS (no HttpOnly) so the client can send it back as a header
    response.set_cookie(
        _CSRF_COOKIE, csrf_token,
        max_age=s.REFRESH_TOKEN_TTL_DAYS * 86400,
        secure=s.COOKIE_SECURE, samesite="strict", httponly=False,
    )


def clear_auth_cookies(response: Response) -> None:
    for name, path in [(_ACCESS_COOKIE, "/"), (_REFRESH_COOKIE, "/auth/refresh"), (_CSRF_COOKIE, "/")]:
        response.delete_cookie(name, path=path)


def _set(response: Response, name: str, value: str, max_age: int, path: str) -> None:
    s = get_settings()
    response.set_cookie(
        name, value, max_age=max_age, path=path,
        httponly=True, secure=s.COOKIE_SECURE, samesite="strict",
    )


# ─── CSRF double-submit validation ───────────────────────────────────────────

def validate_csrf(request: Request) -> None:
    cookie_csrf = request.cookies.get(_CSRF_COOKIE)
    header_csrf = request.headers.get(_CSRF_HEADER)
    if not cookie_csrf or not header_csrf:
        raise HTTPException(status_code=403, detail="CSRF token missing.")
    if not hmac.compare_digest(cookie_csrf, header_csrf):
        raise HTTPException(status_code=403, detail="CSRF token mismatch.")


# ─── Auth extraction ─────────────────────────────────────────────────────────

def _extract_user(request: Request) -> dict | None:
    token = request.cookies.get(_ACCESS_COOKIE)
    if not token:
        return None
    try:
        return verify_access_token(token)
    except ValueError:
        return None


def require_auth(request: Request) -> dict:
    user = _extract_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def optional_auth(request: Request) -> dict | None:
    return _extract_user(request)


def get_refresh_token_from_cookie(request: Request) -> str | None:
    return request.cookies.get(_REFRESH_COOKIE)
