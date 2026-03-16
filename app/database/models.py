from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UserRole(str, PyEnum):
    ADMIN = "ADMIN"
    USER = "USER"
    GUEST = "GUEST"


class AccessType(str, PyEnum):
    SONG = "song"
    GATE = "gate"


class AccessRequestStatus(str, PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Invitation(Base):
    """Acción de invitar: registro de permisos/accesos otorgados (quién invitó a quién, cuándo, tipo)."""
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"))
    invitee_telegram_id: Mapped[int] = mapped_column(index=True)
    invitee_username: Mapped[Optional[str]] = mapped_column(nullable=True)
    invitee_first_name: Mapped[Optional[str]] = mapped_column(nullable=True)
    invitee_last_name: Mapped[Optional[str]] = mapped_column(nullable=True)
    expiration_time: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    registered_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    access_type: Mapped[Optional[str]] = mapped_column(nullable=True)
    # Legacy: mantener por compatibilidad con datos existentes
    song_quota: Mapped[Optional[int]] = mapped_column(nullable=True, default=None)
    songs_used: Mapped[int] = mapped_column(default=0)
    first_used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)
    gate_expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)


class UserQuota(Base):
    """Cuotas y configuraciones por usuario por tipo de acción (canciones, portón)."""
    __tablename__ = "user_quotas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(index=True)
    access_type: Mapped[str] = mapped_column()
    song_quota: Mapped[Optional[int]] = mapped_column(nullable=True, default=None)
    songs_used: Mapped[int] = mapped_column(default=0)
    gate_expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)
    first_used_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class UserOperation(Base):
    """Operaciones realizadas por usuarios (gate_opened, song_generated)."""
    __tablename__ = "user_operations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(index=True)
    operation_type: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    metadata_: Mapped[Optional[str]] = mapped_column("metadata", nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(nullable=True)


class AccessRequest(Base):
    """Solicitudes de más acceso o cantidad (pending/approved/denied)."""
    __tablename__ = "access_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(index=True)
    request_type: Mapped[str] = mapped_column()
    requested_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    requested_value: Mapped[Optional[str]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column()
    responded_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    responded_by: Mapped[Optional[int]] = mapped_column(nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(nullable=True)
