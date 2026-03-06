from typing import Any, Dict
from app.core.module import BaseModule
from app.core.logging import logger

class CommandRouter(BaseModule):
    """
    Routes commands from various sources (API, Telegram, Scheduler) 
    to specific module events.
    """
    __slots__ = ()

    def __init__(self, bus):
        super().__init__(bus)

    async def start(self):
        # We subscribe to general "command" event
        self.bus.subscribe("command", self._route_command)
        logger.info("CommandRouter module initialized.")

    async def _route_command(self, cmd_data: Dict[str, Any]):
        """
        cmd_data: {"command": "pc_on", "source": "telegram", "args": {}}
        """
        command = cmd_data.get("command")
        logger.info(f"Routing command: {command} from {cmd_data.get('source')}")
        
        # Mapping commands to event types
        mapping = {
            "pc_on": "cmd.pc.on",
            "pc_off": "cmd.pc.off",
            "gate_open": "cmd.gate.open",
            "zigbee_set": "cmd.zigbee.set",
            "arlo_status": "cmd.arlo.status"
        }
        
        event_type = mapping.get(command)
        if event_type:
            await self.bus.publish(event_type, cmd_data)
        else:
            logger.warning(f"Unknown command received: {command}")
            await self.bus.publish("notify.error", {"message": f"Unknown command: {command}", "source": cmd_data.get('source')})
