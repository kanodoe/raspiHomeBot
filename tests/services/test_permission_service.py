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

@pytest.mark.asyncio
async def test_create_song_invitation(db_session):
    service = PermissionService(db_session)
    # Test creating a song invitation
    invitation = await service.create_song_invitation(
        inviter_id=123,
        invitee_id=789,
        invitee_username="song_guest",
        song_quota=5,
        duration_hours=24
    )
    
    assert invitation.invitee_telegram_id == 789
    assert invitation.song_quota == 5
    assert (invitation.expiration_time - datetime.utcnow()) > timedelta(hours=23)
    
    # Verify user was created as GUEST
    role = await service.get_user_role(789)
    assert role == UserRole.GUEST
    
    # Verify quota was created
    remaining = await service.get_remaining_songs(789)
    assert remaining == 5

@pytest.mark.asyncio
async def test_consume_song_quota(db_session):
    service = PermissionService(db_session)
    await service.create_song_invitation(
        inviter_id=123,
        invitee_id=789,
        invitee_username="song_guest",
        song_quota=2
    )
    
    # Consume one
    success = await service.consume_song_quota(789)
    assert success is True
    assert await service.get_remaining_songs(789) == 1
    
    # Consume another
    success = await service.consume_song_quota(789)
    assert success is True
    assert await service.get_remaining_songs(789) == 0
    
    # Try to consume one more
    success = await service.consume_song_quota(789)
    assert success is False

@pytest.mark.asyncio
async def test_add_song_quota(db_session):
    service = PermissionService(db_session)
    # Start with 2 songs
    await service.create_song_invitation(
        inviter_id=123,
        invitee_id=789,
        invitee_username="song_guest",
        song_quota=2
    )
    
    # Add 3 more
    await service.add_song_quota(admin_id=123, invitee_telegram_id=789, count=3)
    
    assert await service.get_remaining_songs(789) == 5

@pytest.mark.asyncio
async def test_create_gate_invitation(db_session):
    service = PermissionService(db_session)
    await service.create_gate_invitation(
        inviter_id=123,
        invitee_id=999,
        invitee_username="gate_guest",
        days=7
    )
    
    assert await service.can_open_gate(999) is True
    # Should not have song access
    assert await service.can_generate_song(999) is False
