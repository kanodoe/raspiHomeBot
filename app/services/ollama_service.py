import subprocess
import os
import asyncio
import httpx
from typing import Optional, Dict, Any, List
from app.core.config import settings
from app.core.logging import logger

class OllamaService:
    _base_url: str = settings.OLLAMA_BASE_URL
    _model: str = settings.OLLAMA_MODEL
    _process: Optional[subprocess.Popen] = None

    @classmethod
    async def is_available(cls) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{cls._base_url}/api/tags", timeout=2.0)
                return response.status_code == 200
        except Exception:
            return False

    @classmethod
    async def start_ollama(cls) -> bool:
        if await cls.is_available():
            logger.info("Ollama is already running.")
            return True

        from urllib.parse import urlparse
        parsed = urlparse(cls._base_url)
        host = parsed.hostname
        # If we are in Linux (Docker) and the target is a localhost, it's likely the Windows host.
        # However, it's safer to always check if we should use SSH to reach the Windows environment.
        is_local = host in ("localhost", "127.0.0.1", "0.0.0.0", None)
        
        try:
            # If on POSIX, we almost always want to start Ollama on the host via SSH 
            # unless the user really installed Ollama inside the Docker container.
            if os.name != 'nt':
                from app.utils.ssh import run_ssh_command
                ssh_host = host if not is_local else settings.PC_IP
                logger.info(f"Attempting to start Ollama on host {ssh_host} via SSH...")
                if await run_ssh_command("ollama serve", ssh_host):
                     # Wait for it to be ready
                     for _ in range(15):
                         await asyncio.sleep(2)
                         if await cls.is_available(): return True
                     return True
                return False

            # On Windows, we try to run 'ollama serve'
            # If it's in PATH, this should work.
            cls._process = subprocess.Popen(
                ["ollama", "serve"],
                shell=True if os.name == 'nt' else False,
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            )
            logger.info(f"Ollama started locally with PID: {cls._process.pid}")

            # Wait for it to be ready
            for _ in range(15): # Wait up to 30 seconds
                await asyncio.sleep(2)
                if await cls.is_available():
                    return True
                if cls._process.poll() is not None:
                    logger.error("Ollama process terminated unexpectedly.")
                    return False
            
            return False
        except Exception as e:
            logger.error(f"Error starting Ollama: {e}")
            return False

    @classmethod
    async def stop_ollama(cls) -> bool:
        if not await cls.is_available():
            logger.info("Ollama is not running.")
            return True

        if cls._process:
            try:
                if os.name == 'nt':
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(cls._process.pid)], capture_output=True)
                else:
                    cls._process.terminate()
                cls._process = None
                logger.info("Ollama stopped (process started by bot).")
                return True
            except Exception as e:
                logger.error(f"Error stopping Ollama process: {e}")
                return False
        else:
            # If we didn't start it, maybe we should try to taskkill by name?
            # But that might be too aggressive if it's the user's tray app.
            logger.warning("Ollama is running but was not started by this bot. Cannot stop it safely.")
            return False

    @classmethod
    async def generate_text(cls, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        url = f"{cls._base_url}/api/generate"
        payload = {
            "model": cls._model,
            "prompt": prompt,
            "stream": False
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=60.0)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response")
                else:
                    logger.error(f"Ollama API Error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Error calling Ollama generate: {e}")
        return None

    @classmethod
    async def suggest_song_details(cls, user_prompt: str) -> Optional[Dict[str, str]]:
        """
        Suggests style and lyrics based on a user prompt.
        Returns a dict with 'style' and 'lyrics'.
        """
        system_prompt = (
            "Eres un experto compositor de canciones y productor musical. "
            "Tu tarea es ayudar al usuario a crear una canción. "
            "Debes responder en formato JSON con dos campos: 'style' (una descripción concisa del estilo musical, instrumentos, tempo, etc.) "
            "y 'lyrics' (la letra de la canción). "
            "Asegúrate de que la letra sea creativa y coherente con el estilo. "
            "Responde ÚNICAMENTE el JSON, sin texto adicional."
        )
        
        prompt = f"Crea una canción basada en el siguiente tema o indicaciones: {user_prompt}"
        
        response_text = await cls.generate_text(prompt, system_prompt)
        if not response_text:
            return None

        # Clean response text in case Ollama adds markdown or extra text
        import json
        import re
        
        try:
            # Try to find JSON block if Ollama ignored "only JSON" instruction
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                json_str = match.group(0)
                data = json.loads(json_str)
                return {
                    "style": data.get("style", "Pop rock"),
                    "lyrics": data.get("lyrics", "")
                }
        except Exception as e:
            logger.error(f"Error parsing Ollama JSON response: {e}. Raw: {response_text}")
            
        # Fallback if JSON parsing fails: return the raw text as style and empty lyrics (user will have to fix it)
        return {
            "style": "Error parseando respuesta de IA",
            "lyrics": response_text
        }
