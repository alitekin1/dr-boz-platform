import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_, not_

from app.models import Tip, UserPreference, UserTipDismissal
from app.tips_logic import maybe_send_tip

logger = logging.getLogger(__name__)

async def get_eligible_users_for_tip(db, tip: Tip, limit: int = 100):
    """Find users who should get this scheduled tip."""
    now = datetime.now(timezone.utc)
    min_creation_date = now - timedelta(days=tip.min_account_age_days)
    
    # Subquery to find users who dismissed this tip
    dismissed_users_subq = select(UserTipDismissal.user_id).where(UserTipDismissal.tip_id == tip.id)
    
    stmt = select(UserPreference).where(
        and_(
            UserPreference.created_at <= min_creation_date,
            UserPreference.telegram_user_id.isnot(None), # Must have tg id
            UserPreference.account_status == "active",
            not_(UserPreference.id.in_(dismissed_users_subq))
        )
    ).limit(limit)
    
    result = await db.execute(stmt)
    return result.scalars().all()

async def process_scheduled_tips(bot, db):
    try:
        # Find active scheduled tips
        result = await db.execute(select(Tip).where(
            and_(Tip.is_active == True, Tip.tip_type == "scheduled")
        ))
        tips = result.scalars().all()
        
        for tip in tips:
            users = await get_eligible_users_for_tip(db, tip, limit=50) # Process in batches
            for user in users:
                # We send it, relying on maybe_send_tip's internal logic as backup
                await maybe_send_tip(
                    bot=bot,
                    chat_id=user.telegram_user_id,
                    user_id=user.id,
                    trigger_key=tip.trigger_key,
                    db=db
                )
                
                # To prevent re-sending the same scheduled tip immediately, 
                # we record a dismissal immediately so they only see it once.
                dismissal = UserTipDismissal(user_id=user.id, tip_id=tip.id)
                db.add(dismissal)
                await db.commit()
                
    except Exception as e:
        logger.error(f"Error processing scheduled tips: {e}")
