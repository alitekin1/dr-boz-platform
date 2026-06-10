import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_session
from app.models import ReferralCampaign, ReferralEvent, UserPreference
from app.schemas import ReferralCampaignCreate, ReferralStatsOut, ReferralCampaignOut
from app.admin_routes import verify_admin

router = APIRouter(prefix="/admin/referrals", tags=["admin-referrals"])

@router.post("", response_model=ReferralCampaignOut)
async def create_campaign(
    payload: ReferralCampaignCreate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    code = f"ref_{uuid.uuid4().hex[:8]}"
    campaign = ReferralCampaign(
        code=code,
        description=payload.description,
        is_active=True
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign

@router.get("", response_model=List[ReferralStatsOut])
async def list_campaigns(
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    campaigns = (await db.execute(select(ReferralCampaign).order_by(ReferralCampaign.created_at.desc()))).scalars().all()
    results = []
    for c in campaigns:
        events = (await db.execute(select(ReferralEvent).where(ReferralEvent.campaign_id == c.id))).scalars().all()
        starts = sum(1 for e in events if e.event_type == 'start')
        signups = sum(1 for e in events if e.event_type == 'signup')
        purchases = sum(1 for e in events if e.event_type == 'purchase')
        revenue = sum(e.amount_usd for e in events if e.event_type == 'purchase' and e.amount_usd is not None)
        
        results.append(ReferralStatsOut(
            campaign=ReferralCampaignOut.model_validate(c),
            starts=starts,
            signups=signups,
            purchases=purchases,
            revenue_usd=revenue
        ))
    return results