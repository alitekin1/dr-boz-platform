# Pro User Restriction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict access to the "Projects" section in the Telegram bot to "Pro Users" (users who have charged at least $1.00 or were manually promoted by an admin).

**Architecture:**
- Extend the `UserPreference` model with `is_pro` and `total_charged_usd` fields.
- Update the database initialization logic to handle these new columns.
- Update the payment and promo code logic to track total charges and auto-promote users to Pro status.
- Add access checks to project-related routes and bot commands.
- Update the admin panel to allow manual Pro status management.

**Tech Stack:**
- Backend: Python (FastAPI, SQLAlchemy, Pydantic)
- Database: SQLite (via AIOSQLite)
- Frontend: React (TypeScript, TanStack Query, Tailwind CSS)
- Bot: Python (python-telegram-bot)

---

### Task 1: Database Model and Migration

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/database.py`
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add fields to UserPreference model**
Add `is_pro` and `total_charged_usd` to the `UserPreference` class in `backend/app/models.py`.

```python
class UserPreference(Base):
    # ... existing fields ...
    is_pro = Column(Boolean, default=False)
    total_charged_usd = Column(Float, default=0.0)
```

- [ ] **Step 2: Add migration logic to database.py**
Update `_apply_sqlite_compat_migrations` in `backend/app/database.py` to add the new columns.

```python
    if "user_preferences" in table_names:
        columns = await _sqlite_table_columns(conn, "user_preferences")
        additions = {
            # ... existing additions ...
            "is_pro": "ALTER TABLE user_preferences ADD COLUMN is_pro BOOLEAN DEFAULT 0",
            "total_charged_usd": "ALTER TABLE user_preferences ADD COLUMN total_charged_usd FLOAT DEFAULT 0.0",
        }
```

- [ ] **Step 3: Update schemas.py**
Include the new fields in `UserPreferenceOut` or equivalent schemas if they exist.

```python
class UserOut(BaseModel):
    # ...
    is_pro: bool
    total_charged_usd: float
```

- [ ] **Step 4: Commit**
```bash
git add backend/app/models.py backend/app/database.py backend/app/schemas.py
git commit -m "db: add is_pro and total_charged_usd to UserPreference"
```

---

### Task 2: Backend Logic for Pro Promotion

**Files:**
- Modify: `backend/app/bot.py`
- Modify: `backend/app/services/promo_code_service.py`

- [ ] **Step 1: Update bot.py payment logic**
Update `_apply_topup_credit` in `backend/app/bot.py` to increment `total_charged_usd` and check for Pro status.

```python
async def _apply_topup_credit(...):
    # ...
    user.total_charged_usd = (user.total_charged_usd or 0.0) + float(usd_amount)
    if user.total_charged_usd >= 1.0:
        user.is_pro = True
    # ...
```

- [ ] **Step 2: Update promo_code_service.py**
Update `redeem_promo_code_for_user` in `backend/app/services/promo_code_service.py` to track charges from promo codes.

```python
async def redeem_promo_code_for_user(...):
    # ...
    if charge_amount_usd > 0:
        user.total_charged_usd = (user.total_charged_usd or 0.0) + charge_amount_usd
        if user.total_charged_usd >= 1.0:
            user.is_pro = True
    # ...
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/bot.py backend/app/services/promo_code_service.py
git commit -m "feat: implement automatic pro promotion on charge"
```

---

### Task 3: Enforce Pro Restriction in the Bot

**Files:**
- Modify: `backend/app/services/project_sharing.py`
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update project_sharing.py visibility checks**
Update `list_visible_projects` and `user_can_access_project` to check for Pro status.

```python
async def list_visible_projects(db: AsyncSession, user: UserPreference) -> list[Project]:
    if not user.is_admin and not user.is_pro:
        return []
    # ... rest of logic
```

- [ ] **Step 2: Update bot.py cmd_projects command**
Update `cmd_projects` to show the upgrade guide if the user is not Pro.

```python
async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ...
    if not user.is_admin and not user.is_pro:
        text = "🚀 *دسترسی به پروژه‌ها مخصوص کاربران پرو است!*\n\n" \
               "شما می‌توانید با شارژ حداقل **۱ دلار** حساب خود، به قابلیت مدیریت پروژه‌ها و دانش‌نامه اختصاصی دسترسی پیدا کنید.\n\n" \
               "💡 کاربران پرو می‌توانند فایل‌های خود را آپلود کرده و از هوش مصنوعی بخواهند بر اساس آن‌ها پاسخ دهد."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("➕ شارژ و ارتقا", callback_data="account_topup_start")]])
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        return
    # ... rest of logic
```

- [ ] **Step 3: Commit**
```bash
git add backend/app/services/project_sharing.py backend/app/bot.py
git commit -m "feat: enforce pro restriction in bot projects command"
```

---

### Task 4: Admin Panel Updates

**Files:**
- Modify: `backend/app/admin_routes.py`
- Modify: `frontend-v2/src/lib/api.ts`
- Modify: `frontend-v2/src/components/users/UserTable.tsx`
- Modify: `frontend-v2/src/lib/types.ts`

- [ ] **Step 1: Add admin route to toggle pro status**
In `backend/app/admin_routes.py`, add an endpoint to toggle `is_pro`.

```python
@router.post("/users/{user_id}/toggle-pro")
async def toggle_user_pro(user_id: int, db: AsyncSession = Depends(get_session)):
    user = await db.get(UserPreference, user_id)
    user.is_pro = not user.is_pro
    await db.commit()
    return {"is_pro": user.is_pro}
```

- [ ] **Step 2: Update frontend types**
Add `is_pro` and `total_charged_usd` to the `User` interface in `frontend-v2/src/lib/types.ts`.

- [ ] **Step 3: Add API helper**
Add `toggleUserPro` to `frontend-v2/src/lib/api.ts`.

- [ ] **Step 4: Update UserTable UI**
Add a Pro badge and a toggle button to `frontend-v2/src/components/users/UserTable.tsx`.

- [ ] **Step 5: Commit**
```bash
git add backend/app/admin_routes.py frontend-v2/src/lib/api.ts frontend-v2/src/components/users/UserTable.tsx frontend-v2/src/lib/types.ts
git commit -m "feat: add admin toggle for pro status"
```

---

### Task 5: Verification

- [ ] **Step 1: Verify database migration**
Restart the backend and verify that the `user_preferences` table has the new columns.

- [ ] **Step 2: Verify automatic promotion**
Manually update a user's `total_charged_usd` in the DB or simulate a charge, and verify `is_pro` becomes `True`.

- [ ] **Step 3: Verify bot restriction**
Test `/projects` with a non-pro user and verify the upgrade message appears.
Test `/projects` with a pro user and verify projects are listed.

- [ ] **Step 4: Verify admin toggle**
Use the admin panel to toggle a user's pro status and verify it updates in the DB and affects bot access.
