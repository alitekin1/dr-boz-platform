import asyncio
import os
import sys
from datetime import datetime

from unittest.mock import AsyncMock, MagicMock, patch

# Ensure we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

from app.bot import handle_message
from app.database import init_db
import app.bot

# Mock _claim_update_once to bypass update idempotency checks
app.bot._claim_update_once = AsyncMock(return_value=True)

class MockMessage:
    def __init__(self, text):
        self.text = text
        self.id = 12345
        self.reply_text = AsyncMock(return_value=self)
        self.edit_text = AsyncMock(return_value=self)
        self.contact = None
        self.document = None
        self.photo = None
        self.voice = None
        self.location = None
        self.video = None
        self.audio = None

class MockUser:
    def __init__(self, uid):
        self.id = uid
        self.first_name = "Test"
        self.username = "test_user"

class MockChat:
    def __init__(self, cid):
        self.id = cid
        self.type = "private"

class MockUpdate:
    def __init__(self, uid, text):
        self.effective_user = MockUser(uid)
        self.effective_chat = MockChat(uid)
        self.message = MockMessage(text)
        self.update_id = 99999
        self.callback_query = None
        self.inline_query = None
        self.my_chat_member = None
        self.chat_member = None
        self.message_reaction = None
        self.channel_post = None
        self.edited_message = None
        self.edited_channel_post = None
        self.chosen_inline_result = None
        self.shipping_query = None
        self.pre_checkout_query = None
        self.poll = None
        self.poll_answer = None
        self.chat_join_request = None

class MockContext:
    def __init__(self):
        self.user_data = {}
        self.bot = MagicMock()

async def test_bot_messages():
    await init_db()
    
    test_cases = [
        "What is 2+2?",
        "Use python to calculate 5 ** 20",
        "Search the web to find the capital of France",
    ]
    
    uid = 567136570  # Admin ID to bypass onboarding potentially
    
    for message_text in test_cases:
        print(f"\n{'='*50}\nTESTING: {message_text}\n{'='*50}")
        update = MockUpdate(uid, message_text)
        context = MockContext()
        
        # Call the handler
        await handle_message(update, context)
        
        # Print what the bot did
        print("\n--- ACTIONS ---")
        for call in update.message.reply_text.call_args_list:
            args, kwargs = call
            print(f"[reply_text] {args[0]}")
            
        for call in update.message.edit_text.call_args_list:
            args, kwargs = call
            print(f"[edit_text] {args[0]}")

if __name__ == "__main__":
    asyncio.run(test_bot_messages())