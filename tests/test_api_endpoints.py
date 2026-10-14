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


@pytest.mark.asyncio
async def test_unread_conversations_keep_their_content(mock_session):
    """The conversation list already carries the latest message and the authors."""
    coordinator = _coordinator(mock_session)
    coordinator._is_first_update = True
    mock_session.get.return_value.__aenter__.return_value = _response(
        json_data={
            "conversations": [
                {
                    "id": 1070602,
                    "title": "Team Wochenmarkt",
                    "unreadMessages": 1,
                    "lastMessage": {
                        "id": 42,
                        "authorId": 988336,
                        "body": "Kann jemand die morgige Rettung uebernehmen?",
                        "sentAt": "2026-09-16T04:23:36Z",
                    },
                },
                {"id": 2, "unreadMessages": 0, "lastMessage": {"id": 43}},
            ],
            "profiles": [{"id": 988336, "name": "Nina"}],
        }
    )

    assert await coordinator.fetch_unread_messages() == 1
    assert len(coordinator.unread_conversations) == 1
    conv = coordinator.unread_conversations[0]
    assert conv["title"] == "Team Wochenmarkt"
    assert conv["author"] == "Nina"
    assert conv["body"].startswith("Kann jemand")
    assert conv["sent_at"] == "2026-09-16T04:23:36Z"


@pytest.mark.asyncio
async def test_long_message_bodies_are_truncated(mock_session):
    """Bodies end up in the recorder, so they are capped."""
    coordinator = _coordinator(mock_session)
    mock_session.get.return_value.__aenter__.return_value = _response(
        json_data={
            "conversations": [
                {"id": 1, "unreadMessages": 1, "lastMessage": {"id": 1, "body": "x" * 900}}
            ],
            "profiles": [],
        }
    )

    await coordinator.fetch_unread_messages()
    body = coordinator.unread_conversations[0]["body"]
    assert len(body) == 501
    assert body.endswith("…")


@pytest.mark.asyncio
async def test_bell_content_is_kept_with_absolute_url(mock_session):
    """Bell titles are translation keys; the readable parts live in the payload."""
    coordinator = _coordinator(mock_session)
    mock_session.get.return_value.__aenter__.return_value = _response(
        json_data=[
            {
                "id": 1,
                "isRead": False,
                "key": "store_wall_post.many",
                "title": "store_wall_post_title",
                "href": "/store/45835",
                "payload": {"name": "Fairteiler Kuecknitz", "user": "Patrick", "count": 5},
                "createdAt": "2026-09-15T19:46:18Z",
                "icon": "fas fa-thumbtack",
            },
            {"id": 2, "isRead": True, "key": "other", "href": "/store/1"},
        ]
    )

    assert await coordinator.fetch_bells() == 1
    bell = coordinator.unread_bells[0]
    assert bell["key"] == "store_wall_post.many"
    assert bell["payload"]["user"] == "Patrick"
    assert bell["url"] == "https://foodsharing.de/store/45835"
    assert bell["created_at"] == "2026-09-15T19:46:18Z"
