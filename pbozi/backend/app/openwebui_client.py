"""
OpenWebUI API Client for BOZ GPT Bot
Syncs Telegram/Bale bot messages into OpenWebUI chats.
"""
import httpx
import time
from typing import Optional

from app.config import OPENWEBUI_URL, OPENWEBUI_SYNC_SECRET


class OpenWebUIClient:
    """Client for syncing BOZ GPT bot messages to OpenWebUI."""

    def __init__(self, base_url: Optional[str] = None, sync_secret: Optional[str] = None):
        self.base_url = (base_url or OPENWEBUI_URL).rstrip("/")
        self.sync_secret = sync_secret or OPENWEBUI_SYNC_SECRET

    async def sync_messages(
        self,
        telegram_user_id: int,
        user_name: str,
        user_email: str,
        messages: list[dict],
        chat_title: str = "گفتگوی تلگرام",
    ) -> dict:
        """
        Sync a batch of messages to OpenWebUI.

        messages: list of {"role": "user"|"assistant", "content": str}
        Returns: {"status": "ok", "chat_id": str, "user_id": str, "message_count": int}
        """
        payload = {
            "telegram_user_id": telegram_user_id,
            "user_name": user_name,
            "user_email": user_email,
            "messages": messages,
            "chat_title": chat_title,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/boz/sync",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def sync_user_message_and_response(
        self,
        telegram_user_id: int,
        user_name: str,
        user_message: str,
        bot_response: str,
        model: str = "boz-gpt",
        chat_title: str = "گفتگوی تلگرام",
    ) -> dict:
        """
        Convenience method to sync a single user message + bot response pair.
        """
        email = f"boz-{telegram_user_id}@bozgpt.local"
        messages = [
            {"role": "user", "content": user_message, "timestamp": int(time.time())},
            {"role": "assistant", "content": bot_response, "timestamp": int(time.time()), "model": model},
        ]
        return await self.sync_messages(
            telegram_user_id=telegram_user_id,
            user_name=user_name,
            user_email=email,
            messages=messages,
            chat_title=chat_title,
        )
