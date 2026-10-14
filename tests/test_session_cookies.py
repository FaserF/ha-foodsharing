"""Regression tests for the session cookie handling (issue: permanent 401 on beta)."""

from http.cookies import SimpleCookie
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from yarl import URL

from custom_components.foodsharing.const import CSRF_COOKIE, SESSION_COOKIE
from custom_components.foodsharing.coordinator import FoodsharingCoordinator


def _coordinator(session):
    with patch(
        "custom_components.foodsharing.coordinator.async_get_clientsession",
        return_value=session,
    ):
        return FoodsharingCoordinator(MagicMock(), "test@test.com", "pass")


@pytest.mark.asyncio
async def test_restored_cookies_are_not_host_only():
    """Persisted cookies must reach the beta host too.

    aiohttp keeps the host-only flag of an existing entry even when the server later
    sends the same cookie with Domain=.foodsharing.de, so restoring them host-only
    made every request to beta.foodsharing.de unauthenticated forever.
    """
    session = MagicMock()
    session.cookie_jar = aiohttp.CookieJar()
    coordinator = _coordinator(session)
    coordinator.base_url = "https://beta.foodsharing.de"

    coordinator._restore_cookies({SESSION_COOKIE: "abc", CSRF_COOKIE: "def"})

    assert sorted(session.cookie_jar.filter_cookies(URL("https://beta.foodsharing.de"))) == [
        CSRF_COOKIE,
        SESSION_COOKIE,
    ]
    assert sorted(session.cookie_jar.filter_cookies(URL("https://foodsharing.de"))) == [
        CSRF_COOKIE,
        SESSION_COOKIE,
    ]


@pytest.mark.asyncio
async def test_restore_ignores_legacy_cookie_names():
    """Session files from older versions carry cookies the backend no longer knows."""
    session = MagicMock()
    session.cookie_jar = aiohttp.CookieJar()
    coordinator = _coordinator(session)

    coordinator._restore_cookies({"PHPSESSID": "old", "XSRF-TOKEN": "old"})

    assert not list(session.cookie_jar)


@pytest.mark.asyncio
async def test_authenticated_headers_send_csrf_token():
    """Non-GET calls need X-CSRF-Token from the FS_CSRF_TOKEN cookie."""
    session = MagicMock()
    session.cookie_jar = aiohttp.CookieJar()
    sc = SimpleCookie()
    sc[CSRF_COOKIE] = "token123"
    sc[CSRF_COOKIE]["domain"] = ".foodsharing.de"
    session.cookie_jar.update_cookies(sc, URL("https://foodsharing.de"))
    coordinator = _coordinator(session)

    headers = coordinator.authenticated_headers

    assert headers["X-CSRF-Token"] == "token123"
    assert "XSRF-TOKEN" not in headers
    assert "X-XSRF-TOKEN" not in headers


@pytest.mark.asyncio
async def test_login_with_empty_body_resolves_user_id():
    """/api/login answers 200 with an empty body; the id comes from /api/users/current."""
    session = MagicMock()
    session.cookie_jar = aiohttp.CookieJar()
    coordinator = _coordinator(session)
    coordinator.async_save_session = AsyncMock()

    login_resp = AsyncMock()
    login_resp.status = 200
    login_resp.json.side_effect = aiohttp.ContentTypeError(MagicMock(), ())
    login_resp.text.return_value = ""
    session.post.return_value.__aenter__.return_value = login_resp

    unauthenticated = AsyncMock()
    unauthenticated.status = 401
    unauthenticated.text.return_value = '{"message":"Not logged in","code":401}'
    current = AsyncMock()
    current.status = 200
    current.json.return_value = {"id": 602086, "name": "Steffen"}
    # 3 session checks before login, then /login, then the id lookup after login
    session.get.return_value.__aenter__.side_effect = [
        unauthenticated,
        unauthenticated,
        unauthenticated,
        unauthenticated,
        current,
    ]

    with patch("asyncio.sleep", AsyncMock()):
        assert await coordinator.login() is True
    assert coordinator.user_id == "602086"
    coordinator.async_save_session.assert_awaited()
