from typing import Any, Dict
from app.core.module import BaseModule
from app.core.logging import logger

class Notifier(BaseModule):
    """
    Subscribes to notification events and sends them to the appropriate targets.
    """
    __slots__ = ("bot_app",)

    def __init__(self, bus, bot_app=None):
        super().__init__(bus)
        self.bot_app = bot_app # telegram bot application

    async def start(self):
        # Subscribing to all notification event types
        self.bus.subscribe("notify.info", self._send_notification)
        self.bus.subscribe("notify.error", self._send_notification)
        self.bus.subscribe("notify.status", self._send_notification)
        self.bus.subscribe("notify.audio", self._send_audio_notification)
        logger.info("Notifier module initialized.")

    async def _send_notification(self, data: Dict[str, Any]):
        message = data.get("message", "No message provided")
        source = data.get("source", "system")
        
        logger.info(f"NOTIFICATION [{source}]: {message}")
        
        # In a real scenario, if bot_app is set, it would send a Telegram message
        if self.bot_app and source.startswith("chat_"):
             # extract chat_id from source
             try:
                 chat_id = int(source.replace("chat_", ""))
                 logger.info(f"Sending Telegram message to {chat_id}: {message}")
                 await self.bot_app.bot.send_message(chat_id=chat_id, text=message)
             except Exception as e:
                 logger.error(f"Failed to send Telegram message: {e}")

    async def _send_audio_notification(self, data: Dict[str, Any]):
        audio_bytes = data.get("audio")
        filename = data.get("filename", "audio.mp3")
        source = data.get("source", "system")
        caption = data.get("caption", "")

        logger.info(f"AUDIO NOTIFICATION [{source}]: {filename}")

        if self.bot_app and source.startswith("chat_"):
            try:
                chat_id = int(source.replace("chat_", ""))
                logger.info(f"Sending Telegram audio to {chat_id}: {filename}")
                import io
                audio_file = io.BytesIO(audio_bytes)
                audio_file.name = filename
                await self.bot_app.bot.send_audio(chat_id=chat_id, audio=audio_file, caption=caption)
            except Exception as e:
                logger.error(f"Failed to send Telegram audio: {e}")
