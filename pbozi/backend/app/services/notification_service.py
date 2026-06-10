import logging
from telegram import Bot
from app.config import BOT_TOKEN, BOT_PLATFORM, BALE_API_BASE_URL

logger = logging.getLogger(__name__)

async def send_telegram_notification(telegram_user_id: int, text: str):
    """
    Sends a telegram message to a user.
    Handles both Telegram and Bale platforms based on config.
    """
    if not telegram_user_id:
        return

    try:
        # Initialize bot
        if BOT_PLATFORM == "bale" and BALE_API_BASE_URL:
            bot = Bot(token=BOT_TOKEN, base_url=BALE_API_BASE_URL)
        else:
            bot = Bot(token=BOT_TOKEN)
        
        await bot.send_message(chat_id=telegram_user_id, text=text)
        logger.info(f"Notification sent to {telegram_user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send notification to {telegram_user_id}: {e}")
        return False
