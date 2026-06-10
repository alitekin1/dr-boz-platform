import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models import SubscriptionPlan

async def seed():
    async with async_session() as db:
        # Check if plan already exists
        res = await db.execute(select(SubscriptionPlan).filter_by(name="اشتراک ویژه (Shared)"))
        existing = res.scalar_one_or_none()
        
        if existing:
            print(f"Plan '{existing.name}' already exists. Updating...")
            existing.monthly_price_toman = 200000
            existing.cooldown_limit_toman = 50000 # 50,000 Toman usage before 5h cooldown
            existing.cooldown_hours = 5
            existing.weekly_limit_toman = 250000 # 250,000 Toman usage per week
            existing.plan_type = "tiered_cooldown"
        else:
            print("Creating new subscription plan...")
            new_plan = SubscriptionPlan(
                name="اشتراک ویژه (Shared)",
                plan_type="tiered_cooldown",
                monthly_price_toman=200000,
                gift_credit_toman=0,
                cooldown_limit_toman=50000,
                cooldown_hours=5,
                weekly_limit_toman=250000,
                is_agentic=True,
                is_active=True
            )
            db.add(new_plan)
        
        await db.commit()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(seed())
