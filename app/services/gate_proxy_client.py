"""
Cliente para notificar al proxy del portón (otro bot/servicio) cuando un invitado
solicita abrir el portón. El proxy recibe la petición como si fuera del admin y abre el portón.
"""
import httpx
from typing import Optional

from app.core.logging import logger


async def request_gate_open(
    proxy_url: str,
    secret: str,
    *,
    guest_telegram_id: Optional[int] = None,
    admin_telegram_id: Optional[int] = None,
) -> bool:
    """
    Envía POST al proxy del portón con el secreto. El proxy debe abrir el portón
    (p. ej. enviando la orden al bot del portón como si fuera el admin).
    Devuelve True si el proxy respondió 2xx.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                proxy_url.rstrip("/"),
                json={
                    "secret": secret,
                    "guest_telegram_id": guest_telegram_id,
                    "admin_telegram_id": admin_telegram_id,
                },
            )
            if r.is_success:
                return True
            logger.warning(f"Gate proxy returned {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        logger.warning(f"Gate proxy request failed: {e}")
        return False
