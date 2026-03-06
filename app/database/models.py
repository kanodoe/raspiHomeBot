from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class UserRole(str, PyEnum):
    ADMIN = "ADMIN"
    USER = "USER"
    GUEST = "GUEST"

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id"))
    invitee_telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    invitee_username: Mapped[Optional[str]] = mapped_column(nullable=True)
    expiration_time: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
