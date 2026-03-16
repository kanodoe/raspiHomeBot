"""
Cifrado del payload de enlaces de invitación para que no se pueda alterar el valor.
Formato: start=inv_<token> o start=inv_gate_<token> (token = Fernet(payload_json)).

Payloads soportados:
- Canciones: {"t": "songs", "c": N} con opcionales "exp" (timestamp), "n" (max_uses).
- Portón:    {"t": "gate", "d": N} (días) con opcionales "exp", "n".
"""
import base64
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.core.logging import logger

INVITE_PREFIX = "inv_"
INVITE_GATE_PREFIX = "inv_gate_"


def _get_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt_payload(payload: Dict[str, Any], secret: str) -> Optional[str]:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning("cryptography not installed; invite links will fail.")
        return None
    try:
        key = _get_fernet_key(secret)
        f = Fernet(key)
        token = f.encrypt(json.dumps(payload).encode("utf-8"))
        return token.decode("ascii")
    except Exception as e:
        logger.warning(f"Invite link encode error: {e}")
        return None


def _decrypt_payload(token_b64: str, secret: str) -> Optional[Dict[str, Any]]:
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        return None
    try:
        padding = 4 - len(token_b64) % 4
        if padding != 4:
            token_b64 += "=" * padding
        key = _get_fernet_key(secret)
        f = Fernet(key)
        payload_bytes = f.decrypt(token_b64.encode("ascii"))
        return json.loads(payload_bytes.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, Exception) as e:
        logger.debug(f"Invite link decode failed: {e}")
        return None


def encode_invite_payload(
    count: int,
    secret: str,
    *,
    exp_after_hours: Optional[int] = None,
    max_uses: Optional[int] = None,
) -> Optional[str]:
    """
    Cifra payload de invitación por canciones.
    exp_after_hours: opcional; expiración del enlace (no de la invitación en DB).
    max_uses: opcional; máximo de usos del enlace (aún no aplicado en backend).
    """
    payload: Dict[str, Any] = {"t": "songs", "c": count}
    if exp_after_hours is not None:
        payload["exp"] = int((datetime.utcnow() + timedelta(hours=exp_after_hours)).timestamp())
    if max_uses is not None:
        payload["n"] = max(1, max_uses)
    return _encrypt_payload(payload, secret)


def decode_invite_payload(token_b64: str, secret: str) -> Optional[Dict[str, Any]]:
    """Descifra token y valida payload de canciones. Devuelve None si inválido o manipulado."""
    data = _decrypt_payload(token_b64, secret)
    if not data or data.get("t") != "songs":
        return None
    if not isinstance(data.get("c"), int) or data["c"] < 1 or data["c"] > 999:
        return None
    if "exp" in data and isinstance(data["exp"], (int, float)) and datetime.utcnow().timestamp() > data["exp"]:
        return None  # Enlace expirado
    return data


def encode_gate_payload(
    days: int,
    secret: str,
    *,
    exp_after_hours: Optional[int] = None,
    max_uses: Optional[int] = None,
) -> Optional[str]:
    """Cifra payload de invitación por portón (días de acceso)."""
    payload: Dict[str, Any] = {"t": "gate", "d": days}
    if exp_after_hours is not None:
        payload["exp"] = int((datetime.utcnow() + timedelta(hours=exp_after_hours)).timestamp())
    if max_uses is not None:
        payload["n"] = max(1, max_uses)
    return _encrypt_payload(payload, secret)


def decode_gate_payload(token_b64: str, secret: str) -> Optional[Dict[str, Any]]:
    """Descifra token y valida payload de portón. Devuelve None si inválido o manipulado."""
    data = _decrypt_payload(token_b64, secret)
    if not data or data.get("t") != "gate":
        return None
    if not isinstance(data.get("d"), int) or data["d"] < 1 or data["d"] > 3650:
        return None
    if "exp" in data and isinstance(data["exp"], (int, float)) and datetime.utcnow().timestamp() > data["exp"]:
        return None
    return data
