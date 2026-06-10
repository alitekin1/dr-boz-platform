from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import List

from app.database import get_session
from app.models import Tip
from app.schemas import TipCreate, TipUpdate, TipOut
from app.admin_routes import verify_admin

router = APIRouter(prefix="/api/admin/tips", tags=["Admin Tips"])

@router.get("/", response_model=List[TipOut])
async def list_tips(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Tip))
    tips = result.scalars().all()
    return tips

@router.post("/", response_model=TipOut)
async def create_tip(tip_in: TipCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Tip).where(Tip.trigger_key == tip_in.trigger_key))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Trigger key already exists")
    new_tip = Tip(**tip_in.model_dump())
    db.add(new_tip)
    await db.commit()
    await db.refresh(new_tip)
    return new_tip

@router.put("/{tip_id}", response_model=TipOut)
async def update_tip(tip_id: int, tip_in: TipUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Tip).where(Tip.id == tip_id))
    tip = result.scalar_one_or_none()
    if not tip:
        raise HTTPException(status_code=404, detail="Tip not found")
    
    update_data = tip_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tip, key, value)
        
    await db.commit()
    await db.refresh(tip)
    return tip

@router.delete("/{tip_id}")
async def delete_tip(tip_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Tip).where(Tip.id == tip_id))
    tip = result.scalar_one_or_none()
    if not tip:
        raise HTTPException(status_code=404, detail="Tip not found")
    await db.delete(tip)
    await db.commit()
    return {"status": "ok"}

@router.get("/delivery-logs")
async def list_delivery_logs(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(text("""
        SELECT l.*, u.username, u.first_name, t.trigger_key 
        FROM tip_delivery_logs l
        JOIN user_preferences u ON l.user_id = u.id
        JOIN tips t ON l.tip_id = t.id
        ORDER BY l.delivered_at DESC
        LIMIT 200
    """))
    logs = [dict(row) for row in result.mappings().all()]
    return logs
