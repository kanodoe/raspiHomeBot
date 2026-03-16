"""Helper para formatear identificación de usuario ante el admin (nombre, @username, ID)."""
from typing import Optional

from app.database.models import User, Invitation


def format_user_display(
    *,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
    telegram_id: Optional[int] = None,
) -> str:
    """
    Devuelve un texto legible para mostrar al admin: "Nombre Apellido (@username)" o "Nombre (ID 123)".
    """
    parts = []
    if first_name or last_name:
        name = " ".join(filter(None, [first_name, last_name])).strip()
        if name:
            parts.append(name)
    if username:
        parts.append(f"@{username}")
    if telegram_id is not None and not parts:
        parts.append(f"ID {telegram_id}")
    elif telegram_id is not None and not username:
        parts.append(f"(ID {telegram_id})")
    return " ".join(parts) if parts else (str(telegram_id) if telegram_id is not None else "?")


def format_user_from_model(user: User) -> str:
    return format_user_display(
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        telegram_id=user.telegram_id,
    )


def format_invitee_from_invitation(inv: Invitation) -> str:
    return format_user_display(
        first_name=inv.invitee_first_name,
        last_name=inv.invitee_last_name,
        username=inv.invitee_username,
        telegram_id=inv.invitee_telegram_id,
    )
