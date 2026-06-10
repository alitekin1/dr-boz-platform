import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from app.models import UserPreference, TrialConfig, UserSubscription, AdminAction, CapacityPool
from app.config import BOT_TOKEN, BOT_PLATFORM, BALE_API_BASE_URL
from app.services.codex_capacity_service import assign_subscription_pool
import app.models as models

logger = logging.getLogger(__name__)

class TrialServiceError(Exception):
    pass

class TrialService:
    @staticmethod
    async def grant_trial_subscription(db: AsyncSession, user_id: int, reason: str = "Admin manually granted trial") -> UserSubscription:
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
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = now + timedelta(hours=config.duration_hours)
        
        subscription = UserSubscription(
            user_id=user.id,
            plan_id=config.plan_id,
            status="active",
            purchased_at=now,
            expires_at=expires_at
        )
        db.add(subscription)
        await db.flush() # Populate subscription.id for pool assignment
        
        # 6. Assign to Capacity Pool (CRITICAL FIX)
        try:
            await assign_subscription_pool(db, subscription)
        except Exception as e:
            logger.error(f"Failed to assign pool for trial subscription: {e}")
            # We continue even if pool assignment fails, or should we fail?
            # Regular subscription fails if pool assignment fails.
            raise TrialServiceError(f"Failed to assign capacity pool: {str(e)}")

        # 7. Update user
        user.trial_used = True
        
        # 8. Record admin action
        admin_action = AdminAction(
            action_type="grant_trial",
            target_type="user",
            target_id=user.id,
            after_json={"subscription_plan_id": config.plan_id, "expires_at": expires_at.isoformat()},
            reason=reason
        )
        db.add(admin_action)
        
        await db.commit()
        await db.refresh(subscription)

        # 9. Send Telegram Notification
        if user.telegram_user_id:
            try:
                welcome_msg = config.welcome_message or "🎁 هدیه ویژه! اشتراک تست برای شما فعال شد. اکنون می‌توانید از تمام امکانات استفاده کنید."
                
                # Initialize bot (Ensure we use the latest PTB style)
                from telegram import Bot
                if BOT_PLATFORM == "bale" and BALE_API_BASE_URL:
                    bot = Bot(token=BOT_TOKEN, base_url=BALE_API_BASE_URL)
                else:
                    bot = Bot(token=BOT_TOKEN)
                
                # Use a fire-and-forget task or wait? Better to wait briefly or catch errors
                await bot.send_message(chat_id=user.telegram_user_id, text=welcome_msg)
                logger.info(f"Sent trial notification to user {user.id}")
            except Exception as e:
                logger.error(f"Failed to send trial welcome message to user {user.id}: {e}")

        return subscription
