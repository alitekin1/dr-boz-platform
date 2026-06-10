# Subscription Feature Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a global toggle in the Admin Panel to enable/disable all subscription-related features (purchasing, menu buttons, and discounted pricing logic).

**Architecture:** We add a `SubscriptionConfig` table to store global settings. The Admin API will expose endpoints to get and patch this config. The bot and the billing engine will check this config before proceeding with subscription logic.

**Tech Stack:** FastAPI, SQLAlchemy, React, Telegram Bot.

---

### Task 1: Backend Data Model and Schemas

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_subscription_config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_subscription_config.py
import pytest
from app.models import SubscriptionConfig

def test_subscription_config_model():
    config = SubscriptionConfig(is_enabled=False)
    assert config.is_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_subscription_config.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement model and schema**

```python
# backend/app/models.py
class SubscriptionConfig(Base):
    __tablename__ = "subscription_configs"
    id = Column(Integer, primary_key=True, index=True)
    is_enabled = Column(Boolean, default=True)
```

```python
# backend/app/schemas.py
class SubscriptionConfigOut(BaseModel):
    id: int
    is_enabled: bool
    model_config = ConfigDict(from_attributes=True)

class SubscriptionConfigUpdate(BaseModel):
    is_enabled: bool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_subscription_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/tests/test_subscription_config.py
git commit -m "feat: add SubscriptionConfig model and schemas"
```

---

### Task 2: Admin API Endpoints

**Files:**
- Modify: `backend/app/admin_subscription_routes.py`
- Test: `backend/tests/test_admin_subscriptions.py` (add to existing)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_admin_subscriptions.py (append)
@pytest.mark.asyncio
async def test_subscription_config_flow(admin_client):
    res = await admin_client.get("/api/admin/subscriptions/config")
    assert res.status_code == 200
    assert res.json()["is_enabled"] is True
    
    res = await admin_client.patch("/api/admin/subscriptions/config", json={"is_enabled": False})
    assert res.status_code == 200
    assert res.json()["is_enabled"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_admin_subscriptions.py -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement endpoints**

```python
# backend/app/admin_subscription_routes.py
from .models import SubscriptionConfig
from .schemas import SubscriptionConfigOut, SubscriptionConfigUpdate

async def _get_or_create_config(db: AsyncSession) -> SubscriptionConfig:
    res = await db.execute(select(SubscriptionConfig))
    config = res.scalars().first()
    if not config:
        config = SubscriptionConfig(is_enabled=True)
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config

@router.get("/config", response_model=SubscriptionConfigOut)
async def get_config(db: AsyncSession = Depends(get_session)):
    return await _get_or_create_config(db)

@router.patch("/config", response_model=SubscriptionConfigOut)
async def update_config(data: SubscriptionConfigUpdate, db: AsyncSession = Depends(get_session)):
    config = await _get_or_create_config(db)
    config.is_enabled = data.is_enabled
    await db.commit()
    await db.refresh(config)
    return config
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_admin_subscriptions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/admin_subscription_routes.py backend/tests/test_admin_subscriptions.py
git commit -m "feat: add admin API endpoints for subscription config"
```

---

### Task 3: Bot and Service Integration

**Files:**
- Modify: `backend/app/services/subscription_service.py`
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update `evaluate_usage_cost` service**

```python
# backend/app/services/subscription_service.py
from app.models import SubscriptionConfig

async def evaluate_usage_cost(...):
    # Add check at the very beginning
    config_res = await db.execute(select(SubscriptionConfig))
    config = config_res.scalars().first()
    if config and not config.is_enabled:
        return standard_cost_usd, False
    # ... rest of logic
```

- [ ] **Step 2: Update Bot `main_kb`**

```python
# backend/app/bot.py
async def _is_sub_enabled(db: AsyncSession) -> bool:
    from app.models import SubscriptionConfig
    res = await db.execute(select(SubscriptionConfig))
    cfg = res.scalars().first()
    return cfg.is_enabled if cfg else True

# Since main_kb is sync, we might need a workaround or make it async if possible.
# Given it's used everywhere, let's keep it sync but maybe hide button based on context if available,
# or simply update cmd_plans to say "Feature disabled".
```

- [ ] **Step 3: Update `cmd_plans` and `button_callback`**

Add check for `is_enabled` in `cmd_plans` and `confirm_buy_plan`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/subscription_service.py backend/app/bot.py
git commit -m "feat: respect subscription global toggle in bot and services"
```

---

### Task 4: Frontend UI Toggle

**Files:**
- Modify: `frontend-v2/src/lib/api.ts`
- Modify: `frontend-v2/src/lib/types.ts`
- Modify: `frontend-v2/src/components/config/SubscriptionList.tsx`

- [ ] **Step 1: Add API functions**

```typescript
// frontend-v2/src/lib/api.ts
export const getSubscriptionConfig = () => api.get('/admin/subscriptions/config').then(r => r.data);
export const updateSubscriptionConfig = (data: { is_enabled: boolean }) => api.patch('/admin/subscriptions/config', data).then(r => r.data);
```

- [ ] **Step 2: Add Toggle UI**

Add a Switch or Checkbox at the top of `SubscriptionList.tsx` to control the feature state.

- [ ] **Step 3: Commit**

```bash
git add frontend-v2/
git commit -m "feat: add subscription feature toggle to admin UI"
```
