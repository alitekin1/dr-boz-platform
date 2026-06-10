# Subscription Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a subscription-based pricing model that allows users to buy plans offering free chat slots and discounted token rates, managed via pre-allocated quotas.

**Architecture:** We add four new models (`SubscriptionPlan`, `SubscriptionPlanRule`, `UserSubscription`, `UserSubscriptionQuota`). When a user purchases a plan, we debit their balance and populate their quotas. During chat completion, we check their quota to determine if the chat is free (and update its token bucket) or calculate the cost using their discounted rate.

**Tech Stack:** FastAPI, SQLAlchemy, async asyncpg, pytest, SQLite for tests.

---

### Task 1: Add Database Models

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/check_db_models.py` (or create a script to test creation)
- Test: `backend/test_subscription_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/test_subscription_models.py
import pytest
from datetime import datetime, timezone, timedelta
from app.models import SubscriptionPlan, SubscriptionPlanRule, UserSubscription, UserSubscriptionQuota

def test_subscription_models_exist():
    plan = SubscriptionPlan(name="Pro", monthly_price_usd=10.0)
    rule = SubscriptionPlanRule(free_chats_count=2, free_tokens_per_chat=100000, discount_percent=75.0)
    sub = UserSubscription(status="active", expires_at=datetime.now(timezone.utc) + timedelta(days=30))
    quota = UserSubscriptionQuota(free_chats_remaining=2, discount_percent=75.0)
    assert plan.name == "Pro"
    assert rule.discount_percent == 75.0
    assert sub.status == "active"
    assert quota.free_chats_remaining == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/test_subscription_models.py -v`
Expected: FAIL with "ImportError" or "NameError" for the models.

- [ ] **Step 3: Write minimal implementation**

```python
# Append to backend/app/models.py
class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    monthly_price_usd = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class SubscriptionPlanRule(Base):
    __tablename__ = "subscription_plan_rules"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False, index=True)
    free_chats_count = Column(Integer, default=0)
    free_tokens_per_chat = Column(Integer, default=0)
    discount_percent = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

    plan = relationship("SubscriptionPlan", backref="rules")
    model = relationship("Model")

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False, index=True)
    status = Column(String, default="active", index=True)
    purchased_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False, index=True)

    user = relationship("UserPreference", backref="subscriptions")
    plan = relationship("SubscriptionPlan")

class UserSubscriptionQuota(Base):
    __tablename__ = "user_subscription_quotas"
    id = Column(Integer, primary_key=True, index=True)
    user_subscription_id = Column(Integer, ForeignKey("user_subscriptions.id"), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False, index=True)
    free_chats_remaining = Column(Integer, default=0)
    chat_token_quotas_json = Column(JSON, nullable=True) # {chat_id: tokens_remaining}
    discount_percent = Column(Float, default=0.0)

    user_subscription = relationship("UserSubscription", backref="quotas")
    model = relationship("Model")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/test_subscription_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/test_subscription_models.py backend/app/models.py
git commit -m "feat: add subscription database models"
```

### Task 2: Implement Subscription Service Purchase Logic

**Files:**
- Create: `backend/app/services/subscription_service.py`
- Test: `backend/test_subscription_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/test_subscription_service.py
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models import Base, UserPreference, SubscriptionPlan, SubscriptionPlanRule, Model
from app.services.subscription_service import purchase_subscription

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine)
    async with Session() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_purchase_subscription(db_session):
    user = UserPreference(id=1, credit_balance_usd=20.0)
    plan = SubscriptionPlan(id=1, name="Pro", monthly_price_usd=10.0)
    model = Model(id=1, name="gpt-4")
    rule = SubscriptionPlanRule(plan_id=1, model_id=1, free_chats_count=2, free_tokens_per_chat=1000, discount_percent=75.0)
    db_session.add_all([user, plan, model, rule])
    await db_session.commit()
    
    result = await purchase_subscription(db_session, user, plan)
    
    assert result.ok is True
    assert user.credit_balance_usd == 10.0
    assert result.subscription.status == "active"
    assert len(result.subscription.quotas) == 1
    assert result.subscription.quotas[0].free_chats_remaining == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/test_subscription_service.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/subscription_service.py
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import UserPreference, SubscriptionPlan, SubscriptionPlanRule, UserSubscription, UserSubscriptionQuota
from app.services.wallet_service import debit_usd

@dataclass
class PurchaseResult:
    ok: bool
    subscription: UserSubscription | None = None
    error: str | None = None

async def purchase_subscription(db: AsyncSession, user: UserPreference, plan: SubscriptionPlan) -> PurchaseResult:
    debit_result = await debit_usd(db, user=user, amount_usd=plan.monthly_price_usd, entry_type="subscription_purchase", reason=f"Purchased {plan.name}")
    if not debit_result.ok:
        return PurchaseResult(ok=False, error="insufficient_credit")
        
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    subscription = UserSubscription(user_id=user.id, plan_id=plan.id, status="active", expires_at=expires_at)
    db.add(subscription)
    await db.flush()
    
    rules = (await db.execute(select(SubscriptionPlanRule).where(SubscriptionPlanRule.plan_id == plan.id))).scalars().all()
    
    quotas = []
    for rule in rules:
        quota = UserSubscriptionQuota(
            user_subscription_id=subscription.id,
            model_id=rule.model_id,
            free_chats_remaining=rule.free_chats_count,
            chat_token_quotas_json={},
            discount_percent=rule.discount_percent
        )
        db.add(quota)
        quotas.append(quota)
        
    await db.commit()
    await db.refresh(subscription)
    subscription.quotas = quotas
    return PurchaseResult(ok=True, subscription=subscription)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/test_subscription_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/test_subscription_service.py backend/app/services/subscription_service.py
git commit -m "feat: implement subscription purchase logic"
```

### Task 3: Implement Pricing Evaluation Logic

**Files:**
- Modify: `backend/app/services/subscription_service.py`
- Modify: `backend/test_subscription_service.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/test_subscription_service.py
from app.services.subscription_service import evaluate_usage_cost

@pytest.mark.asyncio
async def test_evaluate_usage_cost_free_chat(db_session):
    user = UserPreference(id=1)
    plan = SubscriptionPlan(id=1)
    sub = UserSubscription(id=1, user_id=1, plan_id=1, status="active", expires_at=datetime.now(timezone.utc) + timedelta(days=10))
    quota = UserSubscriptionQuota(id=1, user_subscription_id=1, model_id=1, free_chats_remaining=1, chat_token_quotas_json={}, discount_percent=75.0)
    db_session.add_all([user, plan, sub, quota])
    await db_session.commit()
    
    # First request: consumes 1000 tokens, standard cost is 0.1, but should be 0 because of free chat
    cost, charged = await evaluate_usage_cost(db_session, user.id, model_id=1, chat_id=100, standard_cost_usd=0.1, input_tokens=500, output_tokens=500, free_tokens_per_chat=100000)
    
    assert cost == 0.0
    await db_session.refresh(quota)
    assert quota.free_chats_remaining == 0
    assert quota.chat_token_quotas_json == {"100": 99000}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/test_subscription_service.py::test_evaluate_usage_cost_free_chat -v`
Expected: FAIL with "ImportError" for evaluate_usage_cost.

- [ ] **Step 3: Write minimal implementation**

```python
# Append to backend/app/services/subscription_service.py
async def evaluate_usage_cost(
    db: AsyncSession, 
    user_id: int, 
    model_id: int, 
    chat_id: int, 
    standard_cost_usd: float, 
    input_tokens: int, 
    output_tokens: int, 
    free_tokens_per_chat: int = 100000
) -> tuple[float, bool]:
    # Returns (final_cost_usd, is_discounted)
    now = datetime.now(timezone.utc)
    sub_query = select(UserSubscriptionQuota).join(UserSubscription).where(
        UserSubscription.user_id == user_id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now,
        UserSubscriptionQuota.model_id == model_id
    )
    quota = (await db.execute(sub_query)).scalar_one_or_none()
    
    if not quota:
        return standard_cost_usd, False
        
    chat_str = str(chat_id)
    quotas_json = quota.chat_token_quotas_json or {}
    total_tokens = input_tokens + output_tokens
    
    if chat_str in quotas_json:
        remaining = quotas_json[chat_str]
        if total_tokens <= remaining:
            quotas_json[chat_str] = remaining - total_tokens
            quota.chat_token_quotas_json = quotas_json
            db.add(quota)
            await db.commit()
            return 0.0, True
        else:
            # Consumed the rest, charge the remainder at discount
            excess_tokens = total_tokens - remaining
            excess_ratio = excess_tokens / total_tokens if total_tokens > 0 else 0
            base_cost_for_excess = standard_cost_usd * excess_ratio
            quotas_json[chat_str] = 0
            quota.chat_token_quotas_json = quotas_json
            db.add(quota)
            await db.commit()
            discounted_cost = base_cost_for_excess * (1.0 - (quota.discount_percent / 100.0))
            return discounted_cost, True
            
    elif quota.free_chats_remaining > 0:
        quota.free_chats_remaining -= 1
        remaining = max(0, free_tokens_per_chat - total_tokens)
        quotas_json[chat_str] = remaining
        quota.chat_token_quotas_json = quotas_json
        db.add(quota)
        await db.commit()
        if total_tokens <= free_tokens_per_chat:
            return 0.0, True
        else:
            excess_tokens = total_tokens - free_tokens_per_chat
            excess_ratio = excess_tokens / total_tokens
            base_cost = standard_cost_usd * excess_ratio
            discounted = base_cost * (1.0 - (quota.discount_percent / 100.0))
            return discounted, True
            
    else:
        # No free chats, apply discount
        discounted = standard_cost_usd * (1.0 - (quota.discount_percent / 100.0))
        return discounted, True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/test_subscription_service.py::test_evaluate_usage_cost_free_chat -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/subscription_service.py backend/test_subscription_service.py
git commit -m "feat: implement subscription pricing evaluation logic"
```
