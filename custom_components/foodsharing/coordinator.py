import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import async_timeout
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DISTANCE,
    CONF_EMAIL,
    CONF_KEYWORDS,
    CONF_LATITUDE_FS,
    CONF_LONGITUDE_FS,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class FoodsharingCoordinator(DataUpdateCoordinator[dict[str, Any]]):  # type: ignore[misc]
    """Class to manage fetching Foodsharing data."""

    def __init__(self, hass: HomeAssistant, entry: config_entries.ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.email = entry.data[CONF_EMAIL]
        self.password = entry.data[CONF_PASSWORD]
        self.latitude = entry.data[CONF_LATITUDE_FS]
        self.longitude = entry.data[CONF_LONGITUDE_FS]
        self.distance = entry.options.get(
            CONF_DISTANCE, entry.data.get(CONF_DISTANCE, 7)
        )
        self.keywords = [
            k.strip().lower()
            for k in entry.options.get(CONF_KEYWORDS, "").split(",")
            if k.strip()
        ]
        self.session = async_get_clientsession(hass)

        self._seen_messages: set[int] = set()
        self._seen_bells: set[int] = set()
        self._seen_fairteiler_posts: set[int] = set()
        self._seen_baskets: set[int] = set()
        self._is_first_update = True

        scan_interval = timedelta(
            minutes=entry.options.get(
                CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, 2)
            )
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            return await self._fetch_all_data()
        except UpdateFailed as err:
            _LOGGER.warning("UpdateFailed: %s, attempting re-login.", err)
            # Try to login and fetch again
            if await self.login():
                return await self._fetch_all_data()
            raise UpdateFailed("Authentication failed during retry.") from err
        except Exception as err:
            raise UpdateFailed(
                f"Unexpected error communicating with API: {err}"
            ) from err

    async def _fetch_all_data(self) -> dict[str, Any]:
        baskets = await self.fetch_baskets()
        messages = await self.fetch_unread_messages()
        bells = await self.fetch_bells()
        fairteiler = await self.fetch_food_share_points()
        pickups = await self.fetch_pickups()
        own_baskets = await self.fetch_own_baskets()

        self._is_first_update = False

        return {
            "baskets": baskets,
            "messages": messages,
            "bells": bells,
            "fairteiler": fairteiler,
            "pickups": pickups,
            "own_baskets": own_baskets,
        }

    async def login(self) -> bool:
        """Login to Foodsharing API."""
        try:
            async with async_timeout.timeout(10):
                login_payload = {
                    "email": self.email,
                    "password": self.password,
                    "remember_me": "true",
                }
                login_url = "https://foodsharing.de/api/user/login"
                async with self.session.post(login_url, json=login_payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return "id" in data
                    else:
                        _LOGGER.error("Login failed with status %s", response.status)
                        return False
        except Exception as e:
            _LOGGER.error("Error during login: %s", e)
            return False

    async def fetch_unread_messages(self) -> int:
        """Fetch unread mailbox message count and detailed conversations."""
        url_count = "https://foodsharing.de/api/mailbox/unread-count"
        url_conv = "https://foodsharing.de/api/conversations"
        unread = 0
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(url_count) as response:
                    if response.status == 200:
                        data = await response.json()
                        unread = data.get("unread", 0) if isinstance(data, dict) else 0

                if unread > 0:
                    async with self.session.get(url_conv) as response:
                        if response.status == 200:
                            data = await response.json()
                            if isinstance(data, list):
                                for conv in data:
                                    if (
                                        isinstance(conv, dict)
                                        and conv.get("unread", 0) > 0
                                    ):
                                        msg_id = conv.get("last_message", {}).get("id")
                                        if msg_id and msg_id not in self._seen_messages:
                                            self._seen_messages.add(msg_id)
                                            if not self._is_first_update:
                                                self.hass.bus.async_fire(
                                                    f"{DOMAIN}_new_message",
                                                    {
                                                        "conversation_id": conv.get(
                                                            "id"
                                                        ),
                                                        "message": conv.get(
                                                            "last_message", {}
                                                        ),
                                                    },
                                                )
        except Exception as e:
            _LOGGER.debug("Error fetching conversations: %s", e)
        return unread

    async def fetch_bells(self) -> int:
        """Fetch unread bell notifications count and trigger events."""
        url = "https://foodsharing.de/api/bells"
        try:
            async with async_timeout.timeout(10), self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        unread_count = 0
                        for bell in data:
                            if isinstance(bell, dict) and bell.get("is_read") == 0:
                                unread_count += 1
                                bell_id = bell.get("id")
                                if bell_id and bell_id not in self._seen_bells:
                                    self._seen_bells.add(bell_id)
                                    if not self._is_first_update:
                                        self.hass.bus.async_fire(
                                            f"{DOMAIN}_new_bell", bell
                                        )
                        return unread_count
        except Exception as e:
            _LOGGER.debug("Error fetching bells: %s", e)
        return 0

    async def fetch_baskets(self) -> list[dict[str, Any]]:
        """Fetch baskets and return structured data without Nominatim."""
        url = f"https://foodsharing.de/api/baskets/nearby?lat={self.latitude}&lon={self.longitude}&distance={self.distance}"
        try:
            async with async_timeout.timeout(10), self.session.get(url) as response:
                if response.status == 200:
                    json_data = await response.json()
                    return self._process_baskets(json_data)
                elif response.status == 401:
                    raise UpdateFailed("Unauthorized access, token might be expired.")
                elif response.status == 503:
                    raise UpdateFailed("Foodsharing API is offline (503).")
                else:
                    raise UpdateFailed(
                        f"Error fetching baskets: HTTP {response.status}"
                    )
        except Exception as e:
            if isinstance(e, UpdateFailed):
                raise
            raise UpdateFailed(f"Error fetching data: {e}") from e

    def _process_baskets(self, json_data: Any) -> list[dict[str, Any]]:
        """Process basket data to structured format."""
        baskets: list[dict[str, Any]] = []

        baskets_data = (
            json_data.get("baskets", []) if isinstance(json_data, dict) else json_data
        )

        if not isinstance(baskets_data, list):
            _LOGGER.error("Unexpected baskets format")
            return []

        # Sort descending by ID (newest first)
        baskets_data = sorted(baskets_data, key=lambda x: x.get("id", 0), reverse=True)

        for basket in baskets_data:
            basket_id = basket.get("id")
            if not basket_id:
                continue

            until_str = "Unknown"
            if "until" in basket:
                try:
                    until_str = datetime.fromtimestamp(basket["until"]).strftime("%c")
                except Exception:
                    pass

            picture = basket.get("picture")
            if picture and picture.lower() != "none" and picture != "unavailable":
                picture = f"https://foodsharing.de{picture}"
            else:
                picture = None

            lat = basket.get("lat")
            lon = basket.get("lon")
            maps_link = (
                f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                if lat and lon
                else "unavailable"
            )

            # Intentionally skipping Nominatim to prevent API rate limiting issues
            # We provide just the coordinates instead

            desc = basket.get("description", "")
            match_keywords = False

            if self.keywords:
                desc_lower = desc.lower()
                for keyword in self.keywords:
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
            }

            if match_keywords and basket_id not in self._seen_baskets:
                self._seen_baskets.add(basket_id)
                if not self._is_first_update:
                    self.hass.bus.async_fire(f"{DOMAIN}_keyword_match", parsed_basket)

            baskets.append(parsed_basket)

        return baskets

    async def fetch_food_share_points(self) -> list[dict[str, Any]]:
        """Fetch nearby Fairteiler (Food Share Points)."""
        # Note: The api endpoint requires bounds or lat/lon distance. The website uses api/maps/blabla
        # To be safe, we'll try something similar to baskets.
        # Actually from the api/doc earlier, it might be /api/foodSharePoints/nearby
        # If it doesn't exist we'll just handle 404 cleanly.
        url = f"https://foodsharing.de/api/foodSharePoints/nearby?lat={self.latitude}&lon={self.longitude}&distance={self.distance}"
        try:
            async with async_timeout.timeout(10), self.session.get(url) as response:
                if response.status == 200:
                    json_data = await response.json()
                    fairteiler_data = (
                        json_data.get("foodSharePoints", [])
                        if isinstance(json_data, dict)
                        else json_data
                    )
                    if not isinstance(fairteiler_data, list):
                        return []

                    points = []
                    semaphore = asyncio.Semaphore(5)

                    async def fetch_wall(fp_id: int, fp_name: str) -> None:
                        async with semaphore:
                            wall_url = (
                                f"https://foodsharing.de/api/fairteiler/{fp_id}/wall"
                            )
                            try:
                                async with async_timeout.timeout(5), self.session.get(
                                    wall_url
                                ) as wall_res:
                                        if wall_res.status == 200:
                                            wall_data = await wall_res.json()
                                            if (
                                                isinstance(wall_data, list)
                                                and len(wall_data) > 0
                                            ):
                                                latest_post = wall_data[0]
                                                post_id = latest_post.get("id")
                                                if (
                                                    post_id
                                                    and post_id
                                                    not in self._seen_fairteiler_posts
                                                ):
                                                    self._seen_fairteiler_posts.add(
                                                        post_id
                                                    )
                                                    if not self._is_first_update:
                                                        self.hass.bus.async_fire(
                                                            f"{DOMAIN}_fairteiler_post",
                                                            {
                                                                "fairteiler_id": fp_id,
                                                                "fairteiler_name": fp_name,
                                                                "post": latest_post,
                                                            },
                                                        )
                            except Exception as e:
                                _LOGGER.debug(
                                    f"Error fetching wall for fairteiler {fp_id}: {e}"
                                )

                    wall_tasks = []
                    for fp in fairteiler_data:
                        if not isinstance(fp, dict):
                            continue
                        fp_id = fp.get("id")
                        fp_name = fp.get("name", "Unknown Fairteiler")
                        points.append(
                            {
                                "id": fp_id,
                                "name": fp_name,
                                "latitude": fp.get("lat"),
                                "longitude": fp.get("lon"),
                            }
                        )

                        if fp_id:
                            wall_tasks.append(fetch_wall(fp_id, fp_name))

                    if wall_tasks:
                        await asyncio.gather(*wall_tasks)

                    return points
                else:
                    # Sometimes this endpoint doesn't exist, ignore failures gracefully
                    _LOGGER.debug(f"Food Share Points fetch returned {response.status}")
                    return []
        except Exception:
            return []

    async def fetch_pickups(self) -> list[dict[str, Any]]:
        """Fetch upcoming pickups for the user."""
        url = (
            "https://foodsharing.de/api/pickups"  # Or whatever the correct endpoint is
        )
        try:
            async with async_timeout.timeout(10), self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        result = data.get("pickups", data.get("data", []))
                        return result if isinstance(result, list) else []
        except Exception as e:
            _LOGGER.debug("Error fetching pickups: %s", e)
        return []

    async def fetch_own_baskets(self) -> list[dict[str, Any]]:
        """Fetch active baskets created by the user."""
        url = "https://foodsharing.de/api/baskets/own"
        try:
            async with async_timeout.timeout(10), self.session.get(url) as response:
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
        except Exception as e:
            _LOGGER.debug("Error fetching own baskets: %s", e)
        return []
