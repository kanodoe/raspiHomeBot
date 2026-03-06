import pytest
from unittest.mock import patch
from app.services.gate_service import GateService

@pytest.mark.asyncio
@patch("app.services.gate_service.asyncio.sleep", return_value=None)
async def test_open_gate_success(mock_sleep):
    result = await GateService.open_gate()
    assert result is True
    mock_sleep.assert_called_once()
