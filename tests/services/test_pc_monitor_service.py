import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.services.pc_monitor_service import PCMonitorService

@pytest.mark.asyncio
@patch("app.services.pc_monitor_service.ping")
@patch("app.services.pc_monitor_service.asyncio.sleep", return_value=None)
async def test_monitor_startup_success(mock_sleep, mock_ping):
    # Setup
    mock_ping.side_effect = [False, False, True] # Online on 3rd attempt
    callback = AsyncMock()
    service = PCMonitorService()
    
    # Run
    await service._poll_pc(12345, callback)
    
    # Assertions
    assert mock_ping.call_count == 3
    callback.assert_called_once_with(12345, "PC is now reachable!")

@pytest.mark.asyncio
@patch("app.services.pc_monitor_service.ping")
@patch("app.services.pc_monitor_service.asyncio.sleep", return_value=None)
async def test_monitor_startup_timeout(mock_sleep, mock_ping):
    # Setup
    mock_ping.return_value = False # Never becomes online
    callback = AsyncMock()
    service = PCMonitorService()
    
    # Run
    await service._poll_pc(12345, callback)
    
    # Assertions
    # max_retries is 30 in the code
    assert mock_ping.call_count == 30
    callback.assert_called_once_with(12345, "PC did not respond after timeout.")

@pytest.mark.asyncio
@patch("app.services.pc_monitor_service.asyncio.create_task")
async def test_monitor_startup_task_creation(mock_create_task):
    service = PCMonitorService()
    callback = AsyncMock()
    
    await service.monitor_startup(123, callback)
    
    # Verify task was created
    mock_create_task.assert_called_once()
    assert 123 in service._monitoring_tasks
    
    # Cleanup task mock to prevent issues
    service._monitoring_tasks[123].done.return_value = False
    
    # Ensure it doesn't create a second task for the same chat
    await service.monitor_startup(123, callback)
    assert mock_create_task.call_count == 1
