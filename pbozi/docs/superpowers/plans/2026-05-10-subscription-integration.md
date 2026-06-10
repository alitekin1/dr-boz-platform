# Subscription Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the subscription billing engine into the Admin API, Frontend UI, and Telegram Bot so users can view and purchase plans, and admins can configure them.

**Architecture:** We will create a dedicated `admin_subscription_routes.py` for CRUD operations on plans and rules, exposed under `/api/admin/subscriptions`. The React frontend will add a new tab and use Tailwind/Shadcn UI patterns to manage these. The bot will gain a new menu item for users to view and buy plans, and its cost logic will switch to using `evaluate_usage_cost`.

**Tech Stack:** FastAPI, Pydantic, React (TypeScript), `python-telegram-bot`.

---

### Task 1: Backend Admin API Schemas and Router

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/admin_subscription_routes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_admin_subscriptions.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_admin_subscriptions.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import Base, UserPreference

@pytest_asyncio.fixture
async def admin_client(db_session):
    admin_user = UserPreference(id=99, telegram_user_id=99, is_admin=True)
    db_session.add(admin_user)
    await db_session.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers={"x-telegram-user-id": "99"}) as ac:
        yield ac

@pytest.mark.asyncio
async def test_create_plan_flow(admin_client):
    res = await admin_client.post("/api/admin/subscriptions/plans", json={"name": "Pro", "monthly_price_usd": 15.0})
    assert res.status_code == 200
    plan_id = res.json()["id"]
    
    res = await admin_client.get("/api/admin/subscriptions/plans")
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "Pro"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_admin_subscriptions.py -v`
Expected: FAIL with 404 (Not Found)

- [ ] **Step 3: Write minimal implementation**

```python
# Append to backend/app/schemas.py
from typing import List, Optional

class SubscriptionPlanCreate(BaseModel):
    name: str
    monthly_price_usd: float
    is_active: bool = True

class SubscriptionPlanOut(SubscriptionPlanCreate):
    id: int
    class Config:
        orm_mode = True

class SubscriptionPlanRuleCreate(BaseModel):
    model_id: int
    free_chats_count: int
    free_tokens_per_chat: int
    discount_percent: float
    is_active: bool = True

class SubscriptionPlanRuleOut(SubscriptionPlanRuleCreate):
    id: int
    plan_id: int
    class Config:
        orm_mode = True
```

```python
# backend/app/admin_subscription_routes.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .database import get_db
from .models import SubscriptionPlan, SubscriptionPlanRule
from .schemas import SubscriptionPlanCreate, SubscriptionPlanOut, SubscriptionPlanRuleCreate, SubscriptionPlanRuleOut

router = APIRouter(prefix="/api/admin/subscriptions", tags=["Admin Subscriptions"])

@router.get("/plans", response_model=list[SubscriptionPlanOut])
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubscriptionPlan))
    return result.scalars().all()

@router.post("/plans", response_model=SubscriptionPlanOut)
async def create_plan(plan: SubscriptionPlanCreate, db: AsyncSession = Depends(get_db)):
    db_plan = SubscriptionPlan(**plan.model_dump())
    db.add(db_plan)
    await db.commit()
    await db.refresh(db_plan)
    return db_plan
```

```python
# Modify backend/app/main.py (add near other routers)
from app.admin_subscription_routes import router as admin_subscription_router
app.include_router(admin_subscription_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_admin_subscriptions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/admin_subscription_routes.py backend/app/main.py backend/tests/test_admin_subscriptions.py
git commit -m "feat: add admin subscription API endpoints"
```

### Task 2: Implement Plan Rules API Endpoints

**Files:**
- Modify: `backend/app/admin_subscription_routes.py`
- Modify: `backend/tests/test_admin_subscriptions.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_admin_subscriptions.py
from app.models import Model

@pytest.mark.asyncio
async def test_plan_rules_flow(admin_client, db_session):
    model = Model(id=1, name="gpt-4")
    db_session.add(model)
    await db_session.commit()
    
    res = await admin_client.post("/api/admin/subscriptions/plans", json={"name": "Ultra", "monthly_price_usd": 20.0})
    plan_id = res.json()["id"]
    
    res = await admin_client.post(f"/api/admin/subscriptions/plans/{plan_id}/rules", json={
        "model_id": 1,
        "free_chats_count": 5,
        "free_tokens_per_chat": 200000,
        "discount_percent": 50.0
    })
    assert res.status_code == 200
    rule_id = res.json()["id"]
    
    res = await admin_client.get(f"/api/admin/subscriptions/plans/{plan_id}/rules")
    assert len(res.json()) == 1
    assert res.json()[0]["free_chats_count"] == 5
    
    res = await admin_client.delete(f"/api/admin/subscriptions/rules/{rule_id}")
    assert res.status_code == 200
    res = await admin_client.get(f"/api/admin/subscriptions/plans/{plan_id}/rules")
    assert len(res.json()) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_admin_subscriptions.py::test_plan_rules_flow -v`
Expected: FAIL (404)

- [ ] **Step 3: Write minimal implementation**

```python
# Append to backend/app/admin_subscription_routes.py

@router.get("/plans/{plan_id}/rules", response_model=list[SubscriptionPlanRuleOut])
async def list_rules(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubscriptionPlanRule).where(SubscriptionPlanRule.plan_id == plan_id))
    return result.scalars().all()

@router.post("/plans/{plan_id}/rules", response_model=SubscriptionPlanRuleOut)
async def create_rule(plan_id: int, rule: SubscriptionPlanRuleCreate, db: AsyncSession = Depends(get_db)):
    db_rule = SubscriptionPlanRule(**rule.model_dump(), plan_id=plan_id)
    db.add(db_rule)
    await db.commit()
    await db.refresh(db_rule)
    return db_rule

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SubscriptionPlanRule).where(SubscriptionPlanRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule:
        await db.delete(rule)
        await db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_admin_subscriptions.py::test_plan_rules_flow -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/admin_subscription_routes.py backend/tests/test_admin_subscriptions.py
git commit -m "feat: add admin subscription rules API"
```

### Task 3: Frontend API Client

**Files:**
- Modify: `frontend-v2/src/lib/api.ts`
- Modify: `frontend-v2/src/lib/types.ts`

- [ ] **Step 1: Write type definitions**

```typescript
// Append to frontend-v2/src/lib/types.ts
export interface SubscriptionPlan {
  id: number;
  name: string;
  monthly_price_usd: number;
  is_active: boolean;
}

export interface SubscriptionPlanCreate {
  name: string;
  monthly_price_usd: number;
  is_active: boolean;
}

export interface SubscriptionPlanRule {
  id: number;
  plan_id: number;
  model_id: number;
  free_chats_count: number;
  free_tokens_per_chat: number;
  discount_percent: number;
  is_active: boolean;
}

export interface SubscriptionPlanRuleCreate {
  model_id: number;
  free_chats_count: number;
  free_tokens_per_chat: number;
  discount_percent: number;
  is_active: boolean;
}
```

- [ ] **Step 2: Add api functions**

```typescript
// Append to frontend-v2/src/lib/api.ts (and import new types at the top)
export const getSubscriptionPlans = () => fetchAPI<SubscriptionPlan[]>('/admin/subscriptions/plans');
export const createSubscriptionPlan = (data: SubscriptionPlanCreate) => fetchAPI<SubscriptionPlan>('/admin/subscriptions/plans', { method: 'POST', body: JSON.stringify(data) });
export const getSubscriptionPlanRules = (planId: number) => fetchAPI<SubscriptionPlanRule[]>(`/admin/subscriptions/plans/${planId}/rules`);
export const createSubscriptionPlanRule = (planId: number, data: SubscriptionPlanRuleCreate) => fetchAPI<SubscriptionPlanRule>(`/admin/subscriptions/plans/${planId}/rules`, { method: 'POST', body: JSON.stringify(data) });
export const deleteSubscriptionPlanRule = (ruleId: number) => fetchAPI<{ok: boolean}>(`/admin/subscriptions/rules/${ruleId}`, { method: 'DELETE' });
```

- [ ] **Step 3: Run typescript check**

Run: `cd frontend-v2 && npm run typecheck` (or `npx tsc --noEmit`)
Expected: No errors related to our changes.

- [ ] **Step 4: Commit**

```bash
git add frontend-v2/src/lib/types.ts frontend-v2/src/lib/api.ts
git commit -m "feat: add frontend api client for subscriptions"
```

### Task 4: Frontend Subscriptions Tab

**Files:**
- Create: `frontend-v2/src/components/config/SubscriptionList.tsx`
- Modify: `frontend-v2/src/App.tsx` (or wherever tabs are defined, maybe `AdminLayout.tsx` or `ConfigPage.tsx`)

- [ ] **Step 1: Create minimal UI**

```tsx
// frontend-v2/src/components/config/SubscriptionList.tsx
import { useEffect, useState } from 'react';
import { getSubscriptionPlans, SubscriptionPlan } from '../../lib/api';

export function SubscriptionList() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  
  useEffect(() => {
    getSubscriptionPlans().then(setPlans).catch(console.error);
  }, []);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">اشتراک‌ها</h2>
      <div className="grid gap-4">
        {plans.map(p => (
          <div key={p.id} className="p-4 border rounded shadow-sm">
            <h3 className="font-semibold">{p.name}</h3>
            <p>${p.monthly_price_usd} / month</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add it to routing/tabs**

Find where `ModelList` or `ProviderList` is rendered (e.g. `ConfigView.tsx` or `App.tsx`), and add a tab for "اشتراک‌ها" pointing to `<SubscriptionList />`.

- [ ] **Step 3: Build to verify**

Run: `cd frontend-v2 && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend-v2/
git commit -m "feat: add basic frontend subscriptions tab"
```

### Task 5: Telegram Bot - Expose Plans

**Files:**
- Modify: `backend/app/bot.py`
- Modify: `backend/app/admin_subscription_routes.py` (Add a public endpoint to get plans, or fetch via bot directly via DB)

- [ ] **Step 1: Write DB query for active plans**

```python
# In backend/app/bot.py
async def _get_active_subscription_plans(db: AsyncSession):
    from app.models import SubscriptionPlan
    res = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_active == True))
    return res.scalars().all()
```

- [ ] **Step 2: Add bot handler for Plans**

```python
# In backend/app/bot.py, add near cmd_profile:
async def cmd_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        plans = await _get_active_subscription_plans(db)
        if not plans:
            await update.message.reply_text("در حال حاضر هیچ اشتراکی فعال نیست.")
            return
            
        text = "💎 اشتراک‌های ویژه:\n\n"
        for p in plans:
            text += f"▪️ {p.name} - ${p.monthly_price_usd}/ماه\n"
        
        await update.message.reply_text(text)
        
# Register it in `start_bot`:
app.add_handler(MessageHandler(filters.Regex("^💎 اشتراک‌ها$"), cmd_plans))
```

- [ ] **Step 3: Add to Reply Keyboard**

Modify `_main_keyboard()` or the profile keyboard in `bot.py` to include `"💎 اشتراک‌ها"`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/bot.py
git commit -m "feat: add plans bot command"
```

### Task 6: Cost Engine Replacement in Bot

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Replace synchronous `_chat_completion_cost_usd`**

Find instances of `_chat_completion_cost_usd(model, input, output)`.
Replace with:
```python
from app.services.subscription_service import evaluate_usage_cost
# Inside async handlers:
standard_cost = _chat_completion_cost_usd(model, input, output) # keep this for standard reference
actual_cost_usd, is_discounted = await evaluate_usage_cost(
    db, user.id, model.id, chat.id if chat else 0, standard_cost, input, output
)
```

- [ ] **Step 2: Fix tests**

Run: `cd backend && source venv/bin/activate && pytest`
Fix any tests that break due to async changes in billing.

- [ ] **Step 3: Commit**

```bash
git add backend/app/bot.py
git commit -m "feat: use new evaluate_usage_cost engine in bot"
```
