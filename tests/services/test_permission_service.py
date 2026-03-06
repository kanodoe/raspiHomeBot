import pytest
from datetime import datetime, timedelta
from app.services.permission_service import PermissionService
from app.database.models import User, UserRole, Invitation

@pytest.mark.asyncio
async def test_get_user_role_admin(db_session):
    # Setup
    admin = User(telegram_id=123, role=UserRole.ADMIN, username="admin")
    db_session.add(admin)
    await db_session.commit()
    
    service = PermissionService(db_session)
    role = await service.get_user_role(123)
    
    assert role == UserRole.ADMIN

@pytest.mark.asyncio
async def test_get_user_role_guest_with_invitation(db_session):
    # Setup
    invitation = Invitation(
        inviter_id=123,
        invitee_telegram_id=456,
        invitee_username="guest",
        expiration_time=datetime.utcnow() + timedelta(hours=1)
    )
    db_session.add(invitation)
    await db_session.commit()
    
    service = PermissionService(db_session)
    role = await service.get_user_role(456)
    
    assert role == UserRole.GUEST

@pytest.mark.asyncio
async def test_is_authorized_admin(db_session):
    admin = User(telegram_id=123, role=UserRole.ADMIN, username="admin")
    db_session.add(admin)
    await db_session.commit()
    
    service = PermissionService(db_session)
    
    assert await service.is_authorized(123, UserRole.ADMIN) is True
    assert await service.is_authorized(123, UserRole.USER) is True
    assert await service.is_authorized(123, UserRole.GUEST) is True

@pytest.mark.asyncio
async def test_is_authorized_guest(db_session):
    invitation = Invitation(
        inviter_id=123,
        invitee_telegram_id=456,
        invitee_username="guest",
        expiration_time=datetime.utcnow() + timedelta(hours=1)
    )
    db_session.add(invitation)
    await db_session.commit()
    
    service = PermissionService(db_session)
    
    # Check unauthorized roles
    assert await service.is_authorized(456, UserRole.ADMIN) is False
    assert await service.is_authorized(456, UserRole.USER) is False
    # Check authorized role
    assert await service.is_authorized(456, UserRole.GUEST) is True

@pytest.mark.asyncio
async def test_create_invitation(db_session):
    service = PermissionService(db_session)
    invitation = await service.create_invitation(111, 222, "new_guest", 3)
    
    assert invitation.invitee_telegram_id == 222
    assert invitation.invitee_username == "new_guest"
    assert (invitation.expiration_time - datetime.utcnow()) > timedelta(hours=2)

@pytest.mark.asyncio
async def test_cleanup_expired_invitations(db_session):
    # Setup
    past_invitation = Invitation(
        inviter_id=123,
        invitee_telegram_id=777,
        invitee_username="expired",
        expiration_time=datetime.utcnow() - timedelta(hours=1)
    )
    db_session.add(past_invitation)
    await db_session.commit()
    
    service = PermissionService(db_session)
    await service.cleanup_expired_invitations()
    
    role = await service.get_user_role(777)
    # Default is GUEST, but check that no invitation remains
    from sqlalchemy import select
    stmt = select(Invitation).where(Invitation.invitee_telegram_id == 777)
    result = await db_session.execute(stmt)
    assert result.scalar_one_or_none() is None
