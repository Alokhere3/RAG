"""Unit tests for CSRF validation and auth cookie hardening (F-05 & F-07)."""

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api.v1.endpoints.auth import _clear_auth_cookie, _set_auth_cookie, verify_csrf_origin
from app.core.config import get_settings
from app.core.errors import AuthorizationError


def _make_request(headers: dict | None = None, cookies: dict | None = None) -> Request:
    header_list = []
    if headers:
        header_list = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/refresh",
        "headers": header_list,
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("localhost", 8000),
        "scheme": "http",
    }
    req = Request(scope)
    if cookies:
        req._cookies = cookies
    return req


def test_csrf_origin_allowed_with_exact_match(monkeypatch):
    """Origin matching allowed CORS origin succeeds."""
    settings = get_settings()
    monkeypatch.setattr(settings, "cors_origins", ["https://app.example.com"])

    req = _make_request(headers={"origin": "https://app.example.com"})
    # Should not raise
    verify_csrf_origin(req)


def test_csrf_origin_rejected_when_untrusted(monkeypatch):
    """Origin not matching allowed CORS origin is rejected."""
    settings = get_settings()
    monkeypatch.setattr(settings, "cors_origins", ["https://app.example.com"])

    req = _make_request(headers={"origin": "https://evil-attacker.com"})
    with pytest.raises(AuthorizationError) as exc_info:
        verify_csrf_origin(req)
    assert exc_info.value.code == "UNTRUSTED_ORIGIN"


def test_csrf_origin_falls_back_to_referer(monkeypatch):
    """When Origin is omitted, Referer header is parsed and validated."""
    settings = get_settings()
    monkeypatch.setattr(settings, "cors_origins", ["https://app.example.com"])

    req = _make_request(headers={"referer": "https://app.example.com/dashboard/chat"})
    # Should not raise
    verify_csrf_origin(req)

    bad_req = _make_request(headers={"referer": "https://malicious.org/page"})
    with pytest.raises(AuthorizationError) as exc_info:
        verify_csrf_origin(bad_req)
    assert exc_info.value.code == "UNTRUSTED_ORIGIN"


def test_csrf_production_missing_origin_with_cookie_raises(monkeypatch):
    """In production, cookie-authenticated requests require an Origin or Referer header."""
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "cors_origins", ["https://app.example.com"])

    req = _make_request(
        headers={},
        cookies={settings.auth_cookie_name: "test-token-value"},
    )
    with pytest.raises(AuthorizationError) as exc_info:
        verify_csrf_origin(req)
    assert exc_info.value.code == "CSRF_VALIDATION_FAILED"


def test_set_and_clear_auth_cookie_attributes(monkeypatch):
    """Ensure cookie attributes have httponly, samesite, path, and secure flags."""
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_cookie_secure", True)

    resp = Response()
    _set_auth_cookie(resp, "test-token-12345")

    set_cookie_header = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header or "httponly" in set_cookie_header.lower()
    assert "Secure" in set_cookie_header or "secure" in set_cookie_header.lower()
    assert "SameSite=lax" in set_cookie_header or "samesite=lax" in set_cookie_header.lower()
    assert "path=/api/v1/auth" in set_cookie_header.lower()

    # Clear cookie
    clear_resp = Response()
    _clear_auth_cookie(clear_resp)
    clear_cookie_header = clear_resp.headers.get("set-cookie", "")
    assert "httponly" in clear_cookie_header.lower()
    assert "secure" in clear_cookie_header.lower()
    assert "max-age=0" in clear_cookie_header.lower()
