import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.acestep_service import AceStepService
import httpx

@pytest.mark.asyncio
async def test_get_base_url():
    # Test that it constructs the URL correctly from settings
    with patch("app.services.acestep_service.settings") as mock_settings:
        mock_settings.ACESTEP_HOST = "192.168.1.10"
        mock_settings.ACESTEP_PORT = 8001
        
        url = AceStepService.get_base_url()
        assert url == "http://192.168.1.10:8001"

@pytest.mark.asyncio
async def test_is_api_ready_success():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        
        ready = await AceStepService.is_api_ready()
        assert ready is True

@pytest.mark.asyncio
async def test_generate_song_success():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200, 
            json=lambda: {"code": 200, "data": {"task_id": "test_task_123"}}
        )
        
        task_id = await AceStepService.generate_song("Pop style", "Hello world", language="German")
        assert task_id == "test_task_123"
        
        # Verify language was sent in payload
        args, kwargs = mock_post.call_args
        payload = kwargs.get("json")
        assert payload["language"] == "German"
        assert payload["prompt"] == "Pop style"
        assert payload["lyrics"] == "Hello world"

@pytest.mark.asyncio
async def test_get_task_status_completed():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # Mocking the complex response structure of ACE-Step
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "code": 200,
                "data": [{
                    "status": 1, # Normalizes to 'completed'
                    "audio_path": "C:\\path\\to\\audio.mp3"
                }]
            }
        )
        
        status = await AceStepService.get_task_status("test_task_123")
        assert status["status"] == "completed"
        assert status["audio_path"] == "C:\\path\\to\\audio.mp3"

@pytest.mark.asyncio
async def test_download_audio():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(status_code=200, content=b"audio data")
        
        content = await AceStepService.download_audio("remote/path.mp3")
        assert content == b"audio data"
