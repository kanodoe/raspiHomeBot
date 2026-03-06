from app.core.config import settings
from app.core.logging import logger

async def shutdown_pc():
    try:
        import asyncssh
        async with asyncssh.connect(
            settings.PC_IP,
            username=settings.SSH_USER,
            client_keys=[settings.SSH_KEY_PATH],
            known_hosts=None # In a real production environment, you should use known_hosts
        ) as conn:
            # For Windows PC use: 'shutdown /s /t 0'
            # For Linux PC use: 'sudo shutdown -h now'
            # We will try a generic approach or depend on config if needed
            result = await conn.run('shutdown /s /t 0', check=False)
            if result.exit_status != 0:
                # Try Linux shutdown
                await conn.run('sudo shutdown -h now', check=False)
            return True
    except Exception as e:
        logger.error(f"SSH shutdown error: {e}")
        return False
