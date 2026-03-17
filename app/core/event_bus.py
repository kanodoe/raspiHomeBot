from typing import Callable, Any, Dict, List, Awaitable
from app.core.logging import logger

class EventBus:
    """
    Bus de eventos interno ligero para desacoplar módulos.
    Permite suscribir funciones asíncronas (callbacks) a tipos de eventos específicos
    y publicar datos que serán recibidos por todos los suscriptores.
    """
    __slots__ = ("_subscribers",)

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], Awaitable[None]]]] = {}

    def subscribe(self, event_type: str, callback: Callable[[Any], Awaitable[None]]):
        """
        Suscribe un callback asíncrono a un tipo de evento.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type}: {callback.__name__ if hasattr(callback, '__name__') else callback}")

    async def publish(self, event_type: str, data: Any = None):
        """
        Publica un evento con datos opcionales.
        Ejecuta todos los callbacks suscritos a ese tipo de evento de forma secuencial.
        """
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    await callback(data)
                except Exception as e:
                    logger.error(f"Error in event callback for {event_type}: {e}")
            logger.debug(f"Published event: {event_type} with data: {data}")
        else:
            logger.debug(f"Published event {event_type} with no subscribers.")
