import asyncio
from typing import Dict, Any, Optional

from app.core.logging import logger
from app.utils.network import ping
from app.core.config import settings

class PCMonitorService:
    _monitoring_tasks: Dict[int, asyncio.Task] = {}

    def __init__(self, bot_context=None):
        self.bot_context = bot_context

    async def monitor_startup(self, chat_id: int, callback):
        """
        Monitors PC status after WOL. 
        Calls callback when PC becomes reachable.
        """
        if chat_id in self._monitoring_tasks:
            if not self._monitoring_tasks[chat_id].done():
                logger.info(f"Monitor already running for chat {chat_id}")
                return
            
        task = asyncio.create_task(self._poll_pc(chat_id, callback))
        self._monitoring_tasks[chat_id] = task

    async def _poll_pc(self, chat_id: int, callback):
        max_retries = 30 # ~2.5 mins if check interval is 5s
        retries = 0
        
        while retries < max_retries:
            is_online = await ping(settings.PC_IP, timeout=settings.PING_TIMEOUT)
            if is_online:
                logger.info(f"PC {settings.PC_IP} is now online. Notifying chat {chat_id}")
                await callback(chat_id, "PC is now reachable!")
                break
            
            retries += 1
            await asyncio.sleep(settings.CHECK_INTERVAL)
        
        if retries == max_retries:
             logger.warning(f"PC {settings.PC_IP} did not become online in time.")
             await callback(chat_id, "PC did not respond after timeout.")
        
        if chat_id in self._monitoring_tasks:
            del self._monitoring_tasks[chat_id]
