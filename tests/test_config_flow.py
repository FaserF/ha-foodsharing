import pytest


# Removed importorskip to surface error
from custom_components.foodsharing.config_flow import FoodsharingConfigFlow


async def test_config_flow_init() -> None:
    """Test flow init."""
    flow = FoodsharingConfigFlow()
    assert flow.VERSION == 3
