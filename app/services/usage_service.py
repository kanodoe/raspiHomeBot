"""Registro de operaciones de usuarios y solicitudes de acceso."""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserOperation, AccessRequest, AccessRequestStatus


class UsageService:
    """
    Servicio para registrar y consultar las operaciones de los usuarios (logs)
    y las solicitudes de acceso (pedir más canciones).
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_operation(
        self,
        telegram_id: int,
        operation_type: str,
        *,
        metadata: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> UserOperation:
        """
        Registra una operación realizada por un usuario en la base de datos.
        """
        op = UserOperation(
            telegram_id=telegram_id,
            operation_type=operation_type,
            metadata_=metadata,
            display_name=display_name,
        )
        self.db.add(op)
        await self.db.commit()
        await self.db.refresh(op)
        return op

    async def create_access_request(
        self,
        telegram_id: int,
        request_type: str,
        requested_value: Optional[str] = None,
    ) -> AccessRequest:
        """
        Crea una solicitud de acceso (p. ej. más canciones) pendiente de aprobación.
        """
        req = AccessRequest(
            telegram_id=telegram_id,
            request_type=request_type,
            requested_value=requested_value,
            status=AccessRequestStatus.PENDING.value,
        )
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def resolve_access_request(
        self,
        request_id: int,
        status: str,
        responded_by: int,
        notes: Optional[str] = None,
    ) -> Optional[AccessRequest]:
        """
        Marca una solicitud de acceso como aprobada o denegada.
        """
        stmt = select(AccessRequest).where(AccessRequest.id == request_id)
        result = await self.db.execute(stmt)
        req = result.scalar_one_or_none()
        if not req:
            return None
        req.status = status
        req.responded_at = datetime.utcnow()
        req.responded_by = responded_by
        if notes is not None:
            req.notes = notes
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def list_access_requests(
        self,
        status: Optional[str] = None,
        telegram_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[AccessRequest]:
        """
        Lista las solicitudes de acceso, opcionalmente filtradas por estado o usuario.
        """
        stmt = select(AccessRequest).order_by(AccessRequest.requested_at.desc())
        if status:
            stmt = stmt.where(AccessRequest.status == status)
        if telegram_id is not None:
            stmt = stmt.where(AccessRequest.telegram_id == telegram_id)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
