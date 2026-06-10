import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.bot import _send_project_share_callback_message, project_kb


class FakeBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()


class FailingMessage:
    async def reply_text(self, *args, **kwargs):
        raise RuntimeError("reply_text should not be used for share callback results")


class FakeUpdate:
    effective_chat = type("Chat", (), {"id": 12345})()


async def main():
    context = FakeContext()
    await _send_project_share_callback_message(
        FakeUpdate(),
        context,
        "✅ پروژه اضافه شد:\n📁 تست",
        reply_markup=project_kb(),
        fallback_message=FailingMessage(),
    )

    assert len(context.bot.sent_messages) == 1
    sent = context.bot.sent_messages[0]
    assert sent["chat_id"] == 12345
    assert "پروژه اضافه شد" in sent["text"]
    assert sent["reply_markup"] is not None


if __name__ == "__main__":
    asyncio.run(main())
