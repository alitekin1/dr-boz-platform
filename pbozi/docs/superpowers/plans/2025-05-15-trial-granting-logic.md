# Trial Granting Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement manual trial granting logic and an admin API endpoint.

**Architecture:** Business logic is encapsulated in `TrialService`, and exposed via `admin_routes.py`. Uses existing `UserPreference`, `TrialConfig`, and `UserSubscription` models.

**Tech Stack:** FastAPI, SQLAlchemy (Async), Pydantic.

---

### Task 1: Implement TrialService

**Files:**
- Create: `backend/app/services/trial_service.py`

- [ ] **Step 1: Write `TrialService` with `grant_trial_subscription` method**

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import UserPreference, TrialConfig, UserSubscription, AdminAction
import app.models as models

class TrialServiceError(Exception):
    pass

class TrialService:
    @staticmethod
    async def grant_trial_subscription(db: AsyncSession, user_id: int) -> UserSubscription:
        # 1. Fetch user
        result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise TrialServiceError("User not found")

        # 2. Check if trial used
        if user.trial_used:
            raise TrialServiceError("User has already used a trial")

        # 3. Fetch trial config
        result = await db.execute(select(TrialConfig).limit(1))
        config = result.scalar_one_or_none()
        if not config or not config.is_enabled or not config.plan_id:
            raise TrialServiceError("Trial configuration is not enabled or missing plan_id")

        # 4. Check for active subscriptions
        sub_result = await db.execute(
            select(UserSubscription)
            .where(UserSubscription.user_id == user.id, UserSubscription.status == "active")
            .limit(1)
        )
        if sub_result.scalar_one_or_none():
            raise TrialServiceError("User already has an active subscription")

        # 5. Create subscription
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=config.duration_hours)
        
        subscription = UserSubscription(
            user_id=user.id,
            plan_id=config.plan_id,
            status="active",
            purchased_at=now,
            expires_at=expires_at
        )
        db.add(subscription)
        
        # 6. Update user
        user.trial_used = True
        
        # 7. Record admin action
        admin_action = AdminAction(
            action_type="grant_trial",
            target_type="user",
            target_id=user.id,
            after_json={"subscription_plan_id": config.plan_id, "expires_at": expires_at.isoformat()},
            reason="Admin manually granted trial"
        )
        db.add(admin_action)
        
        await db.commit()
        await db.refresh(subscription)
        return subscription
```

- [ ] **Step 2: Commit changes**

```bash
git add backend/app/services/trial_service.py
git commit -m "feat: implement TrialService for manual trial granting"
```

---

### Task 2: Add Admin API Route

**Files:**
- Modify: `backend/app/admin_routes.py`

- [ ] **Step 1: Add the route to `admin_routes.py`**

```python
# Add import at the top
from app.services.trial_service import TrialService, TrialServiceError

# ... near other user-related routes ...

@router.post("/users/{user_id}/grant-trial")
async def grant_trial(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    try:
        subscription = await TrialService.grant_trial_subscription(db, user_id)
        return {
            "ok": True,
            "subscription_id": subscription.id,
            "expires_at": subscription.expires_at
        }
    except TrialServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
```

- [ ] **Step 2: Commit changes**

```bash
git add backend/app/admin_routes.py
git commit -m "feat: add admin API route for granting trials"
```

---

### Task 3: Verification

- [ ] **Step 1: Create a verification script `reproduce_trial_grant.py`**

```python
import asyncio
from sqlalchemy import select
from app.database import get_session_context
from app.services.trial_service import TrialService
from app.models import UserPreference, TrialConfig, SubscriptionPlan

async def verify():
    async with get_session_context() as db:
        # Ensure we have a user and a trial config
        user_res = await db.execute(select(UserPreference).limit(1))
        user = user_res.scalar_one_or_none()
        if not user:
            print("No user found for testing")
            return

        plan_res = await db.execute(select(SubscriptionPlan).limit(1))
        plan = plan_res.scalar_one_or_none()
        if not plan:
            print("No subscription plan found for testing")
            return

        config_res = await db.execute(select(TrialConfig).limit(1))
        config = config_res.scalar_one_or_none()
        if not config:
            config = TrialConfig(plan_id=plan.id, is_enabled=True, duration_hours=48)
            db.add(config)
            await db.commit()
        else:
            config.plan_id = plan.id
            config.is_enabled = True
            await db.commit()

        # Reset user for test
        user.trial_used = False
        await db.commit()

        try:
            sub = await TrialService.grant_trial_subscription(db, user.id)
            print(f"Successfully granted trial subscription {sub.id} to user {user.id}")
        except Exception as e:
            print(f"Failed to grant trial: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
```

- [ ] **Step 2: Run verification script**

Run: `python3 reproduce_trial_grant.py`
Expected: "Successfully granted trial subscription ..."

- [ ] **Step 3: Cleanup**

Run: `rm reproduce_trial_grant.py`
