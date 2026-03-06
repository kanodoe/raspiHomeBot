import pytest
from unittest.mock import patch, MagicMock
from app.services.wol_service import WOLService

@patch("app.services.wol_service.send_magic_packet")
def test_send_wol_success(mock_send):
    # Setup
    result = WOLService.send_wol()
    
    # Assertions
    assert result is True
    mock_send.assert_called_once()

@patch("app.services.wol_service.send_magic_packet")
def test_send_wol_failure(mock_send):
    # Setup
    mock_send.side_effect = Exception("Broadcast failed")
    result = WOLService.send_wol()
    
    # Assertions
    assert result is False

@pytest.mark.asyncio
@patch("app.services.wol_service.ping")
async def test_get_pc_status_online(mock_ping):
    mock_ping.return_value = True
    status = await WOLService.get_pc_status()
    assert status == "online"

@pytest.mark.asyncio
@patch("app.services.wol_service.ping")
async def test_get_pc_status_offline(mock_ping):
    mock_ping.return_value = False
    status = await WOLService.get_pc_status()
    assert status == "offline"

@pytest.mark.asyncio
@patch("app.services.wol_service.shutdown_pc")
async def test_shutdown_call(mock_shutdown):
    mock_shutdown.return_value = (True, "Shutdown signal sent")
    result = await WOLService.shutdown()
    assert result == (True, "Shutdown signal sent")
    mock_shutdown.assert_called_once()
