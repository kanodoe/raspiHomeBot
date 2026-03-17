from typing import Any, Dict
from app.core.module import BaseModule
from app.core.logging import logger

class CommandRouter(BaseModule):
    """
    Módulo encargado de enrutar los comandos provenientes de diversas fuentes
    (API, Telegram, Scheduler) hacia los eventos específicos de cada módulo.
    Actúa como un despacho central de comandos.
    """
    __slots__ = ()

    def __init__(self, bus):
        super().__init__(bus)

    async def start(self):
        # Nos suscribimos al evento general "command"
        self.bus.subscribe("command", self._route_command)
        logger.info("CommandRouter module initialized.")

    async def _route_command(self, cmd_data: Dict[str, Any]):
        """
        Analiza un comando genérico y lo traduce a un evento de dominio específico
        (p. ej. 'pc_on' -> 'cmd.pc.on').
        """
        command = cmd_data.get("command")
        logger.info(f"Routing command: {command} from {cmd_data.get('source')}")
        
        # Mapping commands to event types
        mapping = {
            "pc_on": "cmd.pc.on",
            "pc_off": "cmd.pc.off",
            "pc_status": "cmd.pc.status",
            "status": "cmd.status.summary",
            "gate_open": "cmd.gate.open",
            "zigbee_set": "cmd.zigbee.set",
            "arlo_status": "cmd.arlo.status",
            "acestep_start": "cmd.acestep.start",
            "acestep_stop": "cmd.acestep.stop",
            "ollama_start": "cmd.ollama.start",
            "ollama_stop": "cmd.ollama.stop",
            "acestep_generate": "cmd.acestep.generate",
            "acestep_save": "cmd.acestep.save"
        }
        
        event_type = mapping.get(command)
        if event_type:
            await self.bus.publish(event_type, cmd_data)
        else:
            logger.warning(f"Unknown command received: {command}")
            await self.bus.publish("notify.error", {"message": f"Unknown command: {command}", "source": cmd_data.get('source')})
