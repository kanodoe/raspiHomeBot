import asyncio
from typing import Dict, Any, List
from app.core.module import BaseModule
from app.core.logging import logger

class SchedulerModule(BaseModule):
    """
    Independent module to handle background tasks and time-based events.
    """
    __slots__ = ("_running",)

    def __init__(self, bus):
        super().__init__(bus)
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._main_loop())
        logger.info("SchedulerModule module initialized.")

    async def stop(self):
        self._running = False
        logger.info("SchedulerModule module stopping.")

    async def _main_loop(self):
        """
        Periodically publishes tick events and manages log rotation.
        """
        from app.services.log_service import LogService
        count = 0
        while self._running:
            await self.bus.publish("time.tick", {"count": count})
            
            # Every minute (60s)
            if count % 60 == 0:
                await self.bus.publish("time.minute", {"minute": count // 60})
                
                # Check for log rotation once a day at 00:00 (approximate)
                # Or just every 24 hours (86400 seconds)
                if (count // 60) % 1440 == 0:
                    LogService.rotate_logs()
            
            # Cleanup task every hour (3600s)
            if count % 3600 == 0:
                await self.bus.publish("cmd.cleanup", {"source": "scheduler"})
            
            count += 1
            await asyncio.sleep(1)
