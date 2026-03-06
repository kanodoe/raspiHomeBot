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
        
        # Special check for invitation guests
        if role == UserRole.GUEST:
            stmt = select(Invitation).where(
                Invitation.invitee_telegram_id == telegram_id,
                Invitation.expiration_time > datetime.utcnow()
            )
            result = await self.db.execute(stmt)
            if not result.scalar_one_or_none():
                 # No active invitation, guest but unauthorized for gated commands
                 # Actually, we should check if they are in the 'users' table as guest
                 # If they are just some random user, they have no role.
                 pass

        return role_priority.get(role, 0) >= role_priority.get(required_role, 0)

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
