from typing import Any, Dict
from app.core.module import BaseModule
from app.core.logging import logger
from app.database.session import AsyncSessionLocal
from app.services.permission_service import PermissionService

class PermissionController(BaseModule):
    """
    Independent module to manage permissions and invitations.
    """
    __slots__ = ()

    def __init__(self, bus):
        super().__init__(bus)

    async def start(self):
        self.bus.subscribe("cmd.cleanup", self._handle_cleanup)
        logger.info("PermissionController module initialized.")

    async def _handle_cleanup(self, data: Dict[str, Any]):
        logger.info("PermissionController: Running invitation cleanup...")
        async with AsyncSessionLocal() as session:
            service = PermissionService(session)
            await service.cleanup_expired_invitations()
        logger.info("PermissionController: Invitation cleanup complete.")
