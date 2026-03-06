from app.core.config import settings
from app.utils.network import ping
from app.utils.ssh import shutdown_pc
from app.core.logging import logger

class WOLService:
    @staticmethod
    def send_wol():
        try:
            from wakeonlan import send_magic_packet
            send_magic_packet(settings.PC_MAC, ip_address=settings.WOL_BROADCAST)
            logger.info(f"Sent WOL packet to {settings.PC_MAC}")
            return True
        except Exception as e:
            logger.error(f"Error sending WOL: {e}")
            return False

    @staticmethod
    async def get_pc_status():
        is_reachable = await ping(settings.PC_IP, timeout=settings.PING_TIMEOUT)
        return "online" if is_reachable else "offline"

    @staticmethod
    async def shutdown():
        return await shutdown_pc()
