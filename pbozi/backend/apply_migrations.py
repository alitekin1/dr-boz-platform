
import asyncio
from sqlalchemy import text
from app.database import engine

async def migrate():
    async with engine.begin() as conn:
        print("Migrating subscription_plans...")
        try:
            await conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN plan_type VARCHAR DEFAULT 'monthly_credit'"))
            await conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN cooldown_limit_toman INTEGER DEFAULT 0"))
            await conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN cooldown_hours INTEGER DEFAULT 0"))
            await conn.execute(text("ALTER TABLE subscription_plans ADD COLUMN weekly_limit_toman INTEGER DEFAULT 0"))
            print("subscription_plans migrated.")
        except Exception as e:
            print(f"subscription_plans error: {e}")

        print("Migrating user_subscriptions...")
        try:
            await conn.execute(text("ALTER TABLE user_subscriptions ADD COLUMN cooldown_spent_toman INTEGER DEFAULT 0"))
            await conn.execute(text("ALTER TABLE user_subscriptions ADD COLUMN cooldown_ends_at DATETIME"))
            await conn.execute(text("ALTER TABLE user_subscriptions ADD COLUMN weekly_spent_toman INTEGER DEFAULT 0"))
            await conn.execute(text("ALTER TABLE user_subscriptions ADD COLUMN week_resets_at DATETIME"))
            print("user_subscriptions migrated.")
        except Exception as e:
            print(f"user_subscriptions error: {e}")

        print("Migrating user_preferences...")
        try:
            await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN trial_used BOOLEAN DEFAULT FALSE"))
            print("user_preferences migrated.")
        except Exception as e:
            print(f"user_preferences error: {e}")

        print("Creating trial_configs table...")
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS trial_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER,
                    duration_hours INTEGER DEFAULT 48,
                    is_enabled BOOLEAN DEFAULT FALSE,
                    apply_automatically BOOLEAN DEFAULT FALSE,
                    welcome_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(plan_id) REFERENCES subscription_plans(id)
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trial_configs_id ON trial_configs (id)"))
            print("trial_configs table created.")
        except Exception as e:
            print(f"trial_configs error: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
