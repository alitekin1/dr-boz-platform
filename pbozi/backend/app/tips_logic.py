import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import select, and_, text
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from app.models import Tip, UserTipDismissal
from app.database import async_session

logger = logging.getLogger(__name__)

async def _auto_delete_tip(bot, chat_id: int, message_id: int, delay_seconds: int):
    await asyncio.sleep(delay_seconds)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except BadRequest as e:
        if "Message to delete not found" in str(e) or "Message not found" in str(e):
            pass
        else:
            logger.debug(f"Could not auto-delete tip message {message_id}: {e}")
    except Exception as e:
        logger.debug(f"Could not auto-delete tip message {message_id}: {e}")

async def maybe_send_tip(bot, chat_id: int, user_id: int, trigger_key: str, db):
    try:
        # Check if tip exists and is active
        result = await db.execute(select(Tip).where(
            and_(Tip.trigger_key == trigger_key, Tip.is_active == True)
        ))
        tip = result.scalar_one_or_none()
        
        if not tip:
            return

        # Check if user dismissed it
        result = await db.execute(select(UserTipDismissal).where(
            and_(UserTipDismissal.user_id == user_id, UserTipDismissal.tip_id == tip.id)
        ))
        dismissal = result.scalar_one_or_none()

        if dismissal:
            return

        # Prepare delay
        if tip.delay_seconds > 0:
            # We don't want to block the caller for a long time
            # If delay is > 0.5s, let's fire and forget or skip
            if tip.delay_seconds > 1:
                # For now, we'll just ignore delay if it's too long in this sync-like call
                # OR we could create a task to send it later
                pass
            else:
                await asyncio.sleep(tip.delay_seconds)

        keyboard = [
            [
                InlineKeyboardButton("متوجه شدم", callback_data=f"tip_got_it_{tip.id}"),
                InlineKeyboardButton("دیگر نشان نده", callback_data=f"tip_dismiss_{tip.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=f"💡 <b>نکته:</b>\n\n{tip.content}",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.warning(f"Could not send tip to {chat_id}: {e}")
            return

        # Log delivery in a SEPARATE session
        async with async_session() as log_db:
            try:
                await log_db.execute(text("""
                    INSERT INTO tip_delivery_logs (user_id, tip_id, trigger_key, tip_type, delivered_at)
                    VALUES (:user_id, :tip_id, :trigger_key, :tip_type, :delivered_at)
                """), {
                    "user_id": user_id,
                    "tip_id": tip.id,
                    "trigger_key": tip.trigger_key,
                    "tip_type": tip.tip_type,
                    "delivered_at": datetime.now(timezone.utc)
                })
                await log_db.commit()
            except Exception as log_err:
                logger.error(f"Failed to log tip delivery: {log_err}")

        # Schedule auto-delete
        if tip.auto_delete_seconds > 0:
            asyncio.create_task(_auto_delete_tip(bot, chat_id, msg.message_id, tip.auto_delete_seconds))
            
    except Exception as e:
        logger.error(f"Error in maybe_send_tip {trigger_key}: {e}")

async def handle_tip_callback(update, context, db, user_preference_id: int):
    query = update.callback_query
    data = query.data
    
    try:
        if data.startswith("tip_got_it_"):
            try:
                await query.message.delete()
            except Exception:
                pass
            try:
                await query.answer("پیام پاک شد.")
            except Exception:
                pass
            
        elif data.startswith("tip_dismiss_"):
            tip_id = int(data.replace("tip_dismiss_", ""))
            
            # Record dismissal
            result = await db.execute(select(UserTipDismissal).where(
                and_(UserTipDismissal.user_id == user_preference_id, UserTipDismissal.tip_id == tip_id)
            ))
            existing = result.scalar_one_or_none()
            
            if not existing:
                dismissal = UserTipDismissal(user_id=user_preference_id, tip_id=tip_id)
                db.add(dismissal)
                await db.commit()
            
            try:
                await query.message.delete()
            except Exception:
                pass
            try:
                await query.answer("دیگر این راهنما به شما نشان داده نخواهد شد.")
            except Exception:
                pass
            
    except Exception as e:
        logger.error(f"Error handling tip callback {data}: {e}")
        try:
            await query.answer("خطایی رخ داد.")
        except Exception:
            pass
