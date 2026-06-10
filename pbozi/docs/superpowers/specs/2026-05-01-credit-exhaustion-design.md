# Pending Action on Credit Exhaustion Design

## Overview
When a user runs out of credits during a chat, voice transcription, or document embedding, their attempted action is "frozen" and stored in the database. Upon successfully topping up their account, they are presented with a "Continue previous action" button to resume without re-typing or re-uploading.

## Database Changes
- Add a new `JSON` or `JSONB` column `pending_action_payload` to the `user_preferences` table (SQLAlchemy model).
- Add Alembic migration script to add this column.
- This column will store a JSON object containing:
  - `action_type`: string (e.g., "chat_completion", "voice_transcription", "document_embedding")
  - `payload`: dict (the arguments necessary to resume the function, such as `user_message_id`, `chat_id`, `llm_messages`, `uploaded_file_id`, `model_name`, `provider_name`, etc.)
  - `timestamp`: isoformat string (UTC) of when the action was frozen.

## Flow
1. **Freezing State:**
   In `bot.py` and `telegram_bot_runtime.py`, whenever `_has_credit_for_cost` returns false and `_insufficient_credit_text` is sent, we also write the frozen state to `user.pending_action_payload`. We then commit the session.

2. **Recharge Flow:**
   In `handle_successful_payment` in `bot.py`, after a successful top-up:
   - Check if `user.pending_action_payload` is not null.
   - If it exists and is not older than 24 hours, append an InlineKeyboardMarkup with a `resume_pending_action` callback to the success message.

3. **Resumption:**
   - A new `CallbackQueryHandler` for `resume_pending_action` is added in `bot.py`.
   - When triggered, it loads `user.pending_action_payload`.
   - It reconstructs the necessary context (e.g., fetching the original message by its `user_message_id` and `chat_id`, or just re-dispatching the logic).
   - It calls the corresponding function (e.g., `_run_tool_aware_completion`, `_process_audio_message`, `_process_document_message`).
   - Finally, it clears `user.pending_action_payload` from the database.

## Edge Cases
- **Expiration:** If a frozen state is older than 24 hours, the `resume_pending_action` button is not shown.
- **Multiple Interruptions:** If a user triggers a second insufficient credit error while one is already pending, the newer one overwrites the older one.
- **File Validation:** We will rely on Telegram `file_id` which is permanent for the bot, allowing resumption of file/audio processing.