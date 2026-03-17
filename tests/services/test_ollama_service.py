import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.ollama_service import OllamaService

@pytest.mark.asyncio
async def test_is_available():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        
        available = await OllamaService.is_available()
        assert available is True

@pytest.mark.asyncio
async def test_generate_text():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200, 
            json=lambda: {"response": "This is generated text"}
        )
        
        text = await OllamaService.generate_text("Hello")
        assert text == "This is generated text"

@pytest.mark.asyncio
async def test_suggest_song_details():
    with patch("app.services.ollama_service.OllamaService.generate_text", new_callable=AsyncMock) as mock_gen:
        # Mocking the LLM's raw response in JSON format (per prompts expectations)
        mock_gen.return_value = '{"style": "happy pop", "lyrics": "hello world", "summary": "A happy song"}'
        
        details = await OllamaService.suggest_song_details("Write a happy song")
        assert details["style"] == "happy pop"
        assert details["lyrics"] == "hello world"
        assert details["summary"] == "A happy song"

@pytest.mark.asyncio
async def test_suggest_random_song():
    with patch("app.services.ollama_service.OllamaService.generate_text", new_callable=AsyncMock) as mock_gen:
        # Mocking the LLM's raw response in JSON format
        mock_gen.return_value = '{"style": "rock", "lyrics": "rock n roll", "summary": "A rock song"}'
        
        details = await OllamaService.suggest_random_song()
        assert details["style"] == "rock"
        assert details["lyrics"] == "rock n roll"
        assert details["summary"] == "A rock song"

@pytest.mark.asyncio
async def test_start_ollama_already_running():
    with patch("app.services.ollama_service.OllamaService.is_available", new_callable=AsyncMock) as mock_avail:
        mock_avail.return_value = True
        
        success, error = await OllamaService.start_ollama()
        assert success is True
        assert error is None
