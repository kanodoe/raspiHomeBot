from typing import Any, Dict
from app.core.module import BaseModule
from app.core.logging import logger
from app.services.wol_service import WOLService
from app.services.pc_monitor_service import PCMonitorService

class PCController(BaseModule):
    """
    Independent module to manage PC power and status.
    Wraps WOL and SSH shutdown logic.
    """
    __slots__ = ()

    def __init__(self, bus):
        super().__init__(bus)

    async def start(self):
        self.bus.subscribe("cmd.pc.on", self._handle_on)
        self.bus.subscribe("cmd.pc.off", self._handle_off)
        self.bus.subscribe("cmd.pc.status", self._handle_status)
        logger.info("PCController module initialized.")

    async def _handle_on(self, data: Dict[str, Any]):
        source = data.get("source")
        logger.info(f"PCController: Turning on PC (source: {source})")
        
        if WOLService.send_wol():
            await self.bus.publish("notify.info", {"message": "WOL packet sent. Monitoring startup...", "source": source})
            
            # Start monitoring
            monitor = PCMonitorService()
            
            async def notify_callback(chat_id_val, message):
                # chat_id_val is the original source (could be string or int)
                await self.bus.publish("notify.status", {"message": message, "source": source})
                # update state
                if "reachable" in message.lower():
                    await self.bus.publish("state.update", {"key": "pc", "value": "online"})

            # chat_id here is the identifier for the monitor, we'll use a hash or source
            await monitor.monitor_startup(hash(source), notify_callback)
        else:
             await self.bus.publish("notify.error", {"message": "Failed to send WOL packet.", "source": source})

    async def _handle_off(self, data: Dict[str, Any]):
        source = data.get("source")
        logger.info(f"PCController: Shutting down PC (source: {source})")
        
        success = await WOLService.shutdown()
        if success:
            await self.bus.publish("notify.info", {"message": "Shutdown command sent via SSH.", "source": source})
            await self.bus.publish("state.update", {"key": "pc", "value": "offline"})
        else:
            await self.bus.publish("notify.error", {"message": "Failed to send shutdown command via SSH.", "source": source})

    async def _handle_status(self, data: Dict[str, Any]):
        source = data.get("source")
        status = await WOLService.get_pc_status()
        await self.bus.publish("state.update", {"key": "pc", "value": status})
        await self.bus.publish("notify.status", {"message": f"PC Status: {status}", "source": source})
