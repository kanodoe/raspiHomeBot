"""
Envía el comando E (entrada) o S (salida) al canal PortonBot.
El bot debe estar añadido al canal con permiso para enviar mensajes.
"""
from typing import Optional, Union

from app.core.config import settings
from app.core.logging import logger


def get_porton_channel_id() -> Optional[Union[str, int]]:
    raw = getattr(settings, "PORTON_CHANNEL_ID", None) or None
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return str(raw).strip()


async def send_porton_command(bot, command: str) -> bool:
    """
    Envía "E" o "S" al canal configurado (PORTON_CHANNEL_ID).
    bot: instancia de telegram.Bot (o con método send_message).
    command: "E" o "S".
    Devuelve True si se envió correctamente.
    """
    channel = get_porton_channel_id()
    if not channel:
        return False
    if command not in ("E", "S"):
        return False
    try:
        await bot.send_message(chat_id=channel, text=command)
        return True
    except Exception as e:
        logger.warning(f"Failed to send {command} to PortonBot channel: {e}")
        return False
