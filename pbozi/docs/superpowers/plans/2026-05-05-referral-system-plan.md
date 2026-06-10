# Referral System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an event-driven referral link tracking system to log start, signup, and purchase events with exact timestamps.

**Architecture:** We add `ReferralCampaign` and `ReferralEvent` tables. We modify the telegram `/start` command, the onboarding flow, and the wallet top-up logic to insert events. Finally, we add FastAPI admin endpoints to view the aggregated stats.

**Tech Stack:** Python, FastAPI, SQLAlchemy (Async), python-telegram-bot

---

### Task 1: Database Models

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Write DB Models**
Add the new models to `backend/app/models.py`:
```python
class ReferralCampaign(Base):
    __tablename__ = "referral_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_by_admin_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    events = relationship("ReferralEvent", back_populates="campaign", cascade="all, delete-orphan")
    users = relationship("UserPreference", back_populates="referral_campaign")

class ReferralEvent(Base):
    __tablename__ = "referral_events"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("referral_campaigns.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True) # 'start', 'signup', 'purchase'
    amount_usd = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    campaign = relationship("ReferralCampaign", back_populates="events")
    user = relationship("UserPreference")
```
Also in `UserPreference`, add:
```python
    referral_campaign_id = Column(Integer, ForeignKey("referral_campaigns.id"), nullable=True, index=True)
    referral_campaign = relationship("ReferralCampaign", back_populates="users")
```

- [ ] **Step 2: Add Pydantic Schemas**
In `backend/app/schemas.py`:
```python
class ReferralCampaignCreate(BaseModel):
    description: Optional[str] = None

class ReferralCampaignOut(BaseModel):
    id: int
    code: str
    description: Optional[str]
    created_by_admin_id: Optional[int]
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class ReferralStatsOut(BaseModel):
    campaign: ReferralCampaignOut
    starts: int
    signups: int
    purchases: int
    revenue_usd: float
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/models.py backend/app/schemas.py
git commit -m "feat: add referral system database models and schemas"
```

---

### Task 2: Admin Endpoints

**Files:**
- Create: `backend/app/admin_referral_routes.py`
- Modify: `backend/app/main.py` (to include the new router)

- [ ] **Step 1: Write admin endpoints**
Create `backend/app/admin_referral_routes.py`:
```python
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_session
from app.models import ReferralCampaign, ReferralEvent, UserPreference
from app.schemas import ReferralCampaignCreate, ReferralStatsOut, ReferralCampaignOut

router = APIRouter(prefix="/admin/referrals", tags=["admin-referrals"])

@router.post("", response_model=ReferralCampaignOut)
async def create_campaign(
    payload: ReferralCampaignCreate,
    db: AsyncSession = Depends(get_session)
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
async def list_campaigns(db: AsyncSession = Depends(get_session)):
    campaigns = (await db.execute(select(ReferralCampaign).order_by(ReferralCampaign.created_at.desc()))).scalars().all()
    results = []
    for c in campaigns:
        events = (await db.execute(select(ReferralEvent).where(ReferralEvent.campaign_id == c.id))).scalars().all()
        starts = sum(1 for e in events if e.event_type == 'start')
        signups = sum(1 for e in events if e.event_type == 'signup')
        purchases = sum(1 for e in events if e.event_type == 'purchase')
        revenue = sum(e.amount_usd for e in events if e.event_type == 'purchase' and e.amount_usd)
        
        results.append(ReferralStatsOut(
            campaign=ReferralCampaignOut.model_validate(c),
            starts=starts,
            signups=signups,
            purchases=purchases,
            revenue_usd=revenue
        ))
    return results
```

- [ ] **Step 2: Include Router in main.py**
In `backend/app/main.py`, add:
```python
from app.admin_referral_routes import router as admin_referral_router
# ... inside setup_app or where routers are included
app.include_router(admin_referral_router)
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/admin_referral_routes.py backend/app/main.py
git commit -m "feat: add admin referral endpoints"
```

---

### Task 3: Bot `cmd_start` Tracking

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Modify `cmd_start` to detect referrals**
In `backend/app/bot.py`, find `cmd_start` and add logic to handle `ref_` links:
```python
# add to imports if not there: from app.models import ReferralCampaign, ReferralEvent
        if payload.startswith("ref_"):
            token = payload.strip()
            campaign = (await db.execute(select(ReferralCampaign).where(ReferralCampaign.code == token))).scalar_one_or_none()
            if campaign:
                # Set referral_campaign_id if it's a new user or not set yet
                if not user.referral_campaign_id:
                    user.referral_campaign_id = campaign.id
                
                # Log the 'start' event
                event = ReferralEvent(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    event_type="start"
                )
                db.add(event)
                await db.commit()
            
            # Continue normal start flow...
```
*(Insert this right after checking `if payload.startswith(GROUP_OPTIN_START_PREFIX):` block)*

- [ ] **Step 2: Commit**
```bash
git add backend/app/bot.py
git commit -m "feat: track referral start events in bot"
```

---

### Task 4: Bot Onboarding `signup` Tracking

**Files:**
- Modify: `backend/app/bot.py` (or wherever onboarding completes)

- [ ] **Step 1: Track `signup` events**
In `backend/app/bot.py`, find `_mark_onboarding_complete` and modify it. Since it currently just does:
```python
def _mark_onboarding_complete(user: UserPreference):
    # ...
    user.account_status = "active"
```
It might not have DB session access. We need to find where onboarding ACTUALLY finishes (e.g. `handle_contact` or `_ensure_onboarding_or_prompt`) and insert the event.
Alternatively, in `_mark_onboarding_complete`, check if we can pass the DB session, or we do it inside the endpoint/handler that saves the user state:
In `backend/app/bot.py` where `_user_onboarding_completed` goes from False to True, or specifically in `handle_contact` or `account_set_name` callbacks.

Actually, let's create a helper in `bot.py` called `_log_referral_event`:
```python
async def _log_referral_event(db: AsyncSession, user: UserPreference, event_type: str, amount_usd: float = None):
    if user.referral_campaign_id:
        event = ReferralEvent(
            campaign_id=user.referral_campaign_id,
            user_id=user.id,
            event_type=event_type,
            amount_usd=amount_usd
        )
        db.add(event)
        await db.commit()
```

Then, hook into `handle_contact` and `button_callback` where name is set. A better place is when `account_status` actually updates to "active" in the DB.
Let's hook it when `user.account_status` changes to "active". 
In `handle_contact` (bot.py):
```python
            was_pending = not _user_onboarding_completed(user)
            # existing contact saving logic...
            if was_pending and _user_onboarding_completed(user):
                await _log_referral_event(db, user, "signup")
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/bot.py
git commit -m "feat: track referral signup events"
```

---

### Task 5: Top-up `purchase` Tracking

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Track `purchase` events**
In `backend/app/bot.py`, find `_apply_topup_credit`:
```python
async def _apply_topup_credit(
    db: AsyncSession,
    *,
    user: UserPreference,
    usd_amount: Decimal,
    idempotency_key: str,
    metadata: dict | None = None,
) -> tuple[bool, float]:
    # ... existing code ...
    db.add(entry)
    
    # ADD THIS:
    if user.referral_campaign_id:
        ref_event = ReferralEvent(
            campaign_id=user.referral_campaign_id,
            user_id=user.id,
            event_type="purchase",
            amount_usd=float(usd_amount)
        )
        db.add(ref_event)

    await db.commit()
    await db.refresh(user)
    return True, _credit_balance(user)
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/bot.py
git commit -m "feat: track referral purchase events"
```

---

### Task 6: Tests

**Files:**
- Create: `backend/tests/test_referrals.py`

- [ ] **Step 1: Write integration tests**
```python
import pytest
from httpx import AsyncClient
from app.models import ReferralCampaign, UserPreference, ReferralEvent

@pytest.mark.asyncio
async def test_referral_flow(async_client: AsyncClient, db_session):
    # Create campaign
    response = await async_client.post("/admin/referrals", json={"description": "Test Ad"})
    assert response.status_code == 200
    campaign = response.json()
    assert campaign["code"].startswith("ref_")
    
    # ... verify DB insertion ...
```
(Include basic tests ensuring the endpoints return 200 and schema matches).

- [ ] **Step 2: Commit**
```bash
git add backend/tests/test_referrals.py
git commit -m "test: add referral system tests"
```
