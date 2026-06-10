# Pro User Project Restriction & Disable Group Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict project-specific features to Pro users only and disable all group chat functionality.

**Architecture:** 
- Centralize Pro status verification in `bot.py`.
- Apply verification to all project-related command handlers and message processing.
- Disable group chats by clearing allowed chat types and adding a block message.
- Sync restrictions to the Web API in `main_routes.py`.

**Tech Stack:** Python, FastAPI, python-telegram-bot, SQLAlchemy.

---

### Task 1: Disable Group Chat Functionality

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Set `GROUP_ALLOWED_CHAT_TYPES` to empty**
Modify `backend/app/bot.py` to disable group chat types.

```python
# Around line 182
GROUP_ALLOWED_CHAT_TYPES = set() # Changed from {"group", "supergroup"}
```

- [ ] **Step 2: Add group block message in `handle_message`**
Modify `handle_message` in `backend/app/bot.py` to inform users that group chat is disabled if they somehow trigger it.

```python
# Inside handle_message, find the group check
if update.effective_chat and update.effective_chat.type in {"group", "supergroup"}:
    await update.message.reply_text("⚠️ قابلیت گفتگو در گروه‌ها در حال حاضر غیرفعال است.")
    return
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/bot.py
git commit -m "feat: disable group chat functionality"
```

---

### Task 2: Implement Centralized Pro Check Helper

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Define `_is_pro_or_admin` and `_send_pro_restriction_message`**
Add these helpers to `backend/app/bot.py`.

```python
def _is_pro_or_admin(user) -> bool:
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

- [ ] **Step 2: Commit**
```bash
git add backend/app/bot.py
git commit -m "feat: add pro restriction helpers"
```

---

### Task 3: Enforce Pro Restriction in Project Handlers

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update `_process_chat_text_turn`**
Check Pro status if a project is used in a chat.

```python
# Inside _process_chat_text_turn, after project_id is determined
project_id = user.current_project_id or chat.project_id
if project_id and not _is_pro_or_admin(user):
    await _send_pro_restriction_message(update, context)
    return
```

- [ ] **Step 2: Update `cmd_start_convo`**
Check Pro status before starting a project-linked conversation.

```python
# Inside cmd_start_convo
if user.current_project_id and not _is_pro_or_admin(user):
    await _send_pro_restriction_message(update, context)
    return
```

- [ ] **Step 3: Update other project commands**
Update `cmd_project_files`, `cmd_project_instructions`, `cmd_share_project`, and `cmd_project_settings`.

```python
# At the beginning of each of these functions
if not _is_pro_or_admin(user):
    await _send_pro_restriction_message(update, context)
    return
```

- [ ] **Step 4: Commit**
```bash
git add backend/app/bot.py
git commit -m "feat: enforce pro restriction on project handlers"
```

---

### Task 4: Enforce Pro Restriction in Web API

**Files:**
- Modify: `backend/app/main_routes.py`

- [ ] **Step 1: Update `send_message` in `main_routes.py`**
Verify Pro status if `chat.project_id` is set.

```python
# Inside send_message, after resolving resolved_user
if chat.project_id and resolved_user:
    if not (resolved_user.is_admin or resolved_user.is_pro):
        # We can either return a 403 or just skip RAG context.
        # Given the requirement "استفاده باید پرو باشد", blocking is better.
        raise HTTPException(403, "Project features require Pro status. Please upgrade by charging your account.")
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/main_routes.py
git commit -m "feat: enforce pro restriction in web api"
```

---

### Task 5: Verification

- [ ] **Step 1: Test Group Chat**
Try to send a message in a group. Verify it is ignored or shows the block message.

- [ ] **Step 2: Test Project Import & Chat (Non-Pro)**
Import a project via link as a non-Pro user. Try to chat with it. Verify the "Upgrade to Pro" message appears.

- [ ] **Step 3: Test Project Menus (Non-Pro)**
Try to access "Files" or "Instructions" for an imported project. Verify the "Upgrade to Pro" message appears.

- [ ] **Step 4: Test Pro User**
Verify a Pro user can still use projects normally.
