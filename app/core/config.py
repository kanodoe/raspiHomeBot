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

    # From .env
    BOT_TOKEN: str
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

    # Ollama Settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3" # Default to llama3, user can change in .env
    
    # Enabled Modules (comma-separated list)
    ENABLED_MODULES: str = "pc,gate,acestep,ollama,zigbee,arlo,scheduler"

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
