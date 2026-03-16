import subprocess
import os
import asyncio
import httpx
from typing import Optional, Dict, Any, List, Tuple
from app.core.config import settings
from app.core.logging import logger

class OllamaService:
    _base_url: str = settings.OLLAMA_BASE_URL
    _model: str = settings.OLLAMA_MODEL
    _process: Optional[subprocess.Popen] = None
    _last_error: Optional[str] = None  # e.g. "model_not_found" for 404 model not found

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
    async def start_ollama(cls) -> Tuple[bool, Optional[str]]:
        """
        Start Ollama. Returns (success, error_message).
        If the port is already in use on the remote host, we do NOT kill the process;
        we return False with a message asking the user to set OLLAMA_HOST=0.0.0.0.
        """
        if await cls.is_available():
            logger.info("Ollama is already running.")
            return True, None

        from urllib.parse import urlparse
        parsed = urlparse(cls._base_url)
        host = parsed.hostname
        # If we are in Linux (Docker) and the target is a localhost, it's likely the Windows host.
        is_local = host in ("localhost", "127.0.0.1", "0.0.0.0", None)
        
        try:
            # If on POSIX, we almost always want to start Ollama on the host via SSH
            if os.name != 'nt':
                from app.utils.ssh import run_ssh_command
                ssh_host = host if not is_local else settings.PC_IP
                
                # If port is already in use, do NOT kill the process. Ollama may be running with 127.0.0.1.
                if await cls.is_port_listening_remotely(ssh_host, 11434):
                    msg = (
                        f"Ollama parece estar en ejecución en el equipo remoto ({ssh_host}:11434) pero no es accesible desde aquí. "
                        "Configura OLLAMA_HOST=0.0.0.0 antes de iniciar Ollama y permite el puerto 11434 en el firewall de Windows."
                    )
                    logger.warning(msg)
                    return False, msg

                logger.info(f"Attempting to start Ollama on host {ssh_host} via SSH...")
                # Set OLLAMA_HOST in the same session so the child process inherits it
                cmd = 'powershell -Command "$env:OLLAMA_HOST = \'0.0.0.0\'; Start-Process -FilePath \'ollama\' -ArgumentList \'serve\' -WindowStyle Hidden"'
                if await run_ssh_command(cmd, ssh_host):
                    # Wait for it to be ready (up to 30s)
                    for _ in range(15):
                        await asyncio.sleep(2)
                        if await cls.is_available():
                            logger.info("Ollama is ready (via SSH).")
                            return True, None
                    logger.warning("Ollama started via SSH but is not responding yet.")
                    return False, "Ollama se inició por SSH pero no respondió a tiempo. Comprueba que OLLAMA_HOST=0.0.0.0 y el firewall."
                return False, "No se pudo ejecutar el comando SSH para iniciar Ollama. Revisa la conexión y las credenciales."

            # On Windows, we try to run 'ollama serve'
            cls._process = subprocess.Popen(
                ["ollama", "serve"],
                shell=True if os.name == 'nt' else False,
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            )
            logger.info(f"Ollama started locally with PID: {cls._process.pid}")

            for _ in range(15):
                await asyncio.sleep(2)
                if await cls.is_available():
                    return True, None
                if cls._process.poll() is not None:
                    logger.error("Ollama process terminated unexpectedly.")
                    return False, "El proceso de Ollama terminó inesperadamente."
            return False, "Ollama se inició pero no respondió a tiempo."
        except Exception as e:
            logger.error(f"Error starting Ollama: {e}")
            return False, f"Error al iniciar Ollama: {e}"

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
        cls._last_error = None
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
                if response.status_code == 404:
                    try:
                        body = response.json()
                        err = body.get("error", "")
                        if "not found" in err.lower():
                            cls._last_error = "model_not_found"
                            logger.error(f"Ollama model '{cls._model}' not found. Available models: ollama list. Set OLLAMA_MODEL in .env or run 'ollama pull {cls._model}' on the Ollama host.")
                            return None
                    except Exception:
                        pass
                logger.error(f"Ollama API Error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Error calling Ollama generate: {e}")
        return None

    @classmethod
    async def suggest_song_details(
        cls,
        user_prompt: str,
        refinamiento: Optional[str] = None,
        language_code: Optional[str] = None,
        style_only: bool = False,
    ) -> Optional[Dict[str, str]]:
        """
        Suggests style and lyrics based on a user prompt (ACE-Step compatible format).
        Style/tags are always in English; lyrics in the requested language (or empty if style_only).
        Returns a dict with 'style' and 'lyrics'.
        """
        from app.prompts import (
            SYSTEM_PROMPT_STYLE_LYRICS,
            SYSTEM_PROMPT_STYLE_ONLY,
            build_user_prompt,
            get_language_name,
            get_system_prompt_style_lyrics,
            parse_style_lyrics_response,
        )

        if style_only:
            system = SYSTEM_PROMPT_STYLE_ONLY
            prompt = build_user_prompt(user_prompt, refinamiento, style_only=True)
        elif language_code:
            lang_name = get_language_name(language_code)
            system = get_system_prompt_style_lyrics(lang_name)
            prompt = build_user_prompt(user_prompt, refinamiento, language_name=lang_name, style_only=False)
        else:
            system = SYSTEM_PROMPT_STYLE_LYRICS
            prompt = build_user_prompt(user_prompt, refinamiento)

        response_text = await cls.generate_text(prompt, system)
        if not response_text:
            if cls._last_error == "model_not_found":
                return {
                    "style": "",
                    "lyrics": "",
                    "error": "model_not_found",
                    "message": (
                        f"El modelo '{cls._model}' no está instalado en Ollama. "
                        f"En el equipo donde corre Ollama ejecuta: ollama pull {cls._model} "
                        f"o cambia OLLAMA_MODEL en .env por un modelo que ya tengas (ej: llama3.2, mistral)."
                    ),
                }
            return None

        result = parse_style_lyrics_response(response_text)
        if "Error parseando" in result.get("style", ""):
            logger.error(f"Error parsing LLM response. Raw: {response_text[:500]}")
        return result
