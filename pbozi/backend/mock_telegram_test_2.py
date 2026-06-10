import asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, CallbackQuery, User, Message
from app.bot import button_callback
import sys

async def run():
    print("Starting test...")
    update = MagicMock(spec=Update)
    update.update_id = 99999999
    
    query = AsyncMock(spec=CallbackQuery)
    query.data = "model_1"
    
    user = MagicMock(spec=User)
    user.id = 48859866
    query.from_user = user
    
    message = AsyncMock(spec=Message)
    message.chat_id = 12345
    message.id = 12345
    query.message = message
    
    update.callback_query = query
    update.effective_user = user
    update.effective_chat = message
    update.effective_chat.id = 12345
    
    context = MagicMock()
    
    try:
        await button_callback(update, context)
        print("Callback finished!")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run())
