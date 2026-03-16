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
    async def is_port_listening_remotely(cls, host: str, port: int) -> bool:
        """
        Check via SSH if the port is listening on the remote host.
        """
        from app.utils.ssh import run_ssh_command
        # Netstat command that returns exit code 0 if found, 1 otherwise
        cmd = f'powershell -Command "netstat -ano | findstr LISTENING | findstr :{port}"'
        return await run_ssh_command(cmd, host)

    @classmethod
    async def is_available(cls) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{cls._base_url}/api/tags", timeout=2.0)
                return response.status_code == 200
        except Exception:
            # Diagnostics for remote host if we are in Docker
            from urllib.parse import urlparse
            try:
                parsed = urlparse(cls._base_url)
                host = parsed.hostname
                port = parsed.port or 11434
                is_local = host in ("localhost", "127.0.0.1", "0.0.0.0", None)
                
                if os.name != 'nt' and not is_local:
                    ssh_host = host if host else settings.PC_IP
                    if await cls.is_port_listening_remotely(ssh_host, port):
                        logger.warning(f"Ollama IS LISTENING on remote host {ssh_host}:{port} via SSH, but is NOT REACHABLE via HTTP from this container. "
                                       "This usually means it's bound to 127.0.0.1. Set OLLAMA_HOST=0.0.0.0 on Windows.")
            except:
                pass
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
                
                # Check if port is in use but not responding (binding issue)
                if await cls.is_port_listening_remotely(ssh_host, 11434):
                     logger.info(f"Ollama port 11434 is in use on {ssh_host} but not responding to HTTP. Stopping it for a clean start with 0.0.0.0 binding...")
                     await cls.stop_ollama()

                logger.info(f"Attempting to start Ollama on host {ssh_host} via SSH...")
                # We use powershell to set OLLAMA_HOST before starting
                cmd = f'powershell -Command "$env:OLLAMA_HOST = \'0.0.0.0\'; Start-Process -FilePath \'ollama\' -ArgumentList \'serve\' -WindowStyle Hidden"'
                if await run_ssh_command(cmd, ssh_host):
                     # Wait for it to be ready
                     for _ in range(15):
                         await asyncio.sleep(2)
                         if await cls.is_available(): 
                             logger.info("Ollama is ready (via SSH).")
                             return True
                     logger.warning("Ollama started via SSH but is not responding yet.")
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
        from urllib.parse import urlparse
        parsed = urlparse(cls._base_url)
        host = parsed.hostname
        is_local = host in ("localhost", "127.0.0.1", "0.0.0.0", None)
        
        if os.name != 'nt':
            from app.utils.ssh import run_ssh_command
            ssh_host = host if not is_local else settings.PC_IP
            logger.info(f"Attempting to stop Ollama on host {ssh_host} via SSH...")
            # Kill by image name or port if possible
            cmd = 'powershell -Command "Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force; Get-NetTCPConnection -LocalPort 11434 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }"'
            await run_ssh_command(cmd, ssh_host)
            await asyncio.sleep(2)
            return not await cls.is_available()

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
            # Try to kill by name if on Windows locally
            if os.name == 'nt':
                subprocess.run(["taskkill", "/F", "/IM", "ollama.exe", "/T"], capture_output=True)
                await asyncio.sleep(2)
                return not await cls.is_available()
            
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
