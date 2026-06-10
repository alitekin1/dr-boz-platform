# Credit Exhaustion Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to pause their action when credits run out and resume it later via an inline button after a successful recharge.

**Architecture:** Add a JSON column `pending_action_payload` to the `UserPreference` table to freeze the action context. When an action is interrupted by low credits, we write the context to this column. Upon a successful payment callback, we check for a pending action and append a "Continue" inline button. A new callback handler processes this button, rehydrates the context, executes the saved action, and clears the column.

**Tech Stack:** Python, FastAPI/SQLAlchemy (for DB model), python-telegram-bot (v20+), Alembic

---

### Task 1: Database Model and Migration

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/test_pending_action_model.py` (for manual DB validation)
- Create: Alembic migration script

- [ ] **Step 1: Write DB validation test script**

```python
# backend/test_pending_action_model.py
import asyncio
import json
from datetime import datetime, timezone
from app.database import async_session
from app.models import UserPreference
from sqlalchemy import select

async def test_pending_action():
    async with async_session() as db:
        user = await db.scalar(select(UserPreference).limit(1))
        if user:
            user.pending_action_payload = {
                "action_type": "chat_completion",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"text": "hello"}
            }
            await db.commit()
            print("Successfully wrote pending_action_payload")
            user.pending_action_payload = None
            await db.commit()
            print("Successfully cleared pending_action_payload")

if __name__ == "__main__":
    asyncio.run(test_pending_action())
```

- [ ] **Step 2: Run test script to verify it fails**

Run: `cd backend && python test_pending_action_model.py`
Expected: FAIL with `AttributeError` or SQLAlchemy error because column doesn't exist.

- [ ] **Step 3: Modify UserPreference model**

Modify `backend/app/models.py`, class `UserPreference`:
```python
    credit_balance_usd = Column(Numeric(precision=10, scale=4), default=0.0)
    pending_action_payload = Column(JSONB, nullable=True) # Add this line
```
*(Use `JSON` if `JSONB` isn't imported from sqlalchemy.dialects.postgresql, or just standard `JSON` from sqlalchemy).*

- [ ] **Step 4: Generate Alembic Migration**

```bash
cd backend
alembic revision --autogenerate -m "add pending_action_payload"
alembic upgrade head
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python test_pending_action_model.py`
Expected: PASS with "Successfully wrote..." and "Successfully cleared..."

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/ backend/test_pending_action_model.py
git commit -m "feat: add pending_action_payload to UserPreference"
```

### Task 2: State Freezing Logic

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update `_insufficient_credit_text` to log frozen state**

In `backend/app/bot.py`, locate `_run_tool_aware_completion` around line 2190 where `_insufficient_credit_text` is called.

```python
    if not _has_credit_for_cost(user, estimated_cost):
        user.pending_action_payload = {
            "action_type": "chat_completion",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "user_message_id": user_message.id,
                "chat_id": chat.id,
                "provider_name": getattr(provider, "name", ""),
                "model_name": getattr(model, "name", "") if hasattr(model, "name") else model,
                "llm_messages": llm_messages,
                "proj_label": proj_label,
                "allow_tools": allow_tools,
                "uploaded_file_id": uploaded_file_id,
            }
        }
        await db.commit()
        await update.message.reply_text(
            _insufficient_credit_text(
                needed=estimated_cost,
                balance=_credit_balance(user),
                action_label="تولید پاسخ",
            ),
            reply_markup=_insufficient_credit_kb()
        )
        return ""
```
*Apply similar logic if there are other `_has_credit_for_cost` checks for audio/file processing in `bot.py`.*

- [ ] **Step 2: Commit**

```bash
git add backend/app/bot.py
git commit -m "feat: freeze state on credit exhaustion"
```

### Task 3: Recharge Flow Update

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Modify `handle_successful_payment` to add Continue button**

In `backend/app/bot.py`, locate `handle_successful_payment` (around line 2167, the success message).

```python
    if credited_now:
        # ... existing promo_line logic ...
        
        reply_markup = None
        if user.pending_action_payload:
            # Check if it's less than 24h old
            try:
                timestamp = datetime.fromisoformat(user.pending_action_payload.get("timestamp", ""))
                if (datetime.now(timezone.utc) - timestamp).total_seconds() < 86400:
                    reply_markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton("▶️ ادامه چت قبلی", callback_data="resume_pending_action")]
                    ])
                else:
                    # Clear expired
                    user.pending_action_payload = None
                    await db.commit()
            except Exception:
                pass
                
        await message.reply_text(
            "✅ پرداخت با موفقیت انجام شد.\n"
            f"شارژ انجام‌شده: ${usd_label}\n"
            f"مبلغ پرداختی: {toman_amount:,} تومان\n"
            f"{promo_line}\n"
            f"اعتبار جدید: ${balance:.4f}",
            reply_markup=reply_markup
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/bot.py
git commit -m "feat: add continue chat button after recharge"
```

### Task 4: Resumption Handler

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Add `resume_pending_action` logic to callbacks**

In `backend/app/bot.py`, inside the main callback query handler loop (or as a separate handler if defined that way):

```python
        if data == "resume_pending_action":
            await query.answer()
            if not user.pending_action_payload:
                await query.message.reply_text("هیچ کار معلقی برای ادامه وجود ندارد.")
                return
            
            payload_data = user.pending_action_payload
            action_type = payload_data.get("action_type")
            payload_args = payload_data.get("payload", {})
            
            # Clear it immediately to prevent double-execution
            user.pending_action_payload = None
            await db.commit()
            
            await query.message.reply_text("⏳ در حال ادامه پردازش قبلی...")
            
            if action_type == "chat_completion":
                from app.llm import get_provider_and_model
                provider_obj, model_obj = await get_provider_and_model(db, user, payload_args.get("provider_name"), payload_args.get("model_name"))
                
                # We need a dummy message and chat object for the signature
                class DummyObj:
                    def __init__(self, **kwargs):
                        self.__dict__.update(kwargs)
                        
                dummy_msg = DummyObj(id=payload_args.get("user_message_id", update.effective_message.id))
                dummy_chat = DummyObj(id=payload_args.get("chat_id", update.effective_chat.id))
                
                await _run_tool_aware_completion(
                    update, db, user=user, user_message=dummy_msg, chat=dummy_chat,
                    provider=provider_obj, model=model_obj, llm_messages=payload_args.get("llm_messages", []),
                    proj_label=payload_args.get("proj_label", ""), allow_tools=payload_args.get("allow_tools", True),
                    uploaded_file_id=payload_args.get("uploaded_file_id")
                )
            else:
                await query.message.reply_text("نوع کار معلق ناشناخته است.")
            return
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/bot.py
git commit -m "feat: handle resume pending action callback"
```
