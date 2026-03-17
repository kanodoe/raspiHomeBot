import io
import json
from typing import Any, Dict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.core.module import BaseModule
from app.core.logging import logger

class Notifier(BaseModule):
    """
    Subscribes to notification events and sends them to the appropriate targets.
    """
    __slots__ = ("bot_app",)

    def __init__(self, bus, bot_app=None):
        super().__init__(bus)
        self.bot_app = bot_app  # telegram bot application

    async def start(self):
        self.bus.subscribe("notify.info", self._send_notification)
        self.bus.subscribe("notify.error", self._send_notification)
        self.bus.subscribe("notify.status", self._send_notification)
        self.bus.subscribe("notify.audio", self._send_audio_notification)
        self.bus.subscribe("notify.admin.song_generated", self._send_admin_song_copy)
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
                 # En entornos multi-bot, es normal que un bot no tenga acceso al chat de otro.
                 if "Chat not found" in str(e) or "bot was blocked" in str(e):
                     logger.info(f"Could not send notification to {chat_id} (this bot hasn't talked to user): {e}")
                 else:
                     logger.error(f"Failed to send Telegram message to {chat_id}: {e}")

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
                audio_file = io.BytesIO(audio_bytes)
                audio_file.name = filename
                await self.bot_app.bot.send_audio(chat_id=chat_id, audio=audio_file, caption=caption)
            except Exception as e:
                logger.error(f"Failed to send Telegram audio: {e}")

    async def _send_admin_song_copy(self, data: Dict[str, Any]):
        """Envía al admin copia de la canción generada: quién, audio, JSON y opción de guardar."""
        from app.core.config import settings
        if not self.bot_app:
            return
        admin_id = settings.ADMIN_TELEGRAM_ID
        audio_bytes = data.get("audio")
        metadata = data.get("metadata", {})
        task_id = data.get("task_id", "?")
        filename = data.get("filename", "song.mp3")
        user_id = data.get("user_id", "?")
        username = data.get("username", str(user_id))
        display_name = data.get("display_name") or username
        prompt = data.get("prompt", "")

        caption = (
            f"🎵 Canción generada por {display_name}\n"
            f"Estilo: {prompt[:200]}{'…' if len(prompt) > 200 else ''}\n\n"
            "Puedes guardar en servidor con el botón de abajo o con /save_song."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Guardar en servidor", callback_data="save_admin_song")]
        ])
        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            await self.bot_app.bot.send_audio(
                chat_id=admin_id,
                audio=audio_file,
                caption=caption,
                reply_markup=keyboard,
            )
            json_bytes = json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8")
            doc_file = io.BytesIO(json_bytes)
            doc_file.name = f"song_{task_id}.json"
            await self.bot_app.bot.send_document(
                chat_id=admin_id,
                document=doc_file,
                caption="JSON devuelto por la API",
            )
            await self.bus.publish("cmd.acestep.cache_for_admin", {
                "admin_chat_id": admin_id,
                "audio": audio_bytes,
                "metadata": metadata,
                "task_id": task_id,
            })
        except Exception as e:
            logger.error(f"Failed to send admin song copy: {e}")
