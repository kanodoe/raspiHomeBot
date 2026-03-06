import asyncio
import platform

async def ping(ip: str, timeout: int = 2) -> bool:
    """
    Returns True if ip responds to a ping request.
    """
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
    # timeout in ms for windows, seconds for linux
    t = timeout * 1000 if platform.system().lower() == 'windows' else timeout

    command = ['ping', param, '1', timeout_param, str(t), ip]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await process.wait()
    return process.returncode == 0
