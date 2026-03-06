from typing import Any, Dict
from app.core.module import BaseModule
from app.core.logging import logger

class StateStore(BaseModule):
    """
    Subscribes to events to maintain a consistent state of the system.
    """
    __slots__ = ("state",)

    def __init__(self, bus):
        super().__init__(bus)
        self.state: Dict[str, Any] = {
            "pc": "offline",
            "gate": "closed",
            "zigbee_devices": {},
            "arlo_cameras": {}
        }

    async def start(self):
        self.bus.subscribe("state.update", self._handle_state_update)
        logger.info("StateStore module initialized.")

    async def _handle_state_update(self, update_data: Dict[str, Any]):
        """
        Expects update_data in format: {"key": "path.to.state", "value": value}
        """
        key = update_data.get("key")
        value = update_data.get("value")
        if key:
            self.state[key] = value
            logger.debug(f"State updated: {key} = {value}")

    def get_state(self, key: str = None):
        if key:
            return self.state.get(key)
        return self.state
