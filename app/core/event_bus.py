from typing import Callable, Any, Dict, List, Awaitable
from app.core.logging import logger

class EventBus:
    """
    Lightweight internal event bus for decoupling modules.
    No external dependencies required.
    """
    __slots__ = ("_subscribers",)

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], Awaitable[None]]]] = {}

    def subscribe(self, event_type: str, callback: Callable[[Any], Awaitable[None]]):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type}: {callback.__name__ if hasattr(callback, '__name__') else callback}")

    async def publish(self, event_type: str, data: Any = None):
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    await callback(data)
                except Exception as e:
                    logger.error(f"Error in event callback for {event_type}: {e}")
            logger.debug(f"Published event: {event_type} with data: {data}")
        else:
            logger.debug(f"Published event {event_type} with no subscribers.")
