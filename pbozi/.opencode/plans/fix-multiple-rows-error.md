# Fix: "Multiple rows were found when one or none was required"

## Problem
The bot throws `Multiple rows were found when one or none was required` error when processing messages. This is a SQLAlchemy error from using `.scalar_one()` when a query returns more than one row.

## Root Cause
There are 9 places in `backend/app/bot.py` using `.scalar_one()` instead of the safer `.scalar_one_or_none()`. While `Chat.id` is a primary key and should be unique, the database may have corrupted data or the query may be returning duplicates due to some issue.

## Affected Lines in `backend/app/bot.py`
- Line 8467: `current_chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()`
- Line 8524: `chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one(),`
- Line 8566: `chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one(),`
- Line 10065: `current_chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()`
- Line 10132: `chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one(),`
- Line 10173: `chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one(),`
- Line 10233: `current_chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()`
- Line 10299: `chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one(),`
- Line 10340: `chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one(),`

## Fix
Replace all 9 occurrences of `.scalar_one()` with `.scalar_one_or_none()` and add null checks where needed.

### Changes needed:

1. **Line 8467**: Change to `.scalar_one_or_none()` and add null check:
   ```python
   current_chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
   if not current_chat:
       await update.message.reply_text("چت پیدا نشد")
       return
   ```

2. **Lines 8524, 8566, 10132, 10173, 10299, 10340**: These pass `chat` to functions. Change to `.scalar_one_or_none()` - the functions should handle None gracefully, or add null checks before calling.

3. **Lines 10065, 10233**: Same as line 8467 - change to `.scalar_one_or_none()` and add null check.

## Verification
After making changes:
1. Restart the bot
2. Test sending messages in existing chats
3. Verify no more "Multiple rows" errors appear
4. Check that the bot handles missing chats gracefully
