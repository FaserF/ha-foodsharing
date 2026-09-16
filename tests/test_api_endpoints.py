"""Tests for the endpoints and payload shapes the foodsharing API actually uses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.foodsharing.coordinator import FoodsharingCoordinator


def _coordinator(session):
    with patch(
        "custom_components.foodsharing.coordinator.async_get_clientsession",
        return_value=session,
    ):
        return FoodsharingCoordinator(MagicMock(), "test@test.com", "pass")


def _response(status=200, json_data=None, text=""):
    resp = AsyncMock()
    resp.status = status
    resp.json.return_value = json_data
    resp.text.return_value = text
    return resp


@pytest.mark.asyncio
async def test_food_share_points_filtered_by_radius(mock_session):
    """Only markers inside the radius are resolved in detail."""
    coordinator = _coordinator(mock_session)
    coordinator._fetch_markers = AsyncMock(
        return_value=[
            {"id": 1, "name": "Near", "lat": 53.914, "lon": 10.741},
            {"id": 2, "name": "Far", "lat": 48.137, "lon": 11.575},
            {"id": 3, "name": "Broken", "lat": None, "lon": None},
        ]
    )
    detail = _response(json_data={"description": "d", "address": {"street": "S", "city": "C"}})
    wall = _response(json_data={"posts": [{"id": 7, "body": "hi"}]})
    mock_session.get.return_value.__aenter__.side_effect = [detail, wall]

    points = await coordinator.fetch_food_share_points_for_location(53.913795, 10.741268, 5)

    assert [p["id"] for p in points] == [1]
    assert points[0]["latitude"] == 53.914
    assert points[0]["address"] == "S, C"
    assert points[0]["latest_post"]["id"] == 7


@pytest.mark.asyncio
async def test_basket_coordinates_come_from_markers(mock_session):
    """/api/baskets/nearby has no coordinates, the map markers provide them."""
    coordinator = _coordinator(mock_session)
    coordinator._fetch_markers = AsyncMock(
        return_value=[{"id": 42, "lat": 53.5, "lon": 10.1}]
    )

    baskets = await coordinator._add_basket_coordinates(
        [{"id": 42, "description": "x"}, {"id": 99, "description": "unknown"}]
    )

    assert baskets[0]["latitude"] == 53.5
    assert baskets[0]["longitude"] == 10.1
    assert baskets[1].get("latitude") is None


@pytest.mark.asyncio
async def test_region_statistics_uses_newest_month(mock_session):
    """The pickup statistics are sorted newest first."""
    coordinator = _coordinator(mock_session)
    mock_session.get.return_value.__aenter__.return_value = _response(
        json_data={
            "monthly": [
                {"date": "2026-09", "numberOfPickups": 27, "numberOfStores": 3,
                 "numberOfSlots": 35, "numberOfFoodsavers": 12},
                {"date": "2026-08", "numberOfPickups": 1, "numberOfStores": 1,
                 "numberOfSlots": 1, "numberOfFoodsavers": 1},
            ],
            "weekly": [],
            "daily": [],
        }
    )

    stats = await coordinator.fetch_region_statistics(92)

    assert stats["month"] == "2026-09"
    assert stats["numberOfPickups"] == 27
    assert stats["numberOfFoodsavers"] == 12


@pytest.mark.asyncio
async def test_buddies_are_unwrapped(mock_session):
    """The buddy list is wrapped in a dict alongside pending requests."""
    coordinator = _coordinator(mock_session)
    mock_session.get.return_value.__aenter__.return_value = _response(
        json_data={"buddies": [{"id": 1}, {"id": 2}], "myRequests": [{"id": 3}], "requestsToMe": []}
    )

    assert len(await coordinator.fetch_buddies()) == 2


@pytest.mark.asyncio
async def test_user_statistics_come_from_profile_details(mock_session):
    """There is no stats endpoint; the numbers live in the profile details."""
    coordinator = _coordinator(mock_session)
    mock_session.get.return_value.__aenter__.return_value = _response(
        json_data={"id": 602086, "regionId": 92, "stats": {"weight": 4706.0, "count": 444}}
    )

    stats = await coordinator.fetch_user_statistics()

    assert stats == {"fetchCount": 444, "fetchWeight": 4706.0}
    assert coordinator.user_id == "602086"


@pytest.mark.asyncio
async def test_bananas_need_the_numeric_user_id(mock_session):
    """The bananas endpoint rejects the "current" alias, so the id is resolved first."""
    coordinator = _coordinator(mock_session)
    mock_session.get.return_value.__aenter__.side_effect = [
        _response(json_data={"id": 602086}),
        _response(json_data={"receivedCount": 2, "givenCount": 1}),
    ]

    bananas = await coordinator.fetch_bananas()

    assert bananas["receivedCount"] == 2
    assert coordinator.user_id == "602086"
    called_url = mock_session.get.call_args[0][0]
    assert called_url.endswith("/api/users/602086/bananas/meta")
