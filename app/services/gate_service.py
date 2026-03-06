import asyncio
from app.core.logging import logger
from app.core.config import settings

class GateService:
    @staticmethod
    async def open_gate():
        """
        Simulate opening a gate (e.g. triggering a GPIO relay)
        """
        logger.info("Opening gate...")
        # Simulating relay pulse
        await asyncio.sleep(settings.GATE_OPEN_DURATION)
        logger.info("Gate opened (simulation complete).")
        return True
