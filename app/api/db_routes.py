"""Endpoints de solo lectura para consultar la base de datos (users, invitations, quotas, operations, access_requests)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db, AsyncSessionLocal
from app.database.models import User, Invitation, UserQuota, UserOperation, AccessRequest
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["db"])


async def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    api_key = getattr(settings, "API_KEY", None) or None
    if not api_key:
        return
    if x_api_key != api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


@router.get("/users", dependencies=[Depends(require_api_key)])
async def list_users(
    db: AsyncSession = Depends(get_db),
    telegram_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(User)
    if telegram_id is not None:
        stmt = stmt.where(User.telegram_id == telegram_id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    stmt = stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": u.id,
                "telegram_id": u.telegram_id,
                "username": u.username,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "role": u.role.value if hasattr(u.role, "value") else u.role,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/users/{telegram_id}", dependencies=[Depends(require_api_key)])
async def get_user(telegram_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("/invitations", dependencies=[Depends(require_api_key)])
async def list_invitations(
    db: AsyncSession = Depends(get_db),
    access_type: Optional[str] = Query(None),
    invitee_telegram_id: Optional[int] = Query(None),
    expired: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(Invitation).order_by(Invitation.created_at.desc())
    if access_type is not None:
        stmt = stmt.where(Invitation.access_type == access_type)
    if invitee_telegram_id is not None:
        stmt = stmt.where(Invitation.invitee_telegram_id == invitee_telegram_id)
    if expired is not None:
        now = datetime.utcnow()
        if expired:
            stmt = stmt.where(Invitation.expiration_time <= now)
        else:
            stmt = stmt.where(Invitation.expiration_time > now)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": inv.id,
                "inviter_id": inv.inviter_id,
                "invitee_telegram_id": inv.invitee_telegram_id,
                "invitee_username": inv.invitee_username,
                "invitee_first_name": inv.invitee_first_name,
                "invitee_last_name": inv.invitee_last_name,
                "expiration_time": inv.expiration_time.isoformat() if inv.expiration_time else None,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "registered_at": inv.registered_at.isoformat() if inv.registered_at else None,
                "access_type": inv.access_type,
            }
            for inv in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/quotas", dependencies=[Depends(require_api_key)])
async def list_quotas(
    db: AsyncSession = Depends(get_db),
    telegram_id: Optional[int] = Query(None),
    access_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(UserQuota).order_by(UserQuota.updated_at.desc())
    if telegram_id is not None:
        stmt = stmt.where(UserQuota.telegram_id == telegram_id)
    if access_type is not None:
        stmt = stmt.where(UserQuota.access_type == access_type)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": q.id,
                "telegram_id": q.telegram_id,
                "access_type": q.access_type,
                "song_quota": q.song_quota,
                "songs_used": q.songs_used,
                "gate_expires_at": q.gate_expires_at.isoformat() if q.gate_expires_at else None,
                "first_used_at": q.first_used_at.isoformat() if q.first_used_at else None,
                "created_at": q.created_at.isoformat() if q.created_at else None,
                "updated_at": q.updated_at.isoformat() if q.updated_at else None,
            }
            for q in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/operations", dependencies=[Depends(require_api_key)])
async def list_operations(
    db: AsyncSession = Depends(get_db),
    telegram_id: Optional[int] = Query(None),
    operation_type: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(UserOperation).order_by(UserOperation.created_at.desc())
    if telegram_id is not None:
        stmt = stmt.where(UserOperation.telegram_id == telegram_id)
    if operation_type is not None:
        stmt = stmt.where(UserOperation.operation_type == operation_type)
    if since is not None:
        try:
            stmt = stmt.where(UserOperation.created_at >= datetime.fromisoformat(since.replace("Z", "+00:00")))
        except ValueError:
            pass
    if until is not None:
        try:
            stmt = stmt.where(UserOperation.created_at <= datetime.fromisoformat(until.replace("Z", "+00:00")))
        except ValueError:
            pass
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": op.id,
                "telegram_id": op.telegram_id,
                "operation_type": op.operation_type,
                "created_at": op.created_at.isoformat() if op.created_at else None,
                "metadata": op.metadata_,
                "display_name": op.display_name,
            }
            for op in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/access-requests", dependencies=[Depends(require_api_key)])
async def list_access_requests(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    telegram_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = select(AccessRequest).order_by(AccessRequest.requested_at.desc())
    if status is not None:
        stmt = stmt.where(AccessRequest.status == status)
    if telegram_id is not None:
        stmt = stmt.where(AccessRequest.telegram_id == telegram_id)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "telegram_id": r.telegram_id,
                "request_type": r.request_type,
                "requested_at": r.requested_at.isoformat() if r.requested_at else None,
                "requested_value": r.requested_value,
                "status": r.status,
                "responded_at": r.responded_at.isoformat() if r.responded_at else None,
                "responded_by": r.responded_by,
                "notes": r.notes,
            }
            for r in rows
        ],
        "limit": limit,
        "offset": offset,
    }
