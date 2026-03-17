"""
Cifrado del payload de enlaces de invitación para que no se pueda alterar el valor.
Formato: start=inv_<token> o start=inv_gate_<token> (token = Fernet(payload_json)).

Payloads soportados:
- Canciones (solo cantidad): {"t": "songs", "c": N} — N canciones, acceso prolongado (ej. 2 años).
- Canciones (cantidad + horas): {"t": "songs", "c": N, "h": H} — N canciones, acceso dura H horas.
- Portón: {"t": "gate", "d": N} (días) con opcionales "exp", "n".
"""
import base64
import hashlib
import hmac
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
    """
    Intenta cifrar con un formato compacto (v2) para no superar los 64 caracteres de Telegram.
    Si falla, cae a Fernet (legacy).
    """
    # Formato compacto v2: v2<tipo><datos>.<hmac>
    # s: canciones, g: gate
    # c: count, h: hours, d: days, e: expiration, n: max_uses
    try:
        t = payload.get("t")
        data_str = ""
        if t == "songs":
            data_str = f"s{payload['c']}"
            if "h" in payload:
                data_str += f"h{payload['h']}"
        elif t == "gate":
            data_str = f"g{payload['d']}"
        
        if "exp" in payload:
            data_str += f"e{payload['exp']}"
        if "n" in payload:
            data_str += f"n{payload['n']}"
        
        if data_str:
            signature = hmac.new(
                secret.encode(), data_str.encode(), hashlib.sha256
            ).digest()
            # 12 caracteres de HMAC son suficientes para evitar brute force en este contexto
            sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii")[:12]
            token_v2 = f"v2{data_str}.{sig_b64}"
            if len(token_v2) <= 60:  # margen para prefijos
                return token_v2
    except Exception as e:
        logger.debug(f"Compact encode failed, falling back to Fernet: {e}")

    # Fallback a Fernet (legacy, probablemente supere 64 chars)
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


def _decrypt_payload(token_str: str, secret: str) -> Optional[Dict[str, Any]]:
    # 1. Detectar si es formato v2
    if token_str.startswith("v2"):
        try:
            if "." not in token_str:
                return None
            data_part, sig_part = token_str[2:].split(".", 1)
            
            # Validar firma
            expected_sig = hmac.new(
                secret.encode(), data_part.encode(), hashlib.sha256
            ).digest()
            expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode("ascii")[:12]
            
            if not hmac.compare_digest(sig_part, expected_sig_b64):
                logger.warning("Invite link signature mismatch")
                return None
            
            # Parsear datos (muy simple: sN, hN, dN, eN, nN)
            import re
            res: Dict[str, Any] = {}
            if data_part.startswith("s"):
                res["t"] = "songs"
                m = re.search(r"s(\d+)", data_part)
                if m: res["c"] = int(m.group(1))
                m = re.search(r"h(\d+)", data_part)
                if m: res["h"] = int(m.group(1))
            elif data_part.startswith("g"):
                res["t"] = "gate"
                m = re.search(r"g(\d+)", data_part)
                if m: res["d"] = int(m.group(1))
            
            m = re.search(r"e(\d+)", data_part)
            if m: res["exp"] = int(m.group(1))
            m = re.search(r"n(\d+)", data_part)
            if m: res["n"] = int(m.group(1))
            
            return res
        except Exception as e:
            logger.debug(f"V2 decrypt failed: {e}")
            return None

    # 2. Legacy: Fernet
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        return None
    try:
        token_b64 = token_str
        padding = 4 - len(token_b64) % 4
        if padding != 4:
            token_b64 += "=" * padding
        key = _get_fernet_key(secret)
        f = Fernet(key)
        payload_bytes = f.decrypt(token_b64.encode("ascii"))
        return json.loads(payload_bytes.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, Exception) as e:
        logger.debug(f"Invite link decode failed (Fernet): {e}")
        return None


def encode_invite_payload(
    count: int,
    secret: str,
    *,
    duration_hours: Optional[int] = None,
    exp_after_hours: Optional[int] = None,
    max_uses: Optional[int] = None,
) -> Optional[str]:
    """
    Cifra payload de invitación por canciones.
    duration_hours: opcional; si se indica, el acceso del invitado expira tras esas horas.
    exp_after_hours: opcional; expiración del enlace (no de la invitación en DB).
    max_uses: opcional; máximo de usos del enlace (aún no aplicado en backend).
    """
    payload: Dict[str, Any] = {"t": "songs", "c": count}
    if duration_hours is not None and duration_hours > 0:
        payload["h"] = min(duration_hours, 87600)  # máx 10 años
    if exp_after_hours is not None:
        payload["exp"] = int((datetime.utcnow() + timedelta(hours=exp_after_hours)).timestamp())
    if max_uses is not None:
        payload["n"] = max(1, max_uses)
    return _encrypt_payload(payload, secret)


def decode_invite_payload(token_b64: str, secret: str) -> Optional[Dict[str, Any]]:
    """
    Descifra token y valida payload de canciones. Devuelve None si inválido o manipulado.
    El dict puede incluir "h" (duration_hours) si el enlace fue generado con duración en horas.
    """
    data = _decrypt_payload(token_b64, secret)
    if not data or data.get("t") != "songs":
        return None
    if not isinstance(data.get("c"), int) or data["c"] < 1 or data["c"] > 999:
        return None
    if "h" in data and (not isinstance(data["h"], int) or data["h"] < 1 or data["h"] > 87600):
        return None  # horas inválidas (máx 87600 = 10 años)
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
