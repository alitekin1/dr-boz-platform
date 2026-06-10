import asyncio
import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from sqlalchemy import select, delete
from app.database import get_session_context
from app.services.trial_service import TrialService
from app.models import UserPreference, TrialConfig, SubscriptionPlan, UserSubscription

async def verify():
    async with get_session_context() as db:
        # 1. Get or create a subscription plan
        plan_res = await db.execute(select(SubscriptionPlan).limit(1))
        plan = plan_res.scalar_one_or_none()
        if not plan:
            plan = SubscriptionPlan(name="Test Plan", is_active=True)
            db.add(plan)
            await db.commit()
            await db.refresh(plan)
            print(f"Created Test Plan with ID {plan.id}")

        # 2. Get or create a trial config
        config_res = await db.execute(select(TrialConfig).limit(1))
        config = config_res.scalar_one_or_none()
        if not config:
            config = TrialConfig(plan_id=plan.id, is_enabled=True, duration_hours=48)
            db.add(config)
            await db.commit()
            await db.refresh(config)
            print(f"Created TrialConfig with ID {config.id}")
        else:
            config.plan_id = plan.id
            config.is_enabled = True
            await db.commit()
            print(f"Updated TrialConfig with ID {config.id}")

        # 3. Get or create a user
        user_res = await db.execute(select(UserPreference).limit(1))
        user = user_res.scalar_one_or_none()
        if not user:
            user = UserPreference(telegram_user_id=99999, preferred_name="Test User")
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"Created Test User with ID {user.id}")
        
        # Reset user for test
        user.trial_used = False
        # Remove active subscriptions if any
        await db.execute(
            delete(UserSubscription).where(UserSubscription.user_id == user.id)
        )
        await db.commit()

        # 4. Grant trial
        try:
            sub = await TrialService.grant_trial_subscription(db, user.id)
            print(f"Successfully granted trial subscription {sub.id} to user {user.id}")
            print(f"Expires at: {sub.expires_at}")
            
            # Verify user.trial_used is True
            await db.refresh(user)
            assert user.trial_used is True
            print("Verified user.trial_used is True")

        except Exception as e:
            print(f"Failed to grant trial: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    # Mocking some parts if needed, but get_session_context should work if DB is accessible
    # Set PYTHONPATH if needed: export PYTHONPATH=$PYTHONPATH:.
    asyncio.run(verify())
