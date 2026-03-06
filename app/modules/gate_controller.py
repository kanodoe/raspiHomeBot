from typing import Any, Dict
from app.core.module import BaseModule
from app.core.logging import logger
from app.services.gate_service import GateService

class GateController(BaseModule):
    """
    Independent module to manage gate control.
    Wraps GateService logic.
    """
    __slots__ = ()

    def __init__(self, bus):
        super().__init__(bus)

    async def start(self):
        self.bus.subscribe("cmd.gate.open", self._handle_open)
        logger.info("GateController module initialized.")

    async def _handle_open(self, data: Dict[str, Any]):
        source = data.get("source")
        logger.info(f"GateController: Opening gate (source: {source})")
        
        await self.bus.publish("state.update", {"key": "gate", "value": "opening"})
        success = await GateService.open_gate()
        
        if success:
            await self.bus.publish("state.update", {"key": "gate", "value": "closed"}) # it closes after delay in GateService
            await self.bus.publish("notify.info", {"message": "Gate opened.", "source": source})
        else:
            await self.bus.publish("state.update", {"key": "gate", "value": "error"})
            await self.bus.publish("notify.error", {"message": "Failed to open gate.", "source": source})
