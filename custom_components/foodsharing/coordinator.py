import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

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
import json
import os

from .const import (
    CONF_DOMAIN,
    CONF_KEYWORDS,
    CONF_SCAN_INTERVAL,
    CONF_USE_BETA_API,
    DOMAIN,
)
from .helpers import get_locations_from_entry, mask_email

_LOGGER = logging.getLogger(__name__)


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
        self._seen_baskets: set[int] = set()
        self._is_first_update = True
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        self.user_id: str | None = None
        self._xsrf_token: str | None = None
        self.base_url = "https://foodsharing.de"
        self._update_base_url()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{email}",
            update_interval=timedelta(minutes=2),
        )
        self._session_file = hass.config.path(".storage", f"foodsharing_session_{email.replace('@', '_').replace('.', '_')}.json")
        self._load_session()

    def _get_xsrf_token_from_jar(self) -> str | None:
        """Extract XSRF-TOKEN from cookie jar manually to avoid yarl dependency."""
        for cookie in self.session.cookie_jar:
            if cookie.key.lower() == "xsrf-token":
                return cookie.value
        return None

    @property
    def authenticated_headers(self) -> dict[str, str]:
        """Return headers with CSRF token for authenticated requests."""
        headers = {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
            "X-Requested-With": "XMLHttpRequest",
        }

        # Always check the jar to stay in sync with the session
        token = self._get_xsrf_token_from_jar()
        if token:
            headers["X-Csrf-Token"] = token
            self._xsrf_token = token
        elif self._xsrf_token:
            headers["X-Csrf-Token"] = self._xsrf_token

        return headers

    def _load_session(self) -> None:
        """Load session cookies and metadata from file."""
        if not os.path.exists(self._session_file):
            return
        try:
            with open(self._session_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cookies_data = data.get("cookies", {})
                    self.user_id = data.get("user_id")
                    self._xsrf_token = data.get("xsrf_token")

                    if cookies_data:
                        try:
                            from yarl import URL
                            self.session.cookie_jar.update_cookies(cookies_data, URL(self.base_url))
                        except Exception:
                            # Fallback if yarl is somehow not there (it should be)
                            self.session.cookie_jar.update_cookies(cookies_data)
                    _LOGGER.debug("Loaded persisted session for %s (User ID: %s)", self.email, self.user_id)
        except Exception as e:
            _LOGGER.warning("Could not load session file: %s", e)

    def _save_session(self) -> None:
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

            with open(self._session_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            _LOGGER.debug("Saved session for %s", self.email)
        except Exception as e:
            _LOGGER.warning("Could not save session file: %s", e)

    async def fetch_csrf(self):
        """Fetch the CSRF token from the login page."""
        try:
            # Hit /login to ensure we get the right cookies
            async with self.session.get(
                f"{self.base_url}/login", headers={"User-Agent": self._user_agent}
            ) as response:
                await response.text()
                token = self._get_xsrf_token_from_jar()
                if token:
                    self._xsrf_token = token
                    _LOGGER.debug("Fetched CSRF token: %s", self._xsrf_token)
                else:
                    _LOGGER.debug("No XSRF-TOKEN cookie found on /login")
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
            if entry.options.get(
                CONF_USE_BETA_API, entry.data.get(CONF_USE_BETA_API, False)
            ):
                use_beta = True

            # Get domain from entry, default to de
            entry_domain = entry.options.get(
                CONF_DOMAIN, entry.data.get(CONF_DOMAIN, "foodsharing_de")
            )
            if entry_domain != "foodsharing_de":
                domain = entry_domain

        base_domain = "foodsharing.de"
        if domain == "foodsharing_at":
            base_domain = "foodsharing.at"
        elif domain == "foodsharing_ch":
            base_domain = "foodsharing.ch"

        self.base_url = (
            f"https://beta.{base_domain}" if use_beta else f"https://{base_domain}"
        )
        _LOGGER.debug("Foodsharing base URL set to %s", self.base_url)

    def _update_refresh_interval(self) -> None:
        """Update the update interval based on entries."""
        if not self.entries:
            return

        min_interval = 60
        for entry in self.entries.values():
            interval = entry.options.get(
                CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, 2)
            )
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
                raise ConfigEntryAuthFailed(
                    "2FA required for Foodsharing account"
                ) from err

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
            raise UpdateFailed(
                f"Unexpected error communicating with API: {err}"
            ) from err

    async def _fetch_all_data(self) -> dict[str, Any]:
        """Fetch all data for all locations."""
        task_keys = ["messages", "bells", "pickups", "own_baskets"]
        account_results = await asyncio.gather(
            self.fetch_unread_messages(),
            self.fetch_bells(),
            self.fetch_pickups(),
            self.fetch_own_baskets(),
            return_exceptions=True,
        )

        keyed_results = dict(zip(task_keys, account_results, strict=True))

        for res in account_results:
            if isinstance(res, AuthenticationFailed):
                raise res

        messages, bells, pickups, own_baskets = self._normalize_account_results(
            keyed_results
        )

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
            },
            "locations": location_data,
        }

    async def fetch_location_data(
        self, entry_id: str, lat: float, lon: float, dist: float
    ) -> dict[str, Any]:
        """Fetch baskets and fairteiler for a specific location."""
        results = await asyncio.gather(
            self.fetch_baskets_for_location(entry_id, lat, lon, dist),
            self.fetch_food_share_points_for_location(lat, lon, dist),
            return_exceptions=True,
        )

        for res in results:
            if isinstance(res, AuthenticationFailed):
                raise res

        baskets, fairteiler = [
            (r if not isinstance(r, Exception) else []) for r in results
        ]
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
                            "Yes" if "X-Csrf-Token" in auth_headers else "No",
                        )
                        async with self.session.get(
                            current_url, headers=auth_headers, timeout=10
                        ) as current_resp:
                            _LOGGER.debug(
                                "Session check status: %s", current_resp.status
                            )
                            if current_resp.status == 200:
                                current_data = await current_resp.json()
                                if current_data and "id" in current_data:
                                    _LOGGER.debug(
                                        "Session is VALID for user %s. Login successful.",
                                        current_data["id"],
                                    )
                                    self.user_id = str(current_data["id"])
                                    self._save_session()
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
                        _LOGGER.debug(
                            "Session check exception (attempt %d): %s", attempt + 1, err
                        )
                        if attempt < 2:
                            await asyncio.sleep((attempt + 1) * 3)
                            continue

                # 2. Check if we have a dead session (prevents 2FA loop)
                has_session_cookie = any(c.key == "PHPSESSID" for c in self.session.cookie_jar)
                if has_session_cookie:
                    _LOGGER.warning(
                        "Session cookie (PHPSESSID) present but validation failed. "
                        "Aborting auto-login to prevent 2FA challenge loop. User must re-authenticate."
                    )
                    return False

                # 3. If no session, fetch fresh CSRF token from /login
                _LOGGER.warning(
                    "No valid session found. Fetching fresh CSRF token from /login before POST login."
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
                            user_id = body.get("id") or (body.get("user") or {}).get(
                                "id"
                            )

                        if not user_id:
                            # Fallback: get ID from current user endpoint
                            try:
                                async with self.session.get(
                                    f"{self.base_url}/api/users/current",
                                    headers=self.authenticated_headers,
                                ) as current_resp:
                                    if current_resp.status == 200:
                                        current_data = await current_resp.json()
                                        user_id = current_data.get("id")
                            except Exception:
                                pass

                        if user_id:
                            self.user_id = str(user_id)
                            self._save_session()
                            return True

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
        """Fetch unread mailbox message count and detailed conversations."""
        url_count = f"{self.base_url}/api/mailbox/unread-count"
        url_conv = f"{self.base_url}/api/conversations"
        unread = 0
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(
                    url_count, headers=self.authenticated_headers
                ) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    unread = data.get("unread", 0) if isinstance(data, dict) else 0
                elif response.status == 401:
                    raise AuthenticationFailed(
                        "Unauthorized access while fetching message count."
                    )

            if unread > 0:
                async with (
                    asyncio.timeout(10),
                    self.session.get(
                        url_conv, headers=self.authenticated_headers
                    ) as response,
                ):
                    if response.status == 200:
                        data = await response.json()
                        if isinstance(data, list):
                            for conv in data:
                                if isinstance(conv, dict) and conv.get("unread", 0) > 0:
                                    msg_id = conv.get("last_message", {}).get("id")
                                    if msg_id and msg_id not in self._seen_messages:
                                        self._seen_messages.add(msg_id)
                                        if not self._is_first_update:
                                            self.hass.bus.async_fire(
                                                f"{DOMAIN}_new_message",
                                                {
                                                    "conversation_id": conv.get("id"),
                                                    "message": conv.get(
                                                        "last_message", {}
                                                    ),
                                                },
                                            )
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching conversations: %s", e)
        return unread

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
                        unread_bells = [
                            b
                            for b in data
                            if isinstance(b, dict) and b.get("is_read") == 0
                        ]
                        for bell in unread_bells:
                            bell_id = bell.get("id")
                            if bell_id and bell_id not in self._seen_bells:
                                self._seen_bells.add(bell_id)
                                if not self._is_first_update:
                                    self.hass.bus.async_fire(f"{DOMAIN}_new_bell", bell)
                        return len(unread_bells)
                elif response.status == 401:
                    raise AuthenticationFailed(
                        "Unauthorized access while fetching notifications."
                    )
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching bells: %s", e)
            return 0
        return 0

    async def fetch_baskets_for_location(
        self, entry_id: str, lat: float, lon: float, dist: float
    ) -> list[dict[str, Any]]:
        """Fetch baskets for a specific location."""
        url = f"{self.base_url}/api/baskets/nearby?lat={lat}&lon={lon}&distance={dist}"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    json_data = await response.json()
                    return self._process_baskets_for_location(entry_id, json_data)
                elif response.status == 401:
                    raise AuthenticationFailed(
                        "Unauthorized access, token might be expired."
                    )
                elif response.status == 503:
                    async_create_issue(
                        self.hass,
                        DOMAIN,
                        "api_offline",
                        is_fixable=False,
                        severity=IssueSeverity.WARNING,
                        translation_key="api_offline",
                    )
                    raise UpdateFailed("Foodsharing API is offline (503).")
                else:
                    raise UpdateFailed(
                        f"Error fetching baskets: HTTP {response.status}"
                    )
        except UpdateFailed:
            raise
        except AuthenticationFailed:
            raise
        except Exception as e:
            raise UpdateFailed(f"Error fetching data: {e}") from e
        return []

    def _process_baskets_for_location(
        self, entry_id: str, json_data: Any
    ) -> list[dict[str, Any]]:
        """Process basket data for a specific location context."""
        entry = self.entries.get(entry_id)
        if not entry:
            return []

        keywords_raw = entry.options.get(
            CONF_KEYWORDS, entry.data.get(CONF_KEYWORDS, "")
        )
        keywords = [k.strip().lower() for k in keywords_raw.split(",") if k.strip()]

        baskets: list[dict[str, Any]] = []

        baskets_data = (
            json_data.get("baskets", []) if isinstance(json_data, dict) else json_data
        )

        if not isinstance(baskets_data, list):
            _LOGGER.error("Unexpected baskets format")
            return []

        baskets_data = sorted(baskets_data, key=lambda x: x.get("id", 0), reverse=True)

        for basket in baskets_data:
            basket_id = basket.get("id")
            if not basket_id:
                continue

            until_str = "Unknown"
            if "until" in basket:
                try:
                    until_str = datetime.fromtimestamp(
                        basket["until"], tz=UTC
                    ).strftime("%c")
                except Exception:
                    pass

            picture = basket.get("picture")
            if picture and picture.lower() != "none" and picture != "unavailable":
                picture = f"{self.base_url}{picture}"
            else:
                picture = None

            lat = basket.get("lat")
            lon = basket.get("lon")
            maps_link = (
                f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                if lat and lon
                else "unavailable"
            )

            desc = basket.get("description", "")
            match_keywords = False

            if keywords:
                desc_lower = desc.lower()
                for keyword in keywords:
                    if keyword in desc_lower:
                        match_keywords = True
                        break

            parsed_basket = {
                "id": basket_id,
                "description": desc,
                "available_until": until_str,
                "picture": picture,
                "latitude": lat,
                "longitude": lon,
                "maps": maps_link,
                "keyword_match": match_keywords,
                "user_name": basket.get("user_name"),
            }

            if match_keywords and basket_id not in self._seen_baskets:
                self._seen_baskets.add(basket_id)
                if not self._is_first_update:
                    self.hass.bus.async_fire(f"{DOMAIN}_keyword_match", parsed_basket)

            baskets.append(parsed_basket)

        return baskets

    async def fetch_food_share_points_for_location(
        self, lat: float, lon: float, dist: float
    ) -> list[dict[str, Any]]:
        """Fetch nearby Fairteiler for a specific location."""
        url = f"{self.base_url}/api/foodSharePoints/nearby?lat={lat}&lon={lon}&distance={dist}"
        points: list[dict[str, Any]] = []
        wall_tasks: list[Any] = []

        try:
            semaphore = asyncio.Semaphore(5)

            async def fetch_wall(
                fp_id: int, fp_name: str, fp_entry: dict[str, Any]
            ) -> None:
                async with semaphore:
                    wall_url = f"{self.base_url}/api/fairteiler/{fp_id}/wall"
                    try:
                        async with (
                            asyncio.timeout(5),
                            self.session.get(
                                wall_url, headers=self.authenticated_headers
                            ) as wall_res,
                        ):
                            if wall_res.status == 200:
                                wall_data = await wall_res.json()
                                if isinstance(wall_data, list) and len(wall_data) > 0:
                                    latest_post = wall_data[0]
                                    fp_entry["latest_post"] = latest_post

                                    post_id = latest_post.get("id")
                                    if (
                                        post_id
                                        and post_id not in self._seen_fairteiler_posts
                                    ):
                                        self._seen_fairteiler_posts.add(post_id)
                                        if not self._is_first_update:
                                            self.hass.bus.async_fire(
                                                f"{DOMAIN}_fairteiler_post",
                                                {
                                                    "fairteiler_id": fp_id,
                                                    "fairteiler_name": fp_name,
                                                    "post": latest_post,
                                                },
                                            )
                            elif wall_res.status == 401:
                                raise AuthenticationFailed(
                                    "Unauthorized access while fetching fairteiler wall."
                                )
                    except AuthenticationFailed:
                        raise
                    except Exception as e:
                        _LOGGER.debug(
                            "Error fetching wall for fairteiler %s: %s",
                            fp_id,
                            e,
                        )

            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    json_data = await response.json()
                    fairteiler_data = (
                        json_data.get("foodSharePoints", [])
                        if isinstance(json_data, dict)
                        else json_data
                    )
                    if not isinstance(fairteiler_data, list):
                        return []

                    for fp in fairteiler_data:
                        if not isinstance(fp, dict):
                            continue
                        fp_id = fp.get("id")
                        fp_name = fp.get("name", "Unknown Fairteiler")

                        picture = fp.get("picture")
                        if picture and not picture.startswith("http"):
                            picture = f"{self.base_url}{picture}"

                        desc = fp.get("desc")
                        if not desc or desc == "Unknown":
                            desc = fp.get("description", desc)

                        fp_entry = {
                            "id": fp_id,
                            "name": fp_name,
                            "latitude": fp.get("lat"),
                            "longitude": fp.get("lon"),
                            "description": desc,
                            "address": fp.get("address"),
                            "picture": picture,
                            "latest_post": None,
                        }
                        points.append(fp_entry)

                        if fp_id:
                            wall_tasks.append(fetch_wall(fp_id, fp_name, fp_entry))
                elif response.status == 401:
                    raise AuthenticationFailed(
                        "Unauthorized access while fetching fairteiler."
                    )
                else:
                    _LOGGER.debug(
                        "Food Share Points fetch returned %s", response.status
                    )
                    return []

            if wall_tasks:
                await asyncio.gather(*wall_tasks)

        except AuthenticationFailed, asyncio.CancelledError:
            raise
        except Exception:
            return []

        return points

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
                    raise AuthenticationFailed(
                        "Unauthorized access while fetching pickups."
                    )
                elif response.status in (403, 404):
                    _LOGGER.debug(
                        "Pickups not accessible (status %s). User might not be a Foodsaver.",
                        response.status,
                    )
                    return []
                else:
                    body = await response.text()
                    _LOGGER.error(
                        "Error fetching pickups: HTTP %s - %s", response.status, body
                    )
        except AuthenticationFailed, UpdateFailed:
            raise
        except Exception as e:
            _LOGGER.error("Error fetching pickups: %s", e)
        return []

    async def fetch_own_baskets(self) -> list[dict[str, Any]]:
        """Fetch active baskets created by the user."""
        url = f"{self.base_url}/api/baskets/own"
        try:
            async with (
                asyncio.timeout(10),
                self.session.get(url, headers=self.authenticated_headers) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        return [d for d in data if isinstance(d, dict)]
                    elif isinstance(data, dict):
                        result = data.get("baskets", [])
                        return (
                            [r for r in result if isinstance(r, dict)]
                            if isinstance(result, list)
                            else []
                        )
                elif response.status == 401:
                    raise AuthenticationFailed(
                        "Unauthorized access while fetching own baskets."
                    )
                elif response.status in (403, 404):
                    _LOGGER.debug(
                        "Own baskets not accessible (status %s).", response.status
                    )
                    return []
        except AuthenticationFailed:
            raise
        except Exception as e:
            _LOGGER.debug("Error fetching own baskets: %s", e)
        return []

    def _normalize_account_results(
        self, results: dict[str, Any]
    ) -> tuple[int, int, list[dict[str, Any]], list[dict[str, Any]]]:
        """Normalize account results, using defaults for failures."""
        messages_val = results.get("messages", 0)
        messages = int(messages_val) if isinstance(messages_val, (int, float)) else 0

        bells_val = results.get("bells", 0)
        bells = int(bells_val) if isinstance(bells_val, (int, float)) else 0

        pickups_val = results.get("pickups", [])
        pickups: list[dict[str, Any]] = (
            pickups_val if isinstance(pickups_val, list) else []
        )

        own_baskets_val = results.get("own_baskets", [])
        own_baskets: list[dict[str, Any]] = (
            own_baskets_val if isinstance(own_baskets_val, list) else []
        )

        return messages, bells, pickups, own_baskets
