import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # From .env — token del bot (obligatorio si no se usan tokens por modo)
    BOT_TOKEN: Optional[str] = None
    # Tokens por modo cuando se usan varios bots: cada proceso usa el suyo según BOT_MODE
    BOT_TOKEN_ADMIN: Optional[str] = None
    BOT_TOKEN_SONGS: Optional[str] = None
    BOT_TOKEN_GATE: Optional[str] = None
    # Secreto para cifrar enlaces de invitación (si no se define, se usa el token del admin)
    INVITE_LINK_SECRET: Optional[str] = None
    # Proxy del portón: URL a la que este bot envía la orden de abrir cuando un invitado usa /gate_open
    # (el otro bot o servicio debe exponer un endpoint que acepte POST con GATE_PROXY_SECRET y opcionalmente guest_id)
    GATE_PROXY_URL: Optional[str] = None
    GATE_PROXY_SECRET: Optional[str] = None
    PC_MAC: str
    PC_IP: str
    SSH_USER: str
    SSH_KEY_PATH: str
    ADMIN_TELEGRAM_ID: int
    DATABASE_URL: str = "sqlite+aiosqlite:///./home_automation.db"

    # ACE-Step Settings
    ACESTEP_PATH: str = r"C:\path\to\ACE-Step-1.5"
    ACESTEP_HOST: str = "127.0.0.1"
    ACESTEP_PORT: int = 8001
    ACESTEP_SAVE_PATH: str = r"C:\telegram_songs"
    # If set, run this .bat on the remote host as-is (no copy from start_api_server.bat). E.g. start_api_server_docker_remote.bat
    ACESTEP_REMOTE_BAT: str = ""

    # Ollama Settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3" # Default to llama3, user can change in .env
    
    # Enabled Modules (comma-separated list)
    ENABLED_MODULES: str = "pc,gate,acestep,ollama,zigbee,arlo,scheduler"

    # Multi-bot: admin | songs | gate (un solo modo por proceso)
    BOT_MODE: str = "admin"
    # Username del bot de canciones y del bot de portón (para construir enlaces de invitación desde el admin)
    SONGS_BOT_USERNAME: Optional[str] = None
    GATE_BOT_USERNAME: Optional[str] = None
    # Canal PortonBot: ID o @ del canal donde el bot de portón envía E/S (solo en BOT_MODE=gate)
    PORTON_CHANNEL_ID: Optional[str] = None
    # API key opcional para proteger endpoints de consulta
    API_KEY: Optional[str] = None
    # Puerto HTTP de la API (cada servicio en docker-compose debe usar uno distinto si comparten host)
    PORT: int = 8000

    # From config.yaml (default values or loaded later)
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/home_bot.log"
    CHECK_INTERVAL: int = 5
    PING_TIMEOUT: int = 2
    WOL_BROADCAST: str = "255.255.255.255"
    SSH_PORT: int = 22
    GATE_OPEN_DURATION: int = 5

def load_config_yaml(settings: AppSettings, config_path: str = "config.yaml"):
    path = Path(config_path)
    if not path.exists():
        return settings

    with open(path, "r") as f:
        config_data = yaml.safe_load(f)

    if not config_data:
        return settings

    system = config_data.get("system", {})
    pc = config_data.get("pc", {})
    gate = config_data.get("gate", {})

    settings.LOG_LEVEL = system.get("log_level", settings.LOG_LEVEL)
    settings.LOG_FILE = system.get("log_file", settings.LOG_FILE)
    settings.CHECK_INTERVAL = system.get("check_interval", settings.CHECK_INTERVAL)

    settings.PING_TIMEOUT = pc.get("ping_timeout", settings.PING_TIMEOUT)
    settings.WOL_BROADCAST = pc.get("wol_broadcast", settings.WOL_BROADCAST)
    settings.SSH_PORT = pc.get("ssh_port", settings.SSH_PORT)

    settings.GATE_OPEN_DURATION = gate.get("open_duration", settings.GATE_OPEN_DURATION)

    return settings

settings = AppSettings()
settings = load_config_yaml(settings)


def get_bot_token_for_mode(mode: str) -> str:
    """
    Devuelve el token del bot según BOT_MODE.
    Cada modo puede tener su propio token (BOT_TOKEN_ADMIN, BOT_TOKEN_SONGS, BOT_TOKEN_GATE);
    si no está definido, se usa BOT_TOKEN.
    """
    mode = (mode or "admin").strip().lower()
    token = None
    if mode == "admin":
        token = settings.BOT_TOKEN_ADMIN or settings.BOT_TOKEN
    elif mode == "songs":
        token = settings.BOT_TOKEN_SONGS or settings.BOT_TOKEN
    elif mode == "gate":
        token = settings.BOT_TOKEN_GATE or settings.BOT_TOKEN
    else:
        token = settings.BOT_TOKEN
    if not token:
        raise ValueError(
            f"No bot token configured for mode={mode!r}. "
            f"Set BOT_TOKEN or BOT_TOKEN_{mode.upper()} in .env."
        )
    return token


def get_invite_link_secret() -> str:
    """
    Secreto para cifrar/descifrar enlaces de invitación.
    Debe ser el mismo en todos los procesos (admin, songs, gate). Si no se define INVITE_LINK_SECRET,
    se usa el token del bot admin para que el admin codifique y los otros bots decodifiquen con el mismo valor.
    """
    if settings.INVITE_LINK_SECRET:
        return settings.INVITE_LINK_SECRET
    return get_bot_token_for_mode("admin")
