from app.tips_scheduler import process_scheduled_tips
from app.database import async_session
from telegram.ext import ContextTypes

async def run_scheduled_tips(context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        try:
            await process_scheduled_tips(context.bot, session)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in run_scheduled_tips job: {e}")
