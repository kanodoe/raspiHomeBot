import asyncio
import os
import subprocess
import httpx
from pathlib import Path
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

        # Prepare the path for the bat file
        bat_name = "start_api_server.bat"
        if os.name != 'nt' and (":" in settings.ACESTEP_PATH or settings.ACESTEP_PATH.startswith("\\")):
            # Construct Windows path string on POSIX
            path_cleaned = settings.ACESTEP_PATH.rstrip("/\\")
            bat_path_str = f"{path_cleaned}\\{bat_name}".replace("/", "\\")
            ace_path_str = path_cleaned.replace("/", "\\")
        else:
            ace_path = Path(settings.ACESTEP_PATH)
            bat_path = ace_path / bat_name
            bat_path_str = str(bat_path)
            ace_path_str = str(ace_path)
        
        # Check if we should try to run this locally or via SSH
        is_windows_path = ":" in settings.ACESTEP_PATH or settings.ACESTEP_PATH.startswith("\\")
        is_local = settings.ACESTEP_HOST in ("localhost", "127.0.0.1", "0.0.0.0")

        if os.name != 'nt' and is_windows_path:
            if not is_local:
                from app.utils.ssh import run_ssh_command
                logger.info(f"Attempting to start ACE-Step remotely on {settings.ACESTEP_HOST} via SSH...")
                # Start in background if possible, but cmd /c might be enough if it returns
                cmd = f'cmd /c "cd /d {ace_path_str} && set CHECK_UPDATE=false && {bat_name}"'
                if await run_ssh_command(cmd, settings.ACESTEP_HOST):
                    # Wait for it to be ready
                    for _ in range(15):
                        await asyncio.sleep(2)
                        if await cls.is_api_ready(): return True
                    return True
                return False
            else:
                logger.error(f"Cannot run Windows path '{settings.ACESTEP_PATH}' on {os.name} locally. Use a remote ACESTEP_HOST or run the bot on the host.")
                return False

        if not Path(bat_path_str).exists() and os.name == 'nt':
            logger.error(f"ACE-Step bat file not found at: {bat_path_str}")
            return False

        try:
            env = os.environ.copy()
            env["CHECK_UPDATE"] = "false"

            # shell=True es necesario para .bat en Windows
            cls._process = subprocess.Popen(
                [bat_path_str],
                cwd=ace_path_str,
                shell=True,
                env=env,
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            )
            logger.info(f"ACE-Step API started locally with PID: {cls._process.pid}")
            
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
