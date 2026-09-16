import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any

import aiohttp
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from yarl import URL

from .const import (
    CONF_DOMAIN,
    CONF_KEYWORDS,
    CONF_SCAN_INTERVAL,
    CONF_USE_BETA_API,
    CSRF_COOKIE,
    DOMAIN,
    SESSION_COOKIE,
)
from .helpers import get_locations_from_entry, haversine_km, mask_email

_LOGGER = logging.getLogger(__name__)

# Upper bound for per-update Fairteiler detail lookups.
MAX_FAIRTEILER_DETAILS = 25


class AuthenticationFailed(UpdateFailed):
    """Exception to indicate authentication failure."""


class FoodsharingCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """Class to manage fetching Foodsharing data for a single account."""

    def __init__(self, hass: HomeAssistant, email: str, password: str) -> None:
        """Initialize."""
        self.email = email
        self.password = password
        self.hass = hass
        self.session = async_get_clientsession(hass)
        self.entries: dict[str, config_entries.ConfigEntry] = {}

        self._seen_messages: set[int] = set()
        self._seen_bells: set[int] = set()
        self._seen_fairteiler_posts: set[int] = set()
        self._marker_cache: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
        self._seen_baskets: set[int] = set()
        self._is_first_update = True
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        self.user_id: str | None = None
        self.region_id: int | None = None
        self.stats: dict[str, Any] = {}
        self._last_stats_update: datetime | None = None
        self._cached_stats: dict[str, Any] = {}
        self._xsrf_token: str | None = None
        self.base_url = "https://foodsharing.de"
        self._update_base_url()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{email}",
            update_interval=timedelta(minutes=2),
        )
        self._session_file = hass.config.path(
            ".storage",
            f"foodsharing_session_{email.replace('@', '_').replace('.', '_')}.json",
        )

    def _get_csrf_token_from_jar(self) -> str | None:
        """Extract the CSRF token from the cookie jar (backend cookie: FS_CSRF_TOKEN)."""
        for cookie in self.session.cookie_jar:
            if cookie.key == CSRF_COOKIE:
                return str(cookie.value)
        return None

    @property
    def authenticated_headers(self) -> dict[str, str]:
        """Return headers for authenticated requests mimicking a browser."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": self._user_agent,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/",
            "Origin": self.base_url,
        }
        token = self._get_csrf_token_from_jar()
        if token:
            # Backend requires this header on every non-GET request while logged in
            # (src/EventSubscriber/CsrfEventSubscriber.php).
            headers["X-CSRF-Token"] = token
        return headers

    async def async_load_session(self) -> None:
        """Load session cookies and metadata from file."""

        def load():
            if not os.path.exists(self._session_file):
                return None
            try:
                with open(self._session_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                _LOGGER.warning("Could not load session file %s: %s", self._session_file, e)
                return None

        data = await self.hass.async_add_executor_job(load)
        if not data:
            return

        try:
            if isinstance(data, dict):
                cookies_data = data.get("cookies", {})
                self.user_id = data.get("user_id")
                self._xsrf_token = data.get("xsrf_token")

                if cookies_data:
                    self._restore_cookies(cookies_data)
                _LOGGER.debug(
                    "Loaded persisted session for %s (User ID: %s)",
                    self.email,
                    self.user_id,
                )
        except Exception as e:
            _LOGGER.warning("Error processing loaded session: %s", e)

    async def async_save_session(self) -> None:
        """Save session cookies and metadata to file."""
        try:
            cookies = {}
            for cookie in self.session.cookie_jar:
                # We only save cookies relevant for Foodsharing
                domain = str(cookie.get("domain", "")).lower()
                if "foodsharing" in domain:
                    cookies[cookie.key] = cookie.value

            if not cookies:
                # Fallback: if we didn't find them by domain, just save what we have
                for cookie in self.session.cookie_jar:
                    cookies[cookie.key] = cookie.value

            data = {
                "cookies": cookies,
                "user_id": self.user_id,
                "xsrf_token": self._xsrf_token,
                "updated_at": datetime.now(UTC).isoformat(),
            }

            def save():
                with open(self._session_file, "w", encoding="utf-8") as f:
                    json.dump(data, f)

            await self.hass.async_add_executor_job(save)
            _LOGGER.debug("Saved session for %s", self.email)
        except Exception as e:
            _LOGGER.warning("Could not save session file: %s", e)

    def _cookie_domain(self) -> str:
        """Return the cookie domain the backend uses (e.g. '.foodsharing.de').

        The session cookies are set with Domain=.foodsharing.de, so they are valid
        for the beta host as well. Restoring them host-only would make aiohttp keep
        the host-only flag forever and never send them to beta.foodsharing.de.
        """
        host = URL(self.base_url).host or "foodsharing.de"
        return "." + host.removeprefix("beta.").removeprefix("www.")

    def _restore_cookies(self, cookies_data: dict[str, str]) -> None:
        """Put persisted cookies back into the jar with the backend's domain.

        Only the current cookie names are restored; session files written by older
        versions (PHPSESSID/XSRF-TOKEN) are ignored instead of migrated.
        """
        jar_cookies: SimpleCookie = SimpleCookie()
        domain = self._cookie_domain()
        for key, value in cookies_data.items():
            if key not in (SESSION_COOKIE, CSRF_COOKIE):
                continue
            jar_cookies[key] = value
            jar_cookies[key]["domain"] = domain
            jar_cookies[key]["path"] = "/"
        if not jar_cookies:
            _LOGGER.debug("No usable cookies in persisted session, a fresh login is required")
            return
        self.session.cookie_jar.update_cookies(jar_cookies, URL(self.base_url))

    async def fetch_csrf(self):
        """Fetch the CSRF token from the login page."""
        try:
            # Hit /login to ensure we get the right cookies
            async with self.session.get(f"{self.base_url}/login", headers={"User-Agent": self._user_agent}) as response:
                await response.text()
                token = self._get_csrf_token_from_jar()
                if token:
                    self._xsrf_token = token
                    _LOGGER.debug("Fetched CSRF token from %s cookie", CSRF_COOKIE)
                else:
                    _LOGGER.debug("No %s cookie found on /login", CSRF_COOKIE)
        except Exception as e:
            _LOGGER.error("Failed to fetch CSRF token: %s", e)

    def add_entry(self, entry: config_entries.ConfigEntry) -> None:
        """Add a config entry to this coordinator."""
        self.entries[entry.entry_id] = entry
        self._update_refresh_interval()
        self._update_base_url()

    def remove_entry(self, entry_id: str) -> None:
        """Remove a config entry from this coordinator."""
        self.entries.pop(entry_id, None)
        self._update_refresh_interval()
        self._update_base_url()

    def _update_base_url(self) -> None:
        """Update base URL based on entries."""
        use_beta = False
        domain = "foodsharing_de"
        for entry in self.entries.values():
            if entry.options.get(CONF_USE_BETA_API, entry.data.get(CONF_USE_BETA_API, False)):
                use_beta = True

            # Get domain from entry, default to de
            entry_domain = entry.options.get(CONF_DOMAIN, entry.data.get(CONF_DOMAIN, "foodsharing_de"))
            if entry_domain != "foodsharing_de":
                domain = entry_domain

        base_domain = "foodsharing.de"
        if domain == "foodsharing_at":
            base_domain = "foodsharing.at"
        elif domain == "foodsharing_ch":
            base_domain = "foodsharing.ch"

        self.base_url = f"https://beta.{base_domain}" if use_beta else f"https://{base_domain}"
        _LOGGER.debug("Foodsharing base URL set to %s", self.base_url)

    def _update_refresh_interval(self) -> None:
        """Update the update interval based on entries."""
        if not self.entries:
            return

        min_interval = 60
        for entry in self.entries.values():
            interval = entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, 2))
            min_interval = min(min_interval, interval)

        self.update_interval = timedelta(minutes=min_interval)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            return await self._fetch_all_data()
        except AuthenticationFailed as err:
            _LOGGER.warning("AuthenticationFailed: %s, attempting re-login.", err)
            login_res = await self.login()
            if login_res is True:
                async_delete_issue(self.hass, DOMAIN, f"auth_failed_{self.email}")
                return await self._fetch_all_data()
            if login_res == "2fa_required":
                _LOGGER.info(
                    "2FA required for %s, starting re-auth flow.",
                    mask_email(self.email),
                )
                raise ConfigEntryAuthFailed("2FA required for Foodsharing account") from err

            async_create_issue(
                self.hass,
                DOMAIN,
                f"auth_failed_{self.email}",
                is_fixable=False,
                severity=IssueSeverity.ERROR,
                translation_key="auth_failed",
                translation_placeholders={"email": self.email},
            )
            raise ConfigEntryAuthFailed("Authentication failed during retry.") from err
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Unexpected error communicating with API: {err}") from err

    async def _fetch_all_data(self) -> dict[str, Any]:
        """Fetch all data for all locations."""
        now = datetime.now()
        fetch_stats = (
            self._last_stats_update is None
            or (now - self._last_stats_update) > timedelta(days=1)
            or self._is_first_update
        )

        task_keys = [
            "messages",
            "bells",
            "pickups",
            "own_baskets",
        ]
        account_tasks = [
            self.fetch_unread_messages(),
            self.fetch_bells(),
            self.fetch_pickups(),
            self.fetch_own_baskets(),
        ]

        if fetch_stats:
            stats_keys = ["global_stats", "user_stats", "profile", "bananas", "buddies"]
            task_keys.extend(stats_keys)
            account_tasks.extend(
                [
                    self.fetch_global_statistics(),
                    self.fetch_user_statistics(),
                    self.fetch_user_profile(),
                    self.fetch_bananas(),
                    self.fetch_buddies(),
                ]
            )

        account_results = await asyncio.gather(
            *account_tasks,
            return_exceptions=True,
        )

        keyed_results = dict(zip(task_keys, account_results, strict=True))

        # Update cache or use cached stats
        if fetch_stats:
            self._last_stats_update = now
            for key in ["global_stats", "user_stats", "profile", "bananas", "buddies"]:
                self._cached_stats[key] = keyed_results.get(key, {})
        else:
            for key, val in self._cached_stats.items():
                keyed_results[key] = val

        profile = keyed_results.get("profile", {})
        if isinstance(profile, dict):
            self.region_id = profile.get("regionId")

        if self.region_id:
            if fetch_stats:
                r_stats = await self.fetch_region_statistics(self.region_id)
                self._cached_stats["region_stats"] = r_stats
                keyed_results["region_stats"] = r_stats
            else:
                keyed_results["region_stats"] = self._cached_stats.get("region_stats", {})
        else:
            keyed_results["region_stats"] = {}

        for res in account_results:
            if isinstance(res, AuthenticationFailed):
                raise res

        (
            messages,
            bells,
            pickups,
            own_baskets,
            g_stats,
            u_stats,
            prof,
            bananas,
            buddies,
            r_stats,
        ) = self._normalize_account_results(keyed_results)

        location_data: dict[str, list[dict[str, Any]]] = {}
        task_meta: list[tuple[str, int]] = []
        location_tasks: list[Any] = []

        for entry_id, entry in self.entries.items():
            locs = get_locations_from_entry(entry)
            location_data[entry_id] = [{"baskets": [], "fairteiler": []} for _ in locs]
            for idx, loc in enumerate(locs):
                task_meta.append((entry_id, idx))
                location_tasks.append(
                    self.fetch_location_data(
                        entry_id,
                        loc["latitude"],
                        loc["longitude"],
                        loc.get("distance", 7),
                    )
                )

        location_results = await asyncio.gather(*location_tasks, return_exceptions=True)
        for (entry_id, idx), res in zip(task_meta, location_results, strict=True):
            if isinstance(res, AuthenticationFailed):
                raise res
            if isinstance(res, dict):
                location_data[entry_id][idx] = res
            elif isinstance(res, Exception):
                _LOGGER.error(
                    "Error fetching location data for entry %s location %d: %s",
                    entry_id,
                    idx,
                    res,
                )

        self._is_first_update = False

        return {
            "account": {
                "messages": messages,
                "bells": bells,
                "pickups": pickups,
                "own_baskets": own_baskets,
                "global_stats": g_stats,
                "user_stats": u_stats,
                "profile": prof,
                "bananas": bananas,
                "buddies": buddies,
                "region_stats": r_stats,
            },
            "locations": location_data,
        }

    async def fetch_location_data(self, entry_id: str, lat: float, lon: float, dist: float) -> dict[str, Any]:
        """Fetch baskets and fairteiler for a specific location."""
        results = await asyncio.gather(
            self.fetch_baskets_for_location(entry_id, lat, lon, dist),
            self.fetch_food_share_points_for_location(lat, lon, dist),
            return_exceptions=True,
        )

        for res in results:
            if isinstance(res, AuthenticationFailed):
                raise res

        baskets, fairteiler = [(r if not isinstance(r, Exception) else []) for r in results]
        return {"baskets": baskets, "fairteiler": fairteiler}

    async def login(self, totp: str | None = None) -> bool | str:
        """Login to Foodsharing API. Returns True on success, '2fa_required' if TOTP needed, False otherwise."""
        try:
            async with asyncio.timeout(30):
                # 1. Check if we already have a session BEFORE hitting /login
                # We try up to 3 times with increasing delay to handle startup network lag
                for attempt in range(3):
                    try:
                        current_url = f"{self.base_url}/api/users/current"
                        auth_headers = self.authenticated_headers
                        _LOGGER.debug(
                            "Attempt %d: Checking session at %s (Token detected: %s)",
                            attempt + 1,
                            current_url,
                            "Yes" if "X-CSRF-Token" in auth_headers else "No",
                        )
                        async with self.session.get(
                            current_url,
                            headers=auth_headers,
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as current_resp:
                            _LOGGER.debug("Session check status: %s", current_resp.status)
                            if current_resp.status == 200:
                                current_data = await current_resp.json()
                                if current_data and "id" in current_data:
                                    _LOGGER.debug(
                                        "Session is VALID for user %s. Login successful.",
                                        current_data["id"],
                                    )
                                    self.user_id = str(current_data["id"])
                                    await self.async_save_session()
                                    return True
                            else:
                                if attempt < 2:
                                    wait_time = (attempt + 1) * 3
                                    _LOGGER.debug(
                                        "Session check failed (status %s), jar has %d cookies. Retrying in %ds...",
                                        current_resp.status,
                                        len(list(self.session.cookie_jar)),
                                        wait_time,
                                    )
                                    await asyncio.sleep(wait_time)
                                    continue
                    except Exception as err:
                        _LOGGER.debug("Session check exception (attempt %d): %s", attempt + 1, err)
                        if attempt < 2:
                            await asyncio.sleep((attempt + 1) * 3)
                            continue

                # 2. If session check failed but we have cookies, they might be stale.
                # Clear them and try fresh login instead of aborting to prevent loops.
                # Loops are prevented by the fact that if this fresh login requires 2FA,
                # we return '2fa_required' which triggers the HA UI flow.
                has_session_cookie = any(c.key == SESSION_COOKIE for c in self.session.cookie_jar)
                if has_session_cookie:
                    _LOGGER.debug(
                        "Session cookie (%s) present but validation failed. "
                        "Clearing stale cookies and attempting fresh login.",
                        SESSION_COOKIE,
                    )
                    # Clear for all common foodsharing domains
                    for d in [
                        "foodsharing.de",
                        "www.foodsharing.de",
                        "beta.foodsharing.de",
                        "foodsharing.at",
                        "www.foodsharing.at",
                        "beta.foodsharing.at",
                        "foodsharing.ch",
                        "www.foodsharing.ch",
                        "beta.foodsharing.ch",
                    ]:
                        self.session.cookie_jar.clear_domain(d)

                # 3. Fetch fresh CSRF token from /login before POST login
                _LOGGER.debug(
                    "Attempting fresh login for %s. Fetching CSRF token from /login first.",
                    mask_email(self.email),
                )
                await self.fetch_csrf()

                # 3. Attempt login
                login_payload = {
                    "email": self.email,
                    "password": self.password,
                    "rememberMe": True,
                }
                if totp:
                    login_payload["code"] = str(totp)

                login_url = f"{self.base_url}/api/login"
                _LOGGER.debug(
                    "Attempting login for %s (TOTP: %s)",
                    mask_email(self.email),
                    "Yes" if totp else "No",
                )
                async with self.session.post(
                    login_url, json=login_payload, headers=self.authenticated_headers
                ) as response:
                    body = None
                    try:
                        body = await response.json()
                    except Exception:
                        await response.text()

                    is_2fa = (
                        response.status in (403, 401)
                        and isinstance(body, dict)
                        and (
                            body.get("code") == "2fa_required"
                            or "2FA required" in body.get("message", "")
                            or (totp and "code" in body.get("message", ""))
                        )
                    )

                    if is_2fa:
                        _LOGGER.debug("Login required 2FA challenge")
                        return "2fa_required"

                    if response.status == 200:
                        _LOGGER.debug("Login successful (200 OK)")
                        user_id = None
                        if isinstance(body, dict):
                            user_id = body.get("id") or (body.get("user") or {}).get("id")

                        if not user_id:
                            # /api/login answers with an empty body (respondOK()), so the
                            # user id has to be resolved separately.
                            try:
                                async with self.session.get(
                                    f"{self.base_url}/api/users/current",
                                    headers=self.authenticated_headers,
                                ) as current_resp:
                                    if current_resp.status == 200:
                                        current_data = await current_resp.json()
                                        user_id = current_data.get("id")
                                    else:
                                        _LOGGER.warning(
                                            "Login returned 200 but %s/api/users/current answered %s: %s",
                                            self.base_url,
                                            current_resp.status,
                                            (await current_resp.text())[:200],
                                        )
                            except Exception as err:
                                _LOGGER.warning(
                                    "Login returned 200 but resolving the user id failed: %s",
                                    err,
                                )

                        if user_id:
                            self.user_id = str(user_id)
                            await self.async_save_session()
                            return True

                    if response.status == 409:
                        _LOGGER.error(
                            "Login failed for %s: account is not activated yet",
                            mask_email(self.email),
                        )
                    elif response.status == 429:
                        _LOGGER.warning(
                            "Login failed for %s: rate limited by the backend, will retry later",
                            mask_email(self.email),
                        )
                    else:
                        _LOGGER.warning(
                            "Login failed for %s: %s %s",
                            mask_email(self.email),
                            response.status,
                            body,
                        )
                    return False
        except Exception as e:
            _LOGGER.error(
                "Error during login for %s: %s",
                mask_email(self.email),
                e,
            )
            return False
        return False

    async def fetch_unread_messages(self) -> int:
        """Fetch the number of conversations with unread messages."""
        # /api/mailbox/unread-count no longer exists (404); the conversation list
        # carries the unread counter per conversation.
        url = f"{self.base_url}/api/conversations"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 401:
                    raise AuthenticationFailed("Unauthorized access while fetching message count.")
                if response.status != 200:
                    _LOGGER.debug("Conversations API returned status %s", response.status)
                    return 0
                data = await response.json()

            conversations = data.get("conversations") if isinstance(data, dict) else data
            if not isinstance(conversations, list):
                return 0

            unread_conversations = [
                c for c in conversations if isinstance(c, dict) and (c.get("unreadMessages") or 0) > 0
            ]
            for conv in unread_conversations:
                last_message = conv.get("lastMessage") or {}
                msg_id = last_message.get("id")
                if msg_id and msg_id not in self._seen_messages:
                    self._seen_messages.add(msg_id)
                    if not self._is_first_update:
                        self.hass.bus.async_fire(
                            f"{DOMAIN}_new_message",
                            {
                                "conversation_id": conv.get("id"),
                                "title": conv.get("title"),
                                "unread": conv.get("unreadMessages"),
                                "body": last_message.get("body"),
                                "author_id": last_message.get("authorId"),
                                "sent_at": last_message.get("sentAt"),
                            },
                        )
            return len(unread_conversations)
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching messages: %s", e)
        return 0

    async def fetch_bells(self) -> int:
        """Fetch unread bell notifications count and trigger events."""
        url = f"{self.base_url}/api/bells"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        # The API returns isRead as a boolean, not is_read as 0/1.
                        unread_bells = [b for b in data if isinstance(b, dict) and not b.get("isRead", True)]
                        for bell in unread_bells:
                            bell_id = bell.get("id")
                            if bell_id and bell_id not in self._seen_bells:
                                self._seen_bells.add(bell_id)
                                if not self._is_first_update:
                                    self.hass.bus.async_fire(f"{DOMAIN}_new_bell", bell)
                        return len(unread_bells)
                elif response.status == 401:
                    raise AuthenticationFailed("Unauthorized access while fetching notifications.")
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching bells: %s", e)
            return 0
        return 0

    async def fetch_global_statistics(self) -> dict[str, Any]:
        """Fetch overall Foodsharing statistics."""
        url = f"{self.base_url}/api/statistics"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, dict):
                        # Extract the generalStatistics part if it exists
                        res = data.get("generalStatistic", data)
                        return res if isinstance(res, dict) else {}
                return {}
        except Exception as e:
            _LOGGER.debug("Error fetching global statistics: %s", e)
            return {}

    async def fetch_baskets_for_location(
        self, entry_id: str, lat: float, lon: float, dist: float
    ) -> list[dict[str, Any]]:
        """Fetch baskets for a specific location."""
        # The API expects kilometres; retrying with metres only yields
        # 404 "Invalid query parameter distance".
        return await self._fetch_baskets_raw(entry_id, lat, lon, dist)

    async def _fetch_baskets_raw(self, entry_id: str, lat: float, lon: float, dist: float) -> list[dict[str, Any]]:
        """Fetch baskets for a specific location using raw parameters."""
        # Ensure parameters are correctly typed and formatted
        f_lat = f"{float(lat):.6f}"
        f_lon = f"{float(lon):.6f}"
        i_dist = int(float(dist))
        url = f"{self.base_url}/api/baskets/nearby?lat={f_lat}&lon={f_lon}&distance={i_dist}"

        try:
            async with (
                asyncio.timeout(15),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                _LOGGER.debug("Baskets API %s returned status: %s", url, response.status)
                if response.status == 200:
                    json_data = await response.json()
                    if not json_data:
                        _LOGGER.debug("Baskets API returned an empty 200 OK response")
                    json_data = await self._add_basket_coordinates(json_data)
                    return self._process_baskets_for_location(entry_id, json_data)

                if response.status == 401:
                    raise AuthenticationFailed("Unauthorized access, token might be expired.")

                body = await response.text()
                _LOGGER.warning("Baskets API failed with status %s: %s", response.status, body[:200])
                return []
        except AuthenticationFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error in _fetch_baskets_raw: %s", e)
            return []

    async def _add_basket_coordinates(self, json_data: Any) -> Any:
        """Enrich baskets with coordinates.

        /api/baskets/nearby only reports distanceInKm; the map markers carry the
        actual position that the geo_location platform needs.
        """
        if not isinstance(json_data, list) or not json_data:
            return json_data
        markers = await self._fetch_markers("baskets", timedelta(minutes=10))
        by_id = {m.get("id"): m for m in markers if isinstance(m, dict)}
        for basket in json_data:
            if not isinstance(basket, dict) or basket.get("latitude") is not None:
                continue
            marker = by_id.get(basket.get("id"))
            if marker:
                basket["latitude"] = marker.get("lat")
                basket["longitude"] = marker.get("lon")
        return json_data

    def _process_baskets_for_location(self, entry_id: str, json_data: Any) -> list[dict[str, Any]]:
        """Process basket data for a specific location context."""
        entry = self.entries.get(entry_id)
        if not entry:
            return []

        keywords_raw = entry.options.get(CONF_KEYWORDS, entry.data.get(CONF_KEYWORDS, "")) or ""
        keywords = [k.strip().lower() for k in str(keywords_raw).split(",") if k.strip()]

        baskets: list[dict[str, Any]] = []

        baskets_data = []
        if isinstance(json_data, list):
            baskets_data = json_data
        elif isinstance(json_data, dict):
            for key in ("baskets", "data", "items", "nearby"):
                if key in json_data and isinstance(json_data[key], list):
                    baskets_data = json_data[key]
                    break
            else:
                _LOGGER.debug(
                    "Baskets dict does not contain recognized list key. Keys: %s",
                    list(json_data.keys()),
                )

        if not baskets_data and json_data:
            _LOGGER.debug("Baskets API returned data but no list was found or it is empty. Status: 200")

        _LOGGER.debug("Found %d baskets in raw data for location %s", len(baskets_data), entry_id)

        # Ensure all elements are dicts and have an ID
        baskets_data = [b for b in baskets_data if isinstance(b, dict) and b.get("id")]
        baskets_data = sorted(baskets_data, key=lambda x: str(x.get("id", "")), reverse=True)

        for basket in baskets_data:
            basket_id = basket.get("id")
            if not basket_id:
                continue

            until_str = "Unknown"
            until_raw = basket.get("until")
            if until_raw:
                try:
                    if isinstance(until_raw, (int, float)):
                        until_str = datetime.fromtimestamp(until_raw, tz=UTC).strftime("%c")
                    else:
                        dt = datetime.fromisoformat(str(until_raw).replace("Z", "+00:00"))
                        until_str = dt.strftime("%c")
                except Exception:
                    until_str = str(until_raw)

            picture = basket.get("picture")
            if picture and picture.lower() != "none" and picture != "unavailable":
                if not picture.startswith("http"):
                    picture = f"{self.base_url}{picture}"
            else:
                picture = None

            location = basket.get("location")
            if isinstance(location, dict):
                lat = location.get("latitude") or location.get("lat")
                lon = location.get("longitude") or location.get("lon")
            else:
                lat = basket.get("latitude") or basket.get("lat")
                lon = basket.get("longitude") or basket.get("lon")

            maps_link = (
                f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                if lat is not None and lon is not None
                else "unavailable"
            )

            desc = basket.get("description") or ""
            match_keywords = False

            if keywords:
                desc_lower = str(desc).lower()
                for keyword in keywords:
                    if keyword in desc_lower:
                        match_keywords = True
                        break

            user_name = basket.get("user_name")
            creator = basket.get("creator")
            if not user_name and isinstance(creator, dict):
                user_name = creator.get("name")

            parsed_basket = {
                "id": basket_id,
                "description": desc,
                "available_until": until_str,
                "picture": picture,
                "latitude": lat,
                "longitude": lon,
                "maps": maps_link,
                "keyword_match": match_keywords,
                "user_name": user_name,
            }

            if match_keywords and basket_id not in self._seen_baskets:
                self._seen_baskets.add(basket_id)
                if not self._is_first_update:
                    self.hass.bus.async_fire(f"{DOMAIN}_keyword_match", parsed_basket)

            baskets.append(parsed_basket)

        return baskets

    async def fetch_food_share_points_for_location(self, lat: float, lon: float, dist: float) -> list[dict[str, Any]]:
        """Fetch Fairteiler around a location.

        /api/foodSharePoints/nearby no longer exists. The map marker endpoint
        returns every food share point with coordinates, so the radius is applied
        locally and only nearby entries are resolved in detail.
        """
        markers = await self._fetch_markers("food-share-points", timedelta(hours=6))
        nearby = []
        for marker in markers:
            m_lat, m_lon = marker.get("lat"), marker.get("lon")
            if m_lat is None or m_lon is None:
                continue
            try:
                if haversine_km(lat, lon, float(m_lat), float(m_lon)) <= dist:
                    nearby.append(marker)
            except (TypeError, ValueError):
                continue

        # ponytail: cap the detail fan-out, a huge radius would otherwise issue
        # hundreds of requests per update. Raise it if someone needs more.
        nearby = nearby[:MAX_FAIRTEILER_DETAILS]

        semaphore = asyncio.Semaphore(5)

        async def build(marker: dict[str, Any]) -> dict[str, Any] | None:
            async with semaphore:
                return await self._build_food_share_point(marker)

        results = await asyncio.gather(*(build(m) for m in nearby), return_exceptions=True)
        points: list[dict[str, Any]] = []
        for res in results:
            if isinstance(res, AuthenticationFailed):
                raise res
            if isinstance(res, dict):
                points.append(res)
        return points

    async def _build_food_share_point(self, marker: dict[str, Any]) -> dict[str, Any] | None:
        """Turn a map marker into a Fairteiler entry including its latest wall post."""
        fp_id = marker.get("id")
        if not fp_id:
            return None

        entry: dict[str, Any] = {
            "id": fp_id,
            "name": marker.get("name", "Unknown Fairteiler"),
            "latitude": marker.get("lat"),
            "longitude": marker.get("lon"),
            "description": None,
            "address": None,
            "picture": None,
            "latest_post": None,
        }

        try:
            async with (
                asyncio.timeout(10),
                self.session.get(
                    f"{self.base_url}/api/food-share-points/{fp_id}",
                    headers=self.authenticated_headers,
                ) as response,
            ):
                if response.status == 401:
                    raise AuthenticationFailed("Unauthorized access while fetching fairteiler.")
                if response.status == 200:
                    detail = await response.json()
                    if isinstance(detail, dict):
                        entry["description"] = detail.get("description")
                        address = detail.get("address")
                        if isinstance(address, dict):
                            entry["address"] = ", ".join(
                                str(address[k])
                                for k in ("street", "postalCode", "city")
                                if address.get(k)
                            )
                        picture = detail.get("picture")
                        if picture and not str(picture).startswith("http"):
                            picture = f"{self.base_url}/images/{picture}"
                        entry["picture"] = picture
                        location = detail.get("location")
                        if isinstance(location, dict):
                            entry["latitude"] = location.get("lat", entry["latitude"])
                            entry["longitude"] = location.get("lon", entry["longitude"])
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching fairteiler %s: %s", fp_id, e)

        await self._attach_latest_wall_post(fp_id, entry)
        return entry

    async def _attach_latest_wall_post(self, fp_id: int, entry: dict[str, Any]) -> None:
        """Fetch the newest wall post of a Fairteiler and fire an event for it."""
        # The wall moved to the generic /api/walls/{target}/{targetId} endpoint,
        # which answers with {"posts": [...]} instead of a bare list.
        url = f"{self.base_url}/api/walls/fairteiler/{fp_id}"
        try:
            async with (
                asyncio.timeout(5),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 401:
                    raise AuthenticationFailed("Unauthorized access while fetching fairteiler wall.")
                if response.status != 200:
                    return
                data = await response.json()

            posts = data.get("posts") if isinstance(data, dict) else data
            if not isinstance(posts, list) or not posts:
                return

            latest_post = posts[0]
            entry["latest_post"] = latest_post
            post_id = latest_post.get("id") if isinstance(latest_post, dict) else None
            if post_id and post_id not in self._seen_fairteiler_posts:
                self._seen_fairteiler_posts.add(post_id)
                if not self._is_first_update:
                    self.hass.bus.async_fire(
                        f"{DOMAIN}_fairteiler_post",
                        {
                            "fairteiler_id": fp_id,
                            "fairteiler_name": entry.get("name"),
                            "post": latest_post,
                        },
                    )
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching wall for fairteiler %s: %s", fp_id, e)

    async def _fetch_markers(self, kind: str, ttl: timedelta) -> list[dict[str, Any]]:
        """Fetch and cache /api/map/markers/{kind} (the only source with coordinates)."""
        cached = self._marker_cache.get(kind)
        now = datetime.now()
        if cached and now - cached[0] < ttl:
            return cached[1]

        url = f"{self.base_url}/api/map/markers/{kind}"
        try:
            async with (
                asyncio.timeout(20),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 401:
                    raise AuthenticationFailed("Unauthorized access while fetching map markers.")
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        self._marker_cache[kind] = (now, data)
                        return data
                _LOGGER.debug("Map markers %s returned status %s", kind, response.status)
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching %s markers: %s", kind, e)
        return cached[1] if cached else []

    async def fetch_pickups(self) -> list[dict[str, Any]]:
        """Fetch upcoming pickups for the user."""
        user_id = self.user_id or "current"
        url = f"{self.base_url}/api/users/{user_id}/pickups/registered"

        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        result = data.get("pickups", data.get("data", []))
                        return result if isinstance(result, list) else []
                elif response.status == 401:
                    raise AuthenticationFailed("Unauthorized access while fetching pickups.")
                elif response.status in (403, 404):
                    _LOGGER.debug(
                        "Pickups not accessible (status %s). User might not be a Foodsaver.",
                        response.status,
                    )
                    return []
                else:
                    body = await response.text()
                    _LOGGER.error("Error fetching pickups: HTTP %s - %s", response.status, body)
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.error("Error fetching pickups: %s", e)
        return []

    async def fetch_own_baskets(self) -> list[dict[str, Any]]:
        """Fetch active baskets created by the user."""
        url = f"{self.base_url}/api/users/current/baskets"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        return [d for d in data if isinstance(d, dict)]
                    if isinstance(data, dict):
                        result = data.get("baskets", [])
                        return result if isinstance(result, list) else []
                elif response.status == 401:
                    raise AuthenticationFailed("Unauthorized access while fetching own baskets.")
                else:
                    _LOGGER.debug("Own baskets not accessible (status %s).", response.status)
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching own baskets: %s", e)
        return []

    async def _ensure_user_id(self) -> str | None:
        """Return the numeric user id, resolving it once via /api/users/current."""
        if self.user_id:
            return self.user_id
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(
                    f"{self.base_url}/api/users/current", headers=self.authenticated_headers
                ) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, dict) and data.get("id"):
                        self.user_id = str(data["id"])
        except Exception as e:
            _LOGGER.debug("Could not resolve user id: %s", e)
        return self.user_id

    async def fetch_user_statistics(self) -> dict[str, Any]:
        """Fetch user-specific statistics.

        There is no dedicated stats endpoint anymore; the numbers live in the
        profile details as {"stats": {"count": ..., "weight": ...}}.
        """
        profile = await self.fetch_user_profile()
        stats = profile.get("stats") if isinstance(profile, dict) else None
        if not isinstance(stats, dict):
            return {}
        return {
            "fetchCount": stats.get("count", 0),
            "fetchWeight": stats.get("weight", 0),
        }

    async def fetch_user_profile(self) -> dict[str, Any]:
        """Fetch the current user profile.

        /api/users/current only returns id/name/avatar; the details endpoint also
        carries regionId, regionName and the user's own pickup statistics.
        """
        url = f"{self.base_url}/api/users/current/details"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, dict):
                        if data.get("id") and not self.user_id:
                            self.user_id = str(data["id"])
                        return data
        except Exception as e:
            _LOGGER.debug("Error fetching profile: %s", e)
        return {}

    async def fetch_bananas(self) -> dict[str, Any]:
        """Fetch user banana metadata (thanks ratings)."""
        user_id = await self._ensure_user_id()
        if not user_id:
            return {}
        # This endpoint does not accept the "current" alias.
        url = f"{self.base_url}/api/users/{user_id}/bananas/meta"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    return data if isinstance(data, dict) else {}
        except Exception as e:
            _LOGGER.debug("Error fetching bananas: %s", e)
        return {}

    async def fetch_buddies(self) -> list[dict[str, Any]]:
        """Fetch user buddylist."""
        url = f"{self.base_url}/api/users/current/buddies"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    # The API wraps the list: {"buddies": [...], "myRequests": [...]}
                    if isinstance(data, dict):
                        data = data.get("buddies", [])
                    return data if isinstance(data, list) else []
        except Exception as e:
            _LOGGER.debug("Error fetching buddies: %s", e)
        return []

    async def fetch_region_statistics(self, region_id: int) -> dict[str, Any]:
        """Fetch pickup statistics for a region.

        The old /api/regions/{id}/statistics endpoint is gone; only the pickup
        statistics remain, newest entry first.
        """
        url = f"{self.base_url}/api/regions/{region_id}/statistics/pickups"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if not isinstance(data, dict):
                        return {}
                    monthly = data.get("monthly") or []
                    current = monthly[0] if monthly and isinstance(monthly[0], dict) else {}
                    return {
                        "month": current.get("date"),
                        "numberOfPickups": current.get("numberOfPickups"),
                        "numberOfStores": current.get("numberOfStores"),
                        "numberOfSlots": current.get("numberOfSlots"),
                        "numberOfFoodsavers": current.get("numberOfFoodsavers"),
                    }
        except Exception as e:
            _LOGGER.debug("Error fetching region stats: %s", e)
        return {}

    def _normalize_account_results(
        self, results: dict[str, Any]
    ) -> tuple[
        int,
        int,
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        list[dict[str, Any]],
        dict[str, Any],
    ]:
        """Normalize account results, using defaults for failures."""
        task_defaults = {
            "messages": 0,
            "bells": 0,
            "pickups": [],
            "own_baskets": [],
            "global_stats": {},
            "user_stats": {},
            "profile": {},
            "bananas": {},
            "buddies": [],
            "region_stats": {},
        }

        normalized: dict[str, Any] = {}
        for key, default in task_defaults.items():
            val = results.get(key)
            if isinstance(val, Exception) or val is None:
                if isinstance(val, Exception):
                    _LOGGER.debug("Error in %s task: %s", key, val)
                normalized[key] = default
            else:
                normalized[key] = val

        return (
            int(normalized["messages"]),
            int(normalized["bells"]),
            normalized["pickups"],
            normalized["own_baskets"],
            normalized["global_stats"],
            normalized["user_stats"],
            normalized["profile"],
            normalized["bananas"],
            normalized["buddies"],
            normalized["region_stats"],
        )
