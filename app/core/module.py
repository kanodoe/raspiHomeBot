from abc import ABC, abstractmethod
from app.core.event_bus import EventBus
from app.core.logging import logger

class BaseModule(ABC):
    """
    Base class for all independent modules in the system.
    Modules interact via the Event Bus.
    """
    __slots__ = ("bus", "module_name")

    def __init__(self, bus: EventBus):
        self.bus = bus
        self.module_name = self.__class__.__name__

    @abstractmethod
    async def start(self):
        """Called during system startup."""
        logger.info(f"Starting {self.module_name}")
        pass

    async def stop(self):
        """Called during system shutdown."""
        logger.info(f"Stopping {self.module_name}")
        pass
