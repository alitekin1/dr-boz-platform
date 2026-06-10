# Tiered Subscriptions & Usage Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the "Tiered Cooldown Subscriptions" business model and the Usage Report in the Telegram bot.

**Architecture:** Extend existing `SubscriptionPlan` and `UserSubscription` models with cooldown and limit tracking fields. Modify the `toman_billing_service` (or `group_billing_service`) to route charges to the user's main balance when the 5-hour cooldown limit is active. Add a `/usage` handler and UI button in the bot to show the status.

**Tech Stack:** FastAPI, SQLAlchemy, Telegram Bot API.

---

### Task 1: Update Database Models

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add new fields to `SubscriptionPlan`**
Modify `backend/app/models.py` around line 862:
```python
class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    plan_type = Column(String, default="monthly_credit")
    monthly_price_usd = Column(Float, default=0.0)
    monthly_price_toman = Column(Integer, default=0)
    gift_credit_toman = Column(Integer, default=0)
    cooldown_limit_toman = Column(Integer, default=0)
    cooldown_hours = Column(Integer, default=0)
    weekly_limit_toman = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    rules = relationship("SubscriptionPlanRule", back_populates="plan", cascade="all, delete-orphan")
    subscriptions = relationship("UserSubscription", back_populates="plan", cascade="all, delete-orphan")
```

- [ ] **Step 2: Add tracking fields to `UserSubscription`**
Modify `backend/app/models.py` around line 891:
```python
class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False, index=True)
    pool_id = Column(Integer, ForeignKey("capacity_pools.id"), nullable=True, index=True)
    status = Column(String, default="active", index=True)
    purchased_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False, index=True)
    cooldown_spent_toman = Column(Integer, default=0)
    cooldown_ends_at = Column(DateTime, nullable=True)
    weekly_spent_toman = Column(Integer, default=0)
    week_resets_at = Column(DateTime, nullable=True)

    user = relationship("UserPreference")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    pool = relationship("CapacityPool", back_populates="subscriptions")
    quotas = relationship("UserSubscriptionQuota", back_populates="user_subscription", cascade="all, delete-orphan")
```

- [ ] **Step 3: Update Schemas**
Modify `backend/app/schemas.py` around `SubscriptionPlanCreate`:
```python
class SubscriptionPlanCreate(BaseModel):
    name: str
    plan_type: str = "monthly_credit"
    monthly_price_usd: float = 0.0
    monthly_price_toman: int = 0
    gift_credit_toman: int = 0
    cooldown_limit_toman: int = 0
    cooldown_hours: int = 0
    weekly_limit_toman: int = 0
    is_active: bool = True
```

- [ ] **Step 4: Commit**
```bash
git add backend/app/models.py backend/app/schemas.py
git commit -m "feat: add tiered subscription fields to models"
```

### Task 2: Implement Tiered Logic in Billing Service

**Files:**
- Modify: `backend/app/services/toman_billing_service.py`

- [ ] **Step 1: Implement `check_tiered_subscription` logic**
In `backend/app/services/toman_billing_service.py`, modify `charge_chat_usage_toman`. Before checking `available < quote.billable_cost_toman`, we need to check if a tiered plan covers this.
Insert the following logic:

```python
    from datetime import datetime, timezone, timedelta
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select

    # Check for active tiered subscriptions
    now = datetime.now(timezone.utc)
    sub_query = select(UserSubscription).options(selectinload(UserSubscription.plan)).where(
        UserSubscription.user_id == user.id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now
    )
    user_sub = (await db.execute(sub_query)).scalar_one_or_none()

    if user_sub and user_sub.plan.plan_type == "tiered_cooldown":
        plan = user_sub.plan
        in_cooldown = user_sub.cooldown_ends_at and now < user_sub.cooldown_ends_at
        if not in_cooldown:
            # We can cover this from the subscription!
            # If cooldown expired, reset it
            if user_sub.cooldown_ends_at and now >= user_sub.cooldown_ends_at:
                user_sub.cooldown_spent_toman = 0
                user_sub.cooldown_ends_at = None
                
            cost = quote.billable_cost_toman
            user_sub.cooldown_spent_toman = (user_sub.cooldown_spent_toman or 0) + cost
            user_sub.weekly_spent_toman = (user_sub.weekly_spent_toman or 0) + cost
            
            # Check if we hit the limit
            if user_sub.cooldown_spent_toman >= plan.cooldown_limit_toman:
                user_sub.cooldown_ends_at = now + timedelta(hours=plan.cooldown_hours)
                # Bot notification logic will be added via middleware or separate async task later
                
            return ChatUsageChargeResult(ok=True, account=account, metadata={"tiered_covered": True, "cost": cost, "reason": "tiered_subscription"})

    # (Existing logic continues below this block...)
    available = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/services/toman_billing_service.py
git commit -m "feat: apply tiered subscription limits in billing"
```

### Task 3: Bot UI - Usage Report

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Add "Usage Report" to Account Menu**
Find `_account_kb` in `backend/app/bot.py` and modify it:
```python
def _account_kb(active: str) -> InlineKeyboardMarkup:
    profile_label = "✅ پروفایل" if active == "profile" else "🧾 پروفایل"
    home_label = "✅ خلاصه حساب" if active == "home" else "👤 خلاصه حساب"
    usage_label = "✅ گزارش مصرف" if active == "usage" else "📊 گزارش مصرف" # NEW
    
    kb = [
        [
            InlineKeyboardButton(home_label, callback_data="account_home"),
            InlineKeyboardButton(profile_label, callback_data="account_profile"),
            InlineKeyboardButton(usage_label, callback_data="account_usage"), # NEW
        ],
        # ... rest of the existing layout
```

- [ ] **Step 2: Handle `account_usage` callback**
In `backend/app/bot.py` inside the callback handler function (e.g., `handle_account_callbacks` or similar):
```python
        elif data in {"account_usage", "account_refresh_usage"}:
            section = "usage"

        # ... later where section is checked to render text ...
        if section == "usage":
            text = await _account_usage_text(db, user, ctx)
```

- [ ] **Step 3: Implement `_account_usage_text`**
Add the new function near `_account_profile_text`:
```python
async def _account_usage_text(db, user: UserPreference, ctx: dict) -> str:
    from app.models import UserSubscription
    from sqlalchemy.orm import selectinload
    from datetime import datetime, timezone
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    sub_query = select(UserSubscription).options(selectinload(UserSubscription.plan)).where(
        UserSubscription.user_id == user.id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now
    )
    user_sub = (await db.execute(sub_query)).scalar_one_or_none()
    
    lines = ["📊 **گزارش مصرف حساب**", ""]
    
    if not user_sub:
         lines.append("شما در حال حاضر اشتراک فعالی ندارید.")
         return "\n".join(lines)
         
    plan = user_sub.plan
    lines.append(f"📦 بسته فعال: {plan.name}")
    
    if plan.plan_type == "tiered_cooldown":
        lines.append(f"🔹 لیمیت دوره‌ای: {user_sub.cooldown_spent_toman or 0:,} / {plan.cooldown_limit_toman:,} تومان")
        if user_sub.cooldown_ends_at and now < user_sub.cooldown_ends_at:
            diff = user_sub.cooldown_ends_at - now
            hours, remainder = divmod(diff.seconds, 3600)
            minutes = remainder // 60
            lines.append(f"⏳ **حساب در وضعیت قفل!**\nبازگشت به مصرف اشتراکی تا {hours} ساعت و {minutes} دقیقه دیگر.")
        else:
            lines.append("✅ در حال استفاده از حجم اشتراک.")
            
        lines.append(f"🔹 مصرف هفتگی: {user_sub.weekly_spent_toman or 0:,} / {plan.weekly_limit_toman:,} تومان")
    else:
        lines.append("این اشتراک ماهیانه عادی است.")
        
    return "\n".join(lines)
```

- [ ] **Step 4: Commit**
```bash
git add backend/app/bot.py
git commit -m "feat: add usage report menu to bot"
```

