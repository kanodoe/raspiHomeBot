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

    @classmethod
    def get_base_url(cls) -> str:
        """
        Dynamically returns the base URL for the ACE-Step API.
        If we are in Docker (os.name != 'nt') and the host is set to local,
        we fallback to settings.PC_IP for reaching the host.
        """
        host = settings.ACESTEP_HOST
        if os.name != 'nt' and host in ("localhost", "127.0.0.1", "0.0.0.0"):
            host = settings.PC_IP
        return f"http://{host}:{settings.ACESTEP_PORT}"

    @classmethod
    async def start_api(cls) -> bool:
        if await cls.is_api_ready():
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
        # In Docker (POSIX), localhost/127.0.0.1 is the container itself.
        # If it's a Windows path and we are on POSIX, we MUST use SSH to talk to the host.
        use_ssh = os.name != 'nt' and is_windows_path

        if use_ssh:
            # If host is localhost/127.0.0.1 on POSIX, it should probably be host.docker.internal 
            # or the PC_IP to reach the host from Docker.
            ssh_host = settings.ACESTEP_HOST
            if ssh_host in ("localhost", "127.0.0.1", "0.0.0.0"):
                ssh_host = settings.PC_IP # Fallback to PC_IP if host is set to local on Docker
            
            from app.utils.ssh import run_ssh_command
            logger.info(f"Attempting to start ACE-Step remotely on {ssh_host} via SSH (Windows path on {os.name})...")
            # We use powershell Start-Process to launch it in background and return immediately
            # Using absolute path for bat if possible and ensuring .\\ is used
            cmd = f'powershell -Command "Start-Process -FilePath \'cmd.exe\' -ArgumentList \'/c set CHECK_UPDATE=false && .\\{bat_name}\' -WorkingDirectory \'{ace_path_str}\' -WindowStyle Hidden"'
            if await run_ssh_command(cmd, ssh_host):
                # Wait for it to be ready
                logger.info("SSH command sent. Waiting up to 60s for API to be ready...")
                for i in range(30):
                    await asyncio.sleep(2)
                    if await cls.is_api_ready(): 
                        logger.info(f"ACE-Step API is ready (via SSH) after {i*2}s.")
                        return True
                logger.warning("ACE-Step API started via SSH but is not responding yet (timed out after 60s).")
                return False
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
            return False
        except Exception as e:
            logger.error(f"Error starting ACE-Step API: {e}")
            return False

    @classmethod
    async def stop_api(cls) -> bool:
        # Check if we should use SSH to stop
        is_windows_path = ":" in settings.ACESTEP_PATH or settings.ACESTEP_PATH.startswith("\\")
        use_ssh = os.name != 'nt' and is_windows_path
        
        if use_ssh:
            from app.utils.ssh import run_ssh_command
            ssh_host = settings.ACESTEP_HOST
            if ssh_host in ("localhost", "127.0.0.1", "0.0.0.0"):
                ssh_host = settings.PC_IP
            
            logger.info(f"Attempting to stop ACE-Step remotely on {ssh_host} via SSH...")
            # Kill by port 8001
            cmd = f'powershell -Command "Get-NetTCPConnection -LocalPort {settings.ACESTEP_PORT} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object {{ TaskKill /F /PID $_ /T }}"'
            await run_ssh_command(cmd, ssh_host)
            # Wait a bit
            await asyncio.sleep(2)
            return not await cls.is_api_ready()

        if not cls._process or cls._process.poll() is not None:
            # If not started by us, try to kill by port locally if on Windows
            if os.name == 'nt':
                try:
                    cmd = f'powershell -Command "Get-NetTCPConnection -LocalPort {settings.ACESTEP_PORT} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object {{ TaskKill /F /PID $_ /T }}"'
                    subprocess.run(cmd, shell=True, capture_output=True)
                    await asyncio.sleep(2)
                    return not await cls.is_api_ready()
                except:
                    pass
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
        base_url = cls.get_base_url()
        # Try a few endpoints that might be available
        for endpoint in ["/docs", "/"]:
            url = f"{base_url}{endpoint}"
            try:
                async with httpx.AsyncClient() as client:
                    # Probing the API. If we get any response, it's listening.
                    response = await client.get(url, timeout=3.0)
                    return True
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                logger.debug(f"ACE-Step API not ready at {url}: {type(e).__name__}")
            except Exception as e:
                # Other errors like 405 Method Not Allowed or 404 Not Found 
                # still mean the server is there.
                logger.debug(f"ACE-Step API responded with error at {url} (but it is listening): {e}")
                return True
        return False

    @classmethod
    async def generate_song(cls, prompt: str, lyrics: str = "") -> Optional[str]:
        """
        Submits a task and returns the task_id
        """
        url = f"{cls.get_base_url()}/release_task"
        # ACE-Step 1.5 supports more parameters. 
        # For text2music, it often uses 'prompt' as the style/description.
        payload = {
            "prompt": prompt,
            "lyrics": lyrics,
            "thinking": True,
            "use_format": True,
            "task_type": "text2music",
            "gpt_description_prompt": prompt # Sometimes needed alongside prompt
        }
        try:
            async with httpx.AsyncClient() as client:
                logger.debug(f"Calling ACE-Step API: {url} with payload keys {list(payload.keys())}")
                response = await client.post(url, json=payload, timeout=30.0)
                if response.status_code == 200:
                    data = response.json()
                    # ACE-Step wraps response: {"code": 200, "data": {"task_id": "...", ...}}
                    task_id = data.get("data", {}).get("task_id")
                    if task_id:
                        return task_id
                    logger.error(f"ACE-Step API response missing task_id: {data}")
                else:
                    logger.error(f"ACE-Step API Error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Exception in generate_song calling {url}: {type(e).__name__}: {str(e)}")
        return None

    @classmethod
    async def get_task_status(cls, task_id: str) -> Optional[Dict[str, Any]]:
        url = f"{cls.get_base_url()}/query_result"
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
            logger.error(f"Error querying task status at {url}: {e}")
        return None

    @classmethod
    async def download_audio(cls, audio_path: str) -> Optional[bytes]:
        url = f"{cls.get_base_url()}/v1/audio"
        params = {"path": audio_path}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=30.0)
                if response.status_code == 200:
                    return response.content
        except Exception as e:
            logger.error(f"Error downloading audio from {url}: {e}")
        return None
