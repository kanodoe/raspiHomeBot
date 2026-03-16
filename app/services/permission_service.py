from datetime import datetime, timedelta
from typing import Optional, List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Invitation, UserRole

class PermissionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_role(self, telegram_id: int) -> UserRole:
        # Check if user exists in the main users table
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            return user.role
        
        # Check if user has an active invitation
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.expiration_time > datetime.utcnow()
        )
        result = await self.db.execute(stmt)
        invitation = result.scalar_one_or_none()
        
        if invitation:
            return UserRole.GUEST
            
        return UserRole.GUEST # Default to Guest but without permissions

    async def is_authorized(self, telegram_id: int, required_role: UserRole) -> bool:
        role = await self.get_user_role(telegram_id)
        
        # Hierarchical roles: ADMIN > USER > GUEST
        role_priority = {
            UserRole.ADMIN: 3,
            UserRole.USER: 2,
            UserRole.GUEST: 1
        }
        
        current_priority = role_priority.get(role, 0)
        required_priority = role_priority.get(required_role, 0)

        # Special check for invitation guests: 
        # Only GUESTs with an active invitation are allowed to perform GUEST-level actions
        if role == UserRole.GUEST:
            stmt = select(Invitation).where(
                Invitation.invitee_telegram_id == telegram_id,
                Invitation.expiration_time > datetime.utcnow()
            )
            result = await self.db.execute(stmt)
            if not result.scalar_one_or_none():
                 # No active invitation, guest is not authorized for any gated commands
                 return False

        return current_priority >= required_priority

    async def create_invitation(self, inviter_id: int, invitee_id: int, invitee_username: str, duration_hours: int):
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
        stmt = delete(Invitation).where(Invitation.expiration_time <= datetime.utcnow())
        await self.db.execute(stmt)
        await self.db.commit()

    async def ensure_admin(self, admin_id: int):
        stmt = select(User).where(User.telegram_id == admin_id)
        result = await self.db.execute(stmt)
        if not result.scalar_one_or_none():
            admin = User(telegram_id=admin_id, role=UserRole.ADMIN, username="Owner")
            self.db.add(admin)
            await self.db.commit()

    # --- Invitaciones por cupo de canciones (solo generate_song, sin otras funciones) ---

    async def get_song_invitation(self, telegram_id: int) -> Optional[Invitation]:
        """Invitación activa con cupo de canciones (song_quota no nulo y queda saldo)."""
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.expiration_time > datetime.utcnow(),
            Invitation.song_quota.isnot(None),
        )
        result = await self.db.execute(stmt)
        inv = result.scalar_one_or_none()
        if inv and inv.songs_used < inv.song_quota:
            return inv
        return None

    async def can_generate_song(self, telegram_id: int) -> bool:
        """True si es USER/ADMIN o tiene invitación con cupo de canciones disponible."""
        role = await self.get_user_role(telegram_id)
        if role in (UserRole.USER, UserRole.ADMIN):
            return True
        return await self.get_song_invitation(telegram_id) is not None

    async def consume_song_quota(self, telegram_id: int) -> bool:
        """Resta 1 al cupo del invitado. Devuelve True si había cupo y se descontó."""
        inv = await self.get_song_invitation(telegram_id)
        if not inv:
            return False
        inv.songs_used += 1
        await self.db.commit()
        return True

    async def get_remaining_songs(self, telegram_id: int) -> Optional[int]:
        """Canciones restantes para un invitado por cupo; None si no es invitado o sin cupo."""
        inv = await self.get_song_invitation(telegram_id)
        if not inv:
            return None
        return max(0, inv.song_quota - inv.songs_used)

    async def create_song_invitation(
        self,
        inviter_id: int,
        invitee_id: int,
        invitee_username: str,
        song_quota: int,
        duration_hours: Optional[int] = None,
    ) -> Invitation:
        """Crea o actualiza invitación con cupo de canciones (solo puede usar generate_song)."""
        duration = duration_hours if duration_hours is not None else 24 * 365 * 2  # 2 años por defecto
        expiration = datetime.utcnow() + timedelta(hours=duration)
        stmt = select(Invitation).where(Invitation.invitee_telegram_id == invitee_id)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.inviter_id = inviter_id
            existing.invitee_username = invitee_username
            existing.expiration_time = expiration
            existing.song_quota = song_quota
            existing.songs_used = 0
            await self.db.commit()
            return existing
        inv = Invitation(
            inviter_id=inviter_id,
            invitee_telegram_id=invitee_id,
            invitee_username=invitee_username,
            expiration_time=expiration,
            song_quota=song_quota,
            songs_used=0,
        )
        self.db.add(inv)
        await self.db.commit()
        return inv

    async def add_song_quota(
        self,
        admin_id: int,
        invitee_telegram_id: int,
        count: int,
        invitee_username: Optional[str] = None,
    ) -> bool:
        """Añade count canciones al cupo del usuario (o crea invitación si no tiene). Devuelve True si ok."""
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
        # Crear nueva invitación con ese cupo
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
        await self.db.commit()
        return True

    async def has_any_song_invitation(self, telegram_id: int) -> bool:
        """True si el usuario tiene alguna invitación de tipo canción (aunque cupo agotado)."""
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.expiration_time > datetime.utcnow(),
            Invitation.song_quota.isnot(None),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_invitation_first_used(self, telegram_id: int) -> bool:
        """Marca first_used_at en la invitación por canciones si aún no estaba marcada. Devuelve True si era la primera vez."""
        stmt = select(Invitation).where(
            Invitation.invitee_telegram_id == telegram_id,
            Invitation.expiration_time > datetime.utcnow(),
            Invitation.song_quota.isnot(None),
            Invitation.first_used_at.is_(None),
        )
        result = await self.db.execute(stmt)
        inv = result.scalar_one_or_none()
        if not inv:
            return False
        inv.first_used_at = datetime.utcnow()
        await self.db.commit()
        return True

    async def list_song_invitations(self) -> List[dict]:
        """Lista invitaciones con cupo de canciones (no expiradas). Para admin."""
        stmt = select(Invitation).where(
            Invitation.expiration_time > datetime.utcnow(),
            Invitation.song_quota.isnot(None),
        ).order_by(Invitation.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "invitee_telegram_id": inv.invitee_telegram_id,
                "invitee_username": inv.invitee_username or f"ID {inv.invitee_telegram_id}",
                "song_quota": inv.song_quota,
                "songs_used": inv.songs_used,
                "remaining": max(0, (inv.song_quota or 0) - inv.songs_used),
                "expiration_time": inv.expiration_time,
                "first_used_at": inv.first_used_at,
            }
            for inv in rows
        ]
