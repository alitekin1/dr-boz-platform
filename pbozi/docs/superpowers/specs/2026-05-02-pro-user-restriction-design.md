# Design: Pro User Project Restriction

Restrict chat functionality for projects imported via links (and projects in general) to "Pro" users only, while still allowing non-Pro users to import projects.

## Problem
Currently, non-Pro users can import projects via shared links and immediately start chatting with them. Project-specific features like RAG (Retrieval Augmented Generation) and project instructions should be reserved for Pro users (those who have charged at least $1).

## Goals
- Allow non-Pro users to import projects via links.
- Block non-Pro users from chatting with projects (or using project-specific menus).
- Provide a clear "Upgrade to Pro" message when a non-Pro user tries to use a project.
- Ensure consistency between Telegram Bot (Bale) and Web UI.
- **Bale Framework Compatibility**: Ensure messages and keyboards are optimized for the Bale platform.
- **Disable Group Chats**: Disable all group chat functionality for now.

## Proposed Changes

### 1. Centralized Pro Check Helper (Telegram Bot)
Create a helper function in `backend/app/bot.py` to send the "Pro required" message and keyboard.

```python
def _is_pro_or_admin(user: UserPreference) -> bool:
    return user.is_admin or user.is_pro

async def _send_pro_restriction_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🚀 *دسترسی به پروژه‌ها مخصوص کاربران پرو است!*\n\n" \
           "شما می‌توانید با شارژ حداقل **۱ دلار** حساب خود، به قابلیت مدیریت پروژه‌ها و دانش‌نامه اختصاصی دسترسی پیدا کنید.\n\n" \
           "💡 کاربران پرو می‌توانند فایل‌های خود را آپلود کرده و از هوش مصنوعی بخواهند بر اساس آن‌ها پاسخ دهد."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("➕ شارژ و ارتقا", callback_data="account_topup_start")]])
    
    if update.message:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
```

### 2. Update `bot.py` Handlers for Projects
Apply the Pro check to:
- `_process_chat_text_turn`: If `project_id` is present, check Pro status.
- `cmd_start_convo`: Check Pro status if `user.current_project_id` is set.
- `cmd_project_files`, `cmd_project_instructions`, `cmd_share_project`, `cmd_project_settings`: Check Pro status.

### 3. Disable Group Chats
Modify `bot.py`:
- Set `GROUP_ALLOWED_CHAT_TYPES = set()` (empty set) to effectively disable group logic in all checks.
- Add a check in `handle_message` and other entry points to ignore group updates or send a "Disabled" message if it's a group.

### 4. Update Web API (`main_routes.py`)
In `send_message`, check if `chat.project_id` is present. If user is not Pro, block the request or strip project context.

## Approaches

### Approach A: Strict Blocking (Recommended)
Block all project-related actions and group chats.

## Bale Framework Specifics
- Use `ParseMode.MARKDOWN`.
- Use existing Bale payment callback (`account_topup_start`).

## Approval Required
- [ ] Centralized Pro check helper?
- [ ] Blocking all project interactions (Chat, Files, Instructions)?
- [ ] Web API check?
