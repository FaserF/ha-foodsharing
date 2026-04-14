
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import aiohttp
from custom_components.foodsharing.config_flow import validate_credentials
from custom_components.foodsharing.coordinator import FoodsharingCoordinator

@pytest.mark.asyncio
async def test_full_authentication_flow():
    """Test the full authentication flow including 2FA challenge and session recovery."""
    
    email = "test@example.com"
    password = "password123"
    totp = "123456"
    
    with patch("custom_components.foodsharing.config_flow.async_get_clientsession") as mock_session_getter:
        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session_getter.return_value = mock_session
        hass = MagicMock()
        
        # 1. Test Initial Login (Triggering 2FA)
        mock_resp_2fa = AsyncMock()
        mock_resp_2fa.status = 403
        mock_resp_2fa.json.return_value = {"code": "2fa_required", "message": "2FA required"}
        
        mock_resp_login_page = AsyncMock()
        mock_resp_login_page.status = 200
        mock_resp_login_page.text.return_value = "login page"
        
        mock_session.get.return_value.__aenter__.return_value = mock_resp_login_page
        mock_session.post.return_value.__aenter__.return_value = mock_resp_2fa
        
        res = await validate_credentials(hass, email, password)
        assert res == {"2fa_required": True}
        
        # 2. Test TOTP Verification
        mock_resp_success = AsyncMock()
        mock_resp_success.status = 200
        mock_resp_success.json.return_value = {"id": 123}
        mock_session.post.return_value.__aenter__.return_value = mock_resp_success
        
        # Mocking the ID from /api/users/current after success
        mock_resp_current = AsyncMock()
        mock_resp_current.status = 200
        mock_resp_current.json.return_value = {"id": 123}
        mock_session.get.return_value.__aenter__.return_value = mock_resp_current
        
        res_totp = await validate_credentials(hass, email, password, totp=totp)
        assert res_totp == "123"
        
        # 3. Test Coordinator Session Recovery
        coordinator = FoodsharingCoordinator(hass, email, password)
        coordinator.session = mock_session
        
        login_ok = await coordinator.login()
        assert login_ok is True
        assert coordinator.user_id == "123"

@pytest.mark.asyncio
async def test_coordinator_reauth_recovery():
    """Test coordinator handles 401 and recovers via login."""
    hass = MagicMock()
    email = "test@example.com"
    password = "password123"
    
    coordinator = FoodsharingCoordinator(hass, email, password)
    
    with patch.object(coordinator, "login", return_value=True) as mock_login:
        mock_session = MagicMock(spec=aiohttp.ClientSession)
        coordinator.session = mock_session
        
        mock_resp_fail = AsyncMock()
        mock_resp_fail.status = 401
        
        mock_resp_ok = AsyncMock()
        mock_resp_ok.status = 200
        mock_resp_ok.json.return_value = []
        
        # Simulate 401 on first call (for all parallel tasks), success on second after login
        # asyncio.gather will call session.get multiple times. 
        # We need enough responses to satisfy the first gather (4 calls) and then the second gather (4 calls).
        mock_session.get.return_value.__aenter__.side_effect = [
            mock_resp_fail, mock_resp_fail, mock_resp_fail, mock_resp_fail,  # First gather
            mock_resp_ok, mock_resp_ok, mock_resp_ok, mock_resp_ok           # Second gather
        ]
        
        # This will call _fetch_all_data, which will encounter 401 and trigger login()
        await coordinator._async_update_data()
        
        assert mock_login.called
        assert mock_login.call_count == 1
