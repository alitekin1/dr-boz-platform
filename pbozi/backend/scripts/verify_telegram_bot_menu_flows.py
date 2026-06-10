#!/usr/bin/env python3
"""Regression checks for Telegram bot menu flow helpers.

This script intentionally avoids pytest so it can run in the current backend
venv. It checks pure helpers and callback/menu constraints that do not require
real Telegram updates.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram import ReplyKeyboardMarkup

from app import bot


def check(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def _reply_button_texts(markup: ReplyKeyboardMarkup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def verify_learning_in_progress_text():
    text = bot._account_learning_text(
        {
            "learning_payload": {
                "in_progress": True,
                "questions_answered": 2,
                "target_questions": 4,
                "next_question": "سوال بعدی؟",
            }
        }
    )
    check("فرآیند فعال است" in text, "learning tab should describe active in-progress session")
    check("سوال فعلی" in text, "learning tab should show the current question")
    check("برای شروع، «شروع تنظیمات» را بزن." not in text, "in-progress learning tab should not show start-only copy")


def verify_cancel_keyboards():
    contact_kb = bot._contact_request_kb()
    texts = _reply_button_texts(contact_kb)
    check(bot.CANCEL_TEXT in texts, "contact request keyboard should include visible cancel")
    check(any(getattr(button, "request_contact", False) for row in contact_kb.keyboard for button in row), "contact keyboard should still request contact")

    cancel_kb = bot._cancel_reply_kb()
    check(bot.CANCEL_TEXT in _reply_button_texts(cancel_kb), "generic cancel keyboard should include visible cancel")


def verify_onboarding_keyboard_shape():
    check(bot._onboarding_kb(need_phone=False) is None, "onboarding keyboard should be hidden when phone is not required")
    phone_kb = bot._onboarding_kb(need_phone=True)
    check(phone_kb is not None, "onboarding keyboard should exist when phone is required")
    inline_values = [button.callback_data for row in phone_kb.inline_keyboard for button in row]
    check("share_contact_request" in inline_values, "onboarding keyboard should include share_contact_request callback")


def verify_group_optin_menu_shape():
    kb = bot._group_optin_keyboard(group_id=42, enabled=False)
    callbacks = [button.callback_data for row in kb.inline_keyboard for button in row]
    check("groupopt_enable_42" in callbacks, "group opt-in menu should include enable callback")
    check("groupopt_disable_42" in callbacks, "group opt-in menu should include disable callback")
    check("groupopt_refresh_42" in callbacks, "group opt-in menu should include refresh callback")
    check("cancel_main" in callbacks, "group opt-in menu should include inline return-to-main callback")


def verify_admin_delete_confirm_keyboard():
    kb = bot._admin_delete_confirm_kb("prov", 7)
    callbacks = [button.callback_data for row in kb.inline_keyboard for button in row]
    check("delconfirm_prov_7" in callbacks, "admin delete confirm keyboard should include confirmation callback")
    check("cancel_admin_delete" in callbacks, "admin delete confirm keyboard should include cancel callback")


def verify_retry_callback_data_is_safe():
    long_name = "very-" + ("long-" * 20) + "filename.pdf"
    callback_data = bot._retry_upload_callback_data(123, long_name)
    check(len(callback_data.encode("utf-8")) <= 64, "retry upload callback data must fit Telegram's 64-byte limit")
    check(callback_data.startswith("retry_upload_123"), "retry upload callback should preserve the project id")


def verify_chat_access_helper():
    regular_user = SimpleNamespace(id=10, is_admin=False)
    admin_user = SimpleNamespace(id=99, is_admin=True)
    own_chat = SimpleNamespace(user_preference_id=10)
    other_chat = SimpleNamespace(user_preference_id=11)
    legacy_chat = SimpleNamespace(user_preference_id=None)

    check(bot._user_can_access_chat(regular_user, own_chat), "user should access own chat")
    check(not bot._user_can_access_chat(regular_user, other_chat), "user should not access another user's chat")
    check(not bot._user_can_access_chat(regular_user, legacy_chat), "regular user should not access unowned legacy chat")
    check(bot._user_can_access_chat(admin_user, other_chat), "admin should access chats for support/admin use")


def main():
    verify_learning_in_progress_text()
    verify_cancel_keyboards()
    verify_onboarding_keyboard_shape()
    verify_group_optin_menu_shape()
    verify_admin_delete_confirm_keyboard()
    verify_retry_callback_data_is_safe()
    verify_chat_access_helper()
    print("telegram bot menu flow checks passed")


if __name__ == "__main__":
    main()
