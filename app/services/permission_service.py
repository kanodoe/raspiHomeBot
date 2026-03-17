from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Invitation, UserQuota, UserRole
from app.utils.user_display import format_invitee_from_invitation

class PermissionService:
    """
    Servicio encargado de gestionar los permisos y roles de los usuarios,
    así como las invitaciones y cuotas de acceso (canciones y portón).
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_role(self, telegram_id: int) -> UserRole:
        """
        Obtiene el rol de un usuario basado en su telegram_id.
        Si no existe el usuario, pero tiene una invitación válida, se le considera GUEST.
        De lo contrario, devuelve el rol del usuario o GUEST por defecto.
        """
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user.role
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.expiration_time > datetime.utcnow()
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            return UserRole.GUEST
        stmt_q = select(UserQuota).where(UserQuota.telegram_id == telegram_id)
        rq = await self.db.execute(stmt_q)
        now = datetime.utcnow()
        for q in rq.scalars().all():
            if q.access_type == "song" and (q.song_quota or 0) > 0:
                return UserRole.GUEST
            if q.access_type == "gate" and q.gate_expires_at and q.gate_expires_at > now:
                return UserRole.GUEST
        return UserRole.GUEST

    async def is_authorized(self, telegram_id: int, required_role: UserRole) -> bool:
        """
        Verifica si un usuario tiene autorización para un rol específico o superior.
        ADMIN > USER > GUEST.
        También verifica si el usuario tiene cuotas activas si el rol requerido es USER o GUEST.
        """
        role = await self.get_user_role(telegram_id)
        
        # Hierarchical roles: ADMIN > USER > GUEST
        role_priority = {
            UserRole.ADMIN: 3,
            UserRole.USER: 2,
            UserRole.GUEST: 1
        }
        
        current_priority = role_priority.get(role, 0)
        required_priority = role_priority.get(required_role, 0)

        # Solo GUEST con invitación o cuota activa pueden ejecutar acciones de invitado
        if role == UserRole.GUEST:
            stmt = select(Invitation).where(
                Invitation.invitee_telegram_id == telegram_id,
                Invitation.expiration_time > datetime.utcnow()
            )
            result = await self.db.execute(stmt)
            if result.scalar_one_or_none():
                return current_priority >= required_priority
            stmt_q = select(UserQuota).where(UserQuota.telegram_id == telegram_id)
            rq = await self.db.execute(stmt_q)
            for q in rq.scalars().all():
                if q.access_type == "song" and (q.song_quota or 0) > q.songs_used:
                    return current_priority >= required_priority
                if q.access_type == "gate" and q.gate_expires_at and q.gate_expires_at > datetime.utcnow():
                    return current_priority >= required_priority
            return False

        return current_priority >= required_priority

    async def create_invitation(self, inviter_id: int, invitee_id: int, invitee_username: str, duration_hours: int):
        """
        Crea o actualiza una invitación general por tiempo (legacy).
        """
        expiration = datetime.utcnow() + timedelta(hours=duration_hours)
        invitation = Invitation(
            inviter_id=inviter_id,
            invitee_telegram_id=invitee_id,
            invitee_username=invitee_username,
            expiration_time=expiration
        )
        # Upsert logic (if already exists, update expiration)
        stmt = select(Invitation).where(Invitation.invitee_telegram_id == invitee_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.expiration_time = expiration
            existing.inviter_id = inviter_id
            existing.invitee_username = invitee_username
        else:
            self.db.add(invitation)
        
        await self.db.commit()
        return invitation

    async def cleanup_expired_invitations(self):
        """
        Elimina todas las invitaciones cuya fecha de expiración haya pasado.
        """
        stmt = delete(Invitation).where(Invitation.expiration_time <= datetime.utcnow())
        await self.db.execute(stmt)
        await self.db.commit()

    async def ensure_admin(self, admin_id: int, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None):
        """
        Asegura que el administrador principal existe en la base de datos con los datos proporcionados.
        """
        stmt = select(User).where(User.telegram_id == admin_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=admin_id, role=UserRole.ADMIN, username=username or "Owner", first_name=first_name, last_name=last_name)
            self.db.add(user)
            await self.db.commit()
        elif username is not None or first_name is not None or last_name is not None:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            await self.db.commit()

    async def ensure_guest(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """
        Crea o actualiza un usuario con role GUEST para que aparezca en usuarios registrados
        y los permisos funcionen por User.
        """
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                telegram_id=telegram_id,
                role=UserRole.GUEST,
                username=username or f"User_{telegram_id}",
                first_name=first_name,
                last_name=last_name,
            )
            self.db.add(user)
            await self.db.commit()
        else:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            await self.db.commit()
        return user

    async def _get_song_quota(self, telegram_id: int) -> Optional[UserQuota]:
        """UserQuota activo para canciones (quota > used)."""
        stmt = select(UserQuota).where(
            and_(
                UserQuota.telegram_id == telegram_id,
                UserQuota.access_type == "song",
                UserQuota.song_quota.isnot(None),
            )
        )
        result = await self.db.execute(stmt)
        q = result.scalar_one_or_none()
        if q and (q.song_quota or 0) > q.songs_used:
            return q
        return None

    async def _get_gate_quota(self, telegram_id: int) -> Optional[UserQuota]:
        """UserQuota activo para portón (gate_expires_at > now)."""
        stmt = select(UserQuota).where(
            and_(
                UserQuota.telegram_id == telegram_id,
                UserQuota.access_type == "gate",
                UserQuota.gate_expires_at.isnot(None),
                UserQuota.gate_expires_at > datetime.utcnow(),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # --- Invitaciones por cupo de canciones (solo generate_song, sin otras funciones) ---

    async def get_song_invitation(self, telegram_id: int) -> Optional[Invitation]:
        """Invitación activa con cupo (solo legacy Invitation; UserQuota se consulta por separado)."""
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.expiration_time > datetime.utcnow(),
            Invitation.song_quota.isnot(None),
        )
        result = await self.db.execute(stmt)
        inv = result.scalar_one_or_none()
        if inv and inv.songs_used < (inv.song_quota or 0):
            return inv
        return None

    async def can_generate_song(self, telegram_id: int) -> bool:
        """
        Verifica si un usuario puede generar una canción.
        True si es USER/ADMIN o tiene cupo de canciones activo (UserQuota o Invitation legacy).
        """
        role = await self.get_user_role(telegram_id)
        if role in (UserRole.USER, UserRole.ADMIN):
            return True
        if await self._get_song_quota(telegram_id) is not None:
            return True
        return await self.get_song_invitation(telegram_id) is not None

    async def consume_song_quota(self, telegram_id: int) -> bool:
        """
        Resta 1 al cupo de canciones del usuario. 
        Mantiene sincronizados UserQuota e Invitation legacy.
        Devuelve True si se pudo descontar.
        """
        # Intentar descontar de UserQuota
        quota = await self._get_song_quota(telegram_id)
        if quota:
            quota.songs_used += 1
            # Sincronizar con Invitation legacy si existe
            inv = await self.get_song_invitation(telegram_id)
            if inv:
                inv.songs_used = quota.songs_used
            await self.db.commit()
            return True
        
        # Si no hay UserQuota activo, intentar con Invitation legacy
        inv = await self.get_song_invitation(telegram_id)
        if not inv:
            return False
        inv.songs_used += 1
        await self.db.commit()
        return True

    async def get_remaining_songs(self, telegram_id: int) -> Optional[int]:
        """
        Calcula la cantidad de canciones restantes para un usuario.
        Busca en UserQuota y Invitation (legacy), devolviendo 0 si el cupo está agotado.
        Si no tiene ninguna invitación o cuota registrada, devuelve None.
        """
        # Intentar con UserQuota (aunque esté agotado)
        stmt_q = select(UserQuota).where(
            and_(UserQuota.telegram_id == telegram_id, UserQuota.access_type == "song")
        )
        quota = (await self.db.execute(stmt_q)).scalar_one_or_none()
        if quota:
            return max(0, (quota.song_quota or 0) - quota.songs_used)
            
        # Intentar con Invitation legacy (aunque esté agotada)
        stmt_i = select(Invitation).where(
            and_(Invitation.invitee_telegram_id == telegram_id, Invitation.song_quota.isnot(None))
        )
        inv = (await self.db.execute(stmt_i)).scalar_one_or_none()
        if inv:
            return max(0, (inv.song_quota or 0) - inv.songs_used)
            
        return None

    async def create_song_invitation(
        self,
        inviter_id: int,
        invitee_id: int,
        invitee_username: str,
        song_quota: int,
        duration_hours: Optional[int] = None,
        invitee_first_name: Optional[str] = None,
        invitee_last_name: Optional[str] = None,
    ) -> Invitation:
        """
        Crea o actualiza una invitación específica para generación de canciones.
        Establece tanto la invitación (como registro histórico) como la cuota (UserQuota).
        También asegura que el usuario esté registrado como GUEST.
        """
        now = datetime.utcnow()
        duration = duration_hours if duration_hours is not None else 24 * 365 * 2
        expiration = now + timedelta(hours=duration)
        
        # 1. Asegurar que el usuario existe en la tabla users
        await self.ensure_guest(
            telegram_id=invitee_id,
            username=invitee_username,
            first_name=invitee_first_name,
            last_name=invitee_last_name
        )

        # 2. Gestionar Invitación (legacy/registro de evento)
        stmt = select(Invitation).where(Invitation.invitee_telegram_id == invitee_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.inviter_id = inviter_id
            existing.invitee_username = invitee_username
            existing.invitee_first_name = invitee_first_name
            existing.invitee_last_name = invitee_last_name
            existing.expiration_time = expiration
            existing.song_quota = song_quota
            existing.songs_used = 0
            existing.registered_at = existing.registered_at or now
            existing.access_type = "song"
            await self.db.commit()
            inv = existing
        else:
            inv = Invitation(
                inviter_id=inviter_id,
                invitee_telegram_id=invitee_id,
                invitee_username=invitee_username,
                invitee_first_name=invitee_first_name,
                invitee_last_name=invitee_last_name,
                expiration_time=expiration,
                song_quota=song_quota,
                songs_used=0,
                registered_at=now,
                access_type="song",
            )
            self.db.add(inv)
            await self.db.commit()
        stmt_q = select(UserQuota).where(
            and_(UserQuota.telegram_id == invitee_id, UserQuota.access_type == "song")
        )
        rq = await self.db.execute(stmt_q)
        quota = rq.scalar_one_or_none()
        if quota:
            quota.song_quota = song_quota
            quota.songs_used = 0
            quota.updated_at = now
            await self.db.commit()
        else:
            self.db.add(
                UserQuota(
                    telegram_id=invitee_id,
                    access_type="song",
                    song_quota=song_quota,
                    songs_used=0,
                )
            )
            await self.db.commit()
        return inv

    async def add_song_quota(
        self,
        admin_id: int,
        invitee_telegram_id: int,
        count: int,
        invitee_username: Optional[str] = None,
    ) -> bool:
        """
        Añade una cantidad específica de canciones al cupo de un usuario.
        Si el usuario no tiene cuota previa, se le crea una nueva con una duración de 2 años.
        """
        # Asegurar que el usuario existe
        await self.ensure_guest(
            telegram_id=invitee_telegram_id,
            username=invitee_username
        )

        stmt_q = select(UserQuota).where(
            and_(UserQuota.telegram_id == invitee_telegram_id, UserQuota.access_type == "song")
        )
        rq = await self.db.execute(stmt_q)
        quota = rq.scalar_one_or_none()
        if quota:
            quota.song_quota = (quota.song_quota or 0) + count
            quota.updated_at = datetime.utcnow()
            await self.db.commit()
            return True
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == invitee_telegram_id,
            Invitation.song_quota.isnot(None),
        )
        result = await self.db.execute(stmt)
        inv = result.scalar_one_or_none()
        if inv:
            inv.song_quota = (inv.song_quota or 0) + count
            if invitee_username is not None:
                inv.invitee_username = invitee_username
            await self.db.commit()
            return True
        expiration = datetime.utcnow() + timedelta(hours=24 * 365 * 2)
        new_inv = Invitation(
            inviter_id=admin_id,
            invitee_telegram_id=invitee_telegram_id,
            invitee_username=invitee_username or f"Guest_{invitee_telegram_id}",
            expiration_time=expiration,
            song_quota=count,
            songs_used=0,
        )
        self.db.add(new_inv)
        self.db.add(
            UserQuota(
                telegram_id=invitee_telegram_id,
                access_type="song",
                song_quota=count,
                songs_used=0,
            )
        )
        await self.db.commit()
        return True

    async def has_any_song_invitation(self, telegram_id: int) -> bool:
        """True si tiene cupo de canciones (UserQuota o Invitation) aunque agotado."""
        stmt_q = select(UserQuota).where(
            and_(UserQuota.telegram_id == telegram_id, UserQuota.access_type == "song")
        )
        if (await self.db.execute(stmt_q)).scalar_one_or_none():
            return True
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.expiration_time > datetime.utcnow(),
            Invitation.song_quota.isnot(None),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_invitation_first_used(self, telegram_id: int) -> bool:
        """Marca first_used_at en UserQuota e Invitation por canciones si aún no estaba. True si era la primera vez."""
        now = datetime.utcnow()
        marked = False
        stmt_q = select(UserQuota).where(
            and_(UserQuota.telegram_id == telegram_id, UserQuota.access_type == "song")
        )
        rq = await self.db.execute(stmt_q)
        quota = rq.scalar_one_or_none()
        if quota and quota.first_used_at is None:
            quota.first_used_at = now
            marked = True
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.expiration_time > datetime.utcnow(),
            Invitation.song_quota.isnot(None),
            Invitation.first_used_at.is_(None),
        )
        result = await self.db.execute(stmt)
        inv = result.scalar_one_or_none()
        if inv:
            inv.first_used_at = now
            marked = True
        if marked:
            await self.db.commit()
        return marked

    async def list_song_invitations(self) -> List[dict]:
        """Lista invitaciones/cupos de canciones (Invitation + UserQuota). Para admin."""
        stmt = select(Invitation).where(
            Invitation.expiration_time > datetime.utcnow(),
            Invitation.song_quota.isnot(None),
        ).order_by(Invitation.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        out = []
        for inv in rows:
            stmt_q = select(UserQuota).where(
                and_(UserQuota.telegram_id == inv.invitee_telegram_id, UserQuota.access_type == "song")
            )
            rq = await self.db.execute(stmt_q)
            quota_row = rq.scalar_one_or_none()
            used = quota_row.songs_used if quota_row else inv.songs_used
            total = quota_row.song_quota if quota_row else inv.song_quota
            first_used = (quota_row.first_used_at if quota_row else None) or inv.first_used_at
            out.append({
                "invitee_telegram_id": inv.invitee_telegram_id,
                "invitee_username": inv.invitee_username or f"ID {inv.invitee_telegram_id}",
                "invitee_first_name": inv.invitee_first_name,
                "invitee_last_name": inv.invitee_last_name,
                "display_name": format_invitee_from_invitation(inv),
                "song_quota": total,
                "songs_used": used,
                "remaining": max(0, (total or 0) - used),
                "expiration_time": inv.expiration_time,
                "first_used_at": first_used,
            })
        return out

    async def get_invitation_by_id(self, invitation_id: int) -> Optional[Invitation]:
        """Devuelve una invitación por su id, o None si no existe."""
        stmt = select(Invitation).where(Invitation.id == invitation_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_invitation(self, invitation_id: int) -> bool:
        """
        Revoca una invitación por id: elimina la fila Invitation y la cuota asociada (UserQuota)
        del invitee para ese access_type, de modo que pierde el acceso.
        Devuelve True si se revocó, False si no existía.
        """
        inv = await self.get_invitation_by_id(invitation_id)
        if not inv:
            return False
        invitee_id = inv.invitee_telegram_id
        access_type = inv.access_type or ("song" if inv.song_quota is not None else "gate")
        self.db.delete(inv)
        stmt_q = select(UserQuota).where(
            and_(UserQuota.telegram_id == invitee_id, UserQuota.access_type == access_type)
        )
        rq = await self.db.execute(stmt_q)
        quota = rq.scalar_one_or_none()
        if quota:
            self.db.delete(quota)
        await self.db.commit()
        return True

    # --- Invitaciones por portón (acceso por N días) ---

    async def get_gate_invitation(self, telegram_id: int):
        """Invitación/cuota activa de portón: primero UserQuota, luego Invitation legacy."""
        quota = await self._get_gate_quota(telegram_id)
        if quota:
            return quota
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.gate_expires_at.isnot(None),
            Invitation.gate_expires_at > datetime.utcnow(),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def can_open_gate(self, telegram_id: int) -> bool:
        """True si es USER/ADMIN o tiene acceso a portón activo (UserQuota o Invitation)."""
        role = await self.get_user_role(telegram_id)
        if role in (UserRole.USER, UserRole.ADMIN):
            return True
        return await self.get_gate_invitation(telegram_id) is not None

    async def create_gate_invitation(
        self,
        inviter_id: int,
        invitee_id: int,
        invitee_username: str,
        days: int,
        invitee_first_name: Optional[str] = None,
        invitee_last_name: Optional[str] = None,
    ) -> Invitation:
        """
        Crea o actualiza una invitación para el control del portón.
        Establece la expiración en días a partir de ahora y asegura que el usuario sea GUEST.
        """
        now = datetime.utcnow()
        expiration = now + timedelta(days=days)
        
        # 1. Asegurar que el usuario existe en la tabla users
        await self.ensure_guest(
            telegram_id=invitee_id,
            username=invitee_username,
            first_name=invitee_first_name,
            last_name=invitee_last_name
        )

        # 2. Gestionar Invitación
        stmt = select(Invitation).where(Invitation.invitee_telegram_id == invitee_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.inviter_id = inviter_id
            existing.invitee_username = invitee_username
            existing.invitee_first_name = invitee_first_name
            existing.invitee_last_name = invitee_last_name
            existing.gate_expires_at = expiration
            existing.registered_at = existing.registered_at or now
            existing.access_type = "gate"
            if existing.expiration_time < expiration or existing.expiration_time is None:
                existing.expiration_time = expiration
            await self.db.commit()
            inv = existing
        else:
            inv = Invitation(
                inviter_id=inviter_id,
                invitee_telegram_id=invitee_id,
                invitee_username=invitee_username,
                invitee_first_name=invitee_first_name,
                invitee_last_name=invitee_last_name,
                expiration_time=expiration,
                gate_expires_at=expiration,
                registered_at=now,
                access_type="gate",
            )
            self.db.add(inv)
            await self.db.commit()
        stmt_q = select(UserQuota).where(
            and_(UserQuota.telegram_id == invitee_id, UserQuota.access_type == "gate")
        )
        rq = await self.db.execute(stmt_q)
        quota = rq.scalar_one_or_none()
        if quota:
            quota.gate_expires_at = expiration
            quota.updated_at = now
            await self.db.commit()
        else:
            self.db.add(
                UserQuota(
                    telegram_id=invitee_id,
                    access_type="gate",
                    gate_expires_at=expiration,
                )
            )
            await self.db.commit()
        return inv
