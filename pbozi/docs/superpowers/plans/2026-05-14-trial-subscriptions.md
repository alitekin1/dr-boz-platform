# Trial Subscriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a trial subscription system that allows admins to offer a time-limited premium plan to users.

**Architecture:**
- **Backend:** `TrialConfig` model for settings, `trial_used` flag on `UserPreference`. API routes for config and manual granting. Logic integrated into the onboarding flow for automatic application.
- **Frontend:** New tab in Subscription settings for `TrialConfig`. "Grant Trial" button in UserTable.
- **Bot:** Telegram notification when a trial is activated.

**Tech Stack:** FastAPI, SQLAlchemy, React (Tailwind), lucide-react, python-telegram-bot.

---

### Task 1: Database Models & Migrations

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: Add TrialConfig model and trial_used field**
Add the `TrialConfig` model to `backend/app/models.py` and add `trial_used = Column(Boolean, default=False)` to the `UserPreference` model.

```python
class TrialConfig(Base):
    __tablename__ = "trial_configs"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    duration_hours = Column(Integer, default=48)
    is_enabled = Column(Boolean, default=False)
    apply_automatically = Column(Boolean, default=False)
    welcome_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    plan = relationship("SubscriptionPlan")
```

- [ ] **Step 2: Apply changes to DB**
Run a migration script or use the `apply_migrations.py` if available to add these fields/tables to the SQLite database.
Run: `cd backend && source venv/bin/activate && python apply_migrations.py` (assuming it handles dynamic model changes).

- [ ] **Step 3: Commit**
```bash
git add backend/app/models.py
git commit -m "db: add TrialConfig model and trial_used to UserPreference"
```

---

### Task 2: Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add TrialConfig schemas**
Add `TrialConfigOut` and `TrialConfigUpdate` schemas to `backend/app/schemas.py`.

```python
class TrialConfigOut(BaseModel):
    id: int
    plan_id: Optional[int]
    duration_hours: int
    is_enabled: bool
    apply_automatically: bool
    welcome_message: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True

class TrialConfigUpdate(BaseModel):
    plan_id: Optional[int] = None
    duration_hours: Optional[int] = None
    is_enabled: Optional[bool] = None
    apply_automatically: Optional[bool] = None
    welcome_message: Optional[str] = None
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/schemas.py
git commit -m "schema: add TrialConfig schemas"
```

---

### Task 3: Backend API - Admin Settings

**Files:**
- Modify: `backend/app/admin_routes.py`

- [ ] **Step 1: Add trial config endpoints**
Implement `GET /admin/trial-config` and `PATCH /admin/trial-config`.

```python
@router.get("/trial-config", response_model=TrialConfigOut)
async def get_trial_config(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(app_models.TrialConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        config = app_models.TrialConfig()
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config

@router.patch("/trial-config", response_model=TrialConfigOut)
async def update_trial_config(data: TrialConfigUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(app_models.TrialConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        config = app_models.TrialConfig()
        db.add(config)
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    
    await db.commit()
    await db.refresh(config)
    return config
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/admin_routes.py
git commit -m "feat: add admin trial config API"
```

---

### Task 4: Trial Granting Logic & Manual API

**Files:**
- Modify: `backend/app/admin_routes.py`
- Create: `backend/app/services/trial_service.py`

- [ ] **Step 1: Implement grant_trial logic**
Create `backend/app/services/trial_service.py` to handle the business logic of applying a trial.

```python
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import UserPreference, UserSubscription, TrialConfig, AdminAction
from app.services.codex_capacity_service import assign_subscription_pool

async def grant_trial_subscription(db: AsyncSession, user: UserPreference, admin_id: int | None = None) -> bool:
    if user.trial_used:
        return False
    
    result = await db.execute(select(TrialConfig).where(TrialConfig.is_enabled == True))
    config = result.scalar_one_or_none()
    if not config or not config.plan_id:
        return False

    # Check for existing active sub
    now = datetime.now(timezone.utc)
    existing = await db.execute(select(UserSubscription).where(
        UserSubscription.user_id == user.id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now
    ))
    if existing.scalar_one_or_none():
        return False

    subscription = UserSubscription(
        user_id=user.id,
        plan_id=config.plan_id,
        status="active",
        expires_at=now + timedelta(hours=config.duration_hours)
    )
    db.add(subscription)
    user.trial_used = True
    await db.flush()
    
    await assign_subscription_pool(db, subscription)
    
    # Send Telegram msg here later (Task 7)
    
    await db.commit()
    return True
```

- [ ] **Step 2: Add manual grant API route**
In `admin_routes.py`, add `POST /admin/users/{user_id}/grant-trial`.

- [ ] **Step 3: Commit**
```bash
git add backend/app/services/trial_service.py backend/app/admin_routes.py
git commit -m "feat: implement trial granting logic and API"
```

---

### Task 5: Frontend API & Settings UI

**Files:**
- Modify: `frontend-v2/src/lib/api.ts`
- Create: `frontend-v2/src/components/config/TrialSettings.tsx`
- Modify: `frontend-v2/src/components/config/SubscriptionList.tsx`

- [ ] **Step 1: Update frontend API client**
Add `getTrialConfig`, `updateTrialConfig`, and `grantTrial` to `api.ts`.

- [ ] **Step 2: Create TrialSettings component**
Build a form with Plan selection, hours input, and toggles.

- [ ] **Step 3: Add Tab to SubscriptionList**
Include the `TrialSettings` component in the Subscriptions page.

- [ ] **Step 4: Commit**
```bash
git add frontend-v2/src/lib/api.ts frontend-v2/src/components/config/TrialSettings.tsx
git commit -m "ui: add trial subscription settings"
```

---

### Task 6: Grant Button in User Table

**Files:**
- Modify: `frontend-v2/src/components/users/UserTable.tsx`

- [ ] **Step 1: Add "Grant Trial" button**
Add an action button in the UserTable row that calls `grantTrial`. Disable it if `user.trial_used` is true.

- [ ] **Step 2: Commit**
```bash
git add frontend-v2/src/components/users/UserTable.tsx
git commit -m "ui: add grant trial button to user table"
```

---

### Task 7: Automation & Notifications

**Files:**
- Modify: `backend/app/services/account_service.py`
- Modify: `backend/app/services/trial_service.py`

- [ ] **Step 1: Hook into signup**
Update `account_service.py` to call `grant_trial_subscription` automatically if `apply_automatically` is True.

- [ ] **Step 2: Implement Telegram Notification**
In `trial_service.py`, add logic to send the `welcome_message` via the Telegram bot.

- [ ] **Step 3: Commit**
```bash
git commit -am "feat: automate trial application and add notifications"
```
