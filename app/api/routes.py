from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.services.wol_service import WOLService

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
