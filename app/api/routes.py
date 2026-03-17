from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.services.wol_service import WOLService
from app.services.log_service import LogService
from app.core.config import settings

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.get("/status")
async def get_status():
    pc_status = await WOLService.get_pc_status()
    return {
        "pc": pc_status,
        "system": "operational"
    }

@router.post("/pc/on")
async def pc_on():
    success = WOLService.send_wol()
    if success:
        return {"message": "WOL packet sent"}
    raise HTTPException(status_code=500, detail="Failed to send WOL packet")

@router.post("/pc/off")
async def pc_off():
    success = await WOLService.shutdown()
    if success:
        return {"message": "Shutdown command sent"}
    raise HTTPException(status_code=500, detail="Failed to send shutdown command")


@router.post("/api/gate/open")
async def gate_open_proxy(request: Request, authorization: str | None = Header(default=None)):
    """Proxy para abrir el portón: el bot de portón envía POST con secreto; este proceso publica en el bus o abre."""
    try:
        body = await request.json() if request.method == "POST" else {}
    except Exception:
        body = {}
    body_secret = body.get("secret") if isinstance(body, dict) else None
    expected = getattr(settings, "GATE_PROXY_SECRET", None) or ""
    if not expected:
        raise HTTPException(status_code=501, detail="Gate proxy not configured")
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif body_secret is not None:
        token = str(body_secret)
    else:
        raise HTTPException(status_code=401, detail="Missing secret")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid secret")
    bus = getattr(request.app.state, "bus", None)
    if bus:
        await bus.publish("command", {"command": "gate_open", "source": "api_gate_proxy"})
        return {"message": "Gate open command sent"}
    from app.services.gate_service import GateService
    await GateService.open_gate()
    return {"message": "Gate opened"}

@router.get("/logs")
async def list_logs():
    """Lista los archivos de log de respaldo existentes."""
    logs = LogService.list_logs()
    return {"logs": logs}

@router.get("/logs/{filename}")
async def download_log(filename: str):
    """Permite descargar un archivo de log comprimido."""
    file_path = LogService.get_log_path(filename)
    if not file_path:
        raise HTTPException(status_code=404, detail="Log file not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/zip'
    )
