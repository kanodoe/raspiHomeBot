import pytest
import httpx
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.plex_music_service import PlexMusicService

@pytest.mark.asyncio
async def test_process_generated_song_skip_if_not_configured():
    # Test that it skips if PLEX_URL is not set
    with patch("app.services.plex_music_service.settings") as mock_settings:
        mock_settings.PLEX_URL = None
        mock_settings.PLEX_TOKEN = "token"
        
        # We check if it returns early without calling run_ssh_command
        with patch("app.services.plex_music_service.run_ssh_command", new_callable=AsyncMock) as mock_ssh:
            await PlexMusicService.process_generated_song(
                task_id="test_task",
                audio_path_on_remote="C:\\path.mp3",
                metadata={},
                user_info={"prompt": "Jazz", "display_name": "TestUser"}
            )
            mock_ssh.assert_not_called()

@pytest.mark.asyncio
async def test_process_generated_song_success():
    # Test successful copy, tagging and notification
    with patch("app.services.plex_music_service.settings") as mock_settings:
        mock_settings.PLEX_URL = "http://plex:32400"
        mock_settings.PLEX_TOKEN = "test_token"
        mock_settings.PLEX_REMOTE_MUSIC_PATH = "E:\\Music"
        mock_settings.ACESTEP_HOST = "192.168.1.10"
        mock_settings.PLEX_MUSIC_SECTION_ID = "1"
        
        task_id = "task123"
        prompt = "Smooth Jazz, 120 BPM, Saxophone"
        user_info = {"prompt": prompt, "display_name": "Juan Pérez", "username": "juanp"}
        language = "Spanish"
        
        with patch("app.services.plex_music_service.run_ssh_command", new_callable=AsyncMock) as mock_ssh, \
             patch("app.services.plex_music_service.PlexMusicService.notify_plex_scan", new_callable=AsyncMock) as mock_notify:
            
            mock_ssh.return_value = True
            
            await PlexMusicService.process_generated_song(
                task_id=task_id,
                audio_path_on_remote="C:\\temp\\audio.mp3",
                metadata={},
                user_info=user_info,
                language=language
            )
            
            # Verify SSH command contains expected elements
            args, kwargs = mock_ssh.call_args
            command = args[0]
            host = args[1]
            
            # Since it's now base64 encoded, we decode to verify content
            import base64
            encoded = command.split(" ")[-1]
            decoded = base64.b64decode(encoded).decode('utf-16-le')
            
            assert "Smooth Jazz" in decoded
            assert "120 BPM" in decoded
            assert "Spanish" in decoded
            assert "Juan Pérez" in decoded
            assert "RaspiValSong" in decoded
            assert host == "192.168.1.10"
            
            mock_notify.assert_called_once()

@pytest.mark.asyncio
async def test_notify_plex_scan_success():
    # Test successful Plex API call
    with patch("app.services.plex_music_service.settings") as mock_settings:
        mock_settings.PLEX_URL = "http://plex:32400"
        mock_settings.PLEX_TOKEN = "test_token"
        mock_settings.PLEX_MUSIC_SECTION_ID = "5"
        
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            
            await PlexMusicService.notify_plex_scan()
            
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            url = args[0]
            params = kwargs.get("params", {})
            
            assert "/library/sections/5/refresh" in url
            assert params.get("X-Plex-Token") == "test_token"

@pytest.mark.asyncio
async def test_notify_plex_scan_failure():
    # Test Plex API call failure (logs error but doesn't crash)
    with patch("app.services.plex_music_service.settings") as mock_settings:
        mock_settings.PLEX_URL = "http://plex:32400"
        mock_settings.PLEX_TOKEN = "test_token"
        mock_settings.PLEX_MUSIC_SECTION_ID = "5"
        
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(status_code=500, text="Internal Server Error")
            
            # Should not raise exception
            await PlexMusicService.notify_plex_scan()
            mock_get.assert_called_once()
