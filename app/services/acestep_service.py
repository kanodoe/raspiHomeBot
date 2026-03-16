import asyncio
import os
import subprocess
import httpx
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.logging import logger

class AceStepService:
    _process: Optional[subprocess.Popen] = None
    _base_url: str = f"http://{settings.ACESTEP_HOST}:{settings.ACESTEP_PORT}"

    @classmethod
    async def start_api(cls) -> bool:
        if cls._process and cls._process.poll() is None:
            logger.info("ACE-Step API is already running.")
            return True

        bat_path = os.path.join(settings.ACESTEP_PATH, "start_api_server.bat")
        if not os.path.exists(bat_path):
            logger.error(f"ACE-Step bat file not found at: {bat_path}")
            return False

        try:
            # We use creationflags to run it in a new console window or detached if needed
            # For now, let's just run it. shell=True is needed for .bat
            cls._process = subprocess.Popen(
                [bat_path],
                cwd=settings.ACESTEP_PATH,
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            logger.info(f"ACE-Step API started with PID: {cls._process.pid}")
            
            # Wait for the API to be ready
            for _ in range(30): # Wait up to 30 seconds
                await asyncio.sleep(2)
                if await cls.is_api_ready():
                    return True
                if cls._process.poll() is not None:
                    logger.error("ACE-Step API process terminated unexpectedly.")
                    return False
            
            logger.warning("ACE-Step API started but health check failed after 60s.")
            return True # Assume it might still be loading
        except Exception as e:
            logger.error(f"Error starting ACE-Step API: {e}")
            return False

    @classmethod
    async def stop_api(cls) -> bool:
        if not cls._process or cls._process.poll() is not None:
            # Try to kill any leftover processes if possible, but mainly we want to stop what we started
            # ACE-Step might have multiple processes (uv run -> python)
            # A better way might be to find the process using the port
            logger.info("ACE-Step API is not running.")
            return True

        try:
            # On Windows, killing the shell process might not kill children.
            # Taskkill is more reliable for process trees
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(cls._process.pid)], capture_output=True)
            cls._process = None
            logger.info("ACE-Step API stopped.")
            return True
        except Exception as e:
            logger.error(f"Error stopping ACE-Step API: {e}")
            return False

    @classmethod
    async def is_api_ready(cls) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{cls._base_url}/docs", timeout=1.0)
                return response.status_code == 200
        except Exception:
            return False

    @classmethod
    async def generate_song(cls, prompt: str, lyrics: str = "") -> Optional[str]:
        """
        Submits a task and returns the task_id
        """
        url = f"{cls._base_url}/release_task"
        payload = {
            "prompt": prompt,
            "lyrics": lyrics,
            "thinking": True,
            "use_format": True,
            "task_type": "text2music"
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    # ACE-Step wraps response: {"code": 200, "data": {"task_id": "...", ...}}
                    return data.get("data", {}).get("task_id")
                else:
                    logger.error(f"API Error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Error calling generate_song: {e}")
        return None

    @classmethod
    async def get_task_status(cls, task_id: str) -> Optional[Dict[str, Any]]:
        url = f"{cls._base_url}/query_result"
        payload = {"task_id_list": f'["{task_id}"]'}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("data", [])
                    if results:
                        return results[0]
        except Exception as e:
            logger.error(f"Error querying task status: {e}")
        return None

    @classmethod
    async def download_audio(cls, audio_path: str) -> Optional[bytes]:
        url = f"{cls._base_url}/v1/audio"
        params = {"path": audio_path}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30.0)
                if response.status_code == 200:
                    return response.content
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
        return None
