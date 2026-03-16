from app.core.config import settings
from app.core.logging import logger

async def shutdown_pc():
    return await run_ssh_command("shutdown /s /t 0") or await run_ssh_command("sudo shutdown -h now")

async def run_ssh_command(command: str, host: str = None) -> bool:
    """
    Runs a command on a remote PC via SSH.
    If host is None, uses settings.PC_IP.
    """
    if host is None or host in ("localhost", "127.0.0.1", "0.0.0.0"):
        host = settings.PC_IP
        
    try:
        import asyncssh
        async with asyncssh.connect(
            host,
            username=settings.SSH_USER,
            client_keys=[settings.SSH_KEY_PATH],
            known_hosts=None
        ) as conn:
            result = await conn.run(command, check=False)
            if result.exit_status == 0:
                logger.info(f"SSH command executed successfully on {host}: {command}")
                return True
            else:
                logger.error(f"SSH command failed on {host} ({result.exit_status}): {result.stderr}")
                return False
    except Exception as e:
        logger.error(f"SSH error on {host} executing '{command}': {e}")
        return False
