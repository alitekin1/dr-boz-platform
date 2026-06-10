# Hybrid Subscription and PAYG Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a hybrid pricing model where users can use a subscription with daily/weekly limits, and automatically fall back to paid balance when limits are reached, with clear bot notifications and a retry mechanism.

**Architecture:**
1.  **Billing Service:** Enforce `weekly_limit_toman` and provide granular failure reasons (cooldown, weekly limit, insufficient balance).
2.  **Bot Logic:** Detect specific billing failures and send localized messages (Farsi) with a "Retry" button.
3.  **Database Seeding:** Ensure the 200,000 Toman plan exists with appropriate limits.

**Tech Stack:** Python, SQLAlchemy, Pydantic, Telegram Bot API (PTB style).

---

### Task 1: Enforce Weekly Limit and Granular Reasons in Billing Service

**Files:**
- Modify: `backend/app/services/toman_billing_service.py`

- [ ] **Step 1: Update `ChatUsageChargeResult` to include failure type**

```python
@dataclass
class ChatUsageChargeResult:
    ok: bool
    account: UserBillingAccount
    global_api_cost_usd: float = 0.0
    base_cost_toman: int = 0
    billable_cost_toman: int = 0
    gift_spent_toman: int = 0
    paid_spent_toman: int = 0
    ledger_entry: TomanLedgerEntry | None = None
    metadata: dict[str, Any] | None = None
    reason: str | None = None  # Will be 'insufficient_toman_credit', 'cooldown_active', 'weekly_limit_hit', etc.
```

- [ ] **Step 2: Implement weekly reset and limit enforcement in `charge_chat_usage_toman`**

```python
    # ... inside charge_chat_usage_toman ...
    if user_sub and user_sub.plan.plan_type == "tiered_cooldown":
        plan = user_sub.plan
        
        # Weekly reset logic
        if not user_sub.week_resets_at or now >= user_sub.week_resets_at:
            user_sub.weekly_spent_toman = 0
            user_sub.week_resets_at = now + timedelta(days=7)
            
        # Weekly limit check
        if plan.weekly_limit_toman > 0 and (user_sub.weekly_spent_toman or 0) >= plan.weekly_limit_toman:
            # Fall back to balance charging but note the reason
            # The current logic already falls through if tiered is not handled.
            pass
        else:
            in_cooldown = user_sub.cooldown_ends_at and now < user_sub.cooldown_ends_at
            if not in_cooldown:
                # ... existing cooldown reset logic ...
                cost = quote.billable_cost_toman
                user_sub.cooldown_spent_toman = (user_sub.cooldown_spent_toman or 0) + cost
                user_sub.weekly_spent_toman = (user_sub.weekly_spent_toman or 0) + cost
                # ...
                return ChatUsageChargeResult(ok=True, ...)
            else:
                # In cooldown, falls through to balance
                pass
```

- [ ] **Step 3: Refine `insufficient_toman_credit` reason when limits are hit**

```python
    # ... after balance check fails ...
    reason = "insufficient_toman_credit"
    if user_sub and user_sub.plan.plan_type == "tiered_cooldown":
        if user_sub.cooldown_ends_at and now < user_sub.cooldown_ends_at:
            reason = "cooldown_limit_reached"
        elif user_sub.plan.weekly_limit_toman > 0 and (user_sub.weekly_spent_toman or 0) >= user_sub.plan.weekly_limit_toman:
            reason = "weekly_limit_reached"
            
    return ChatUsageChargeResult(ok=False, ..., reason=reason)
```

### Task 2: Bot UI - Granular Error Messages and Retry Button

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Add helper for limit-hit text and keyboard**

```python
def _limit_reached_text(reason: str, user_sub: UserSubscription) -> str:
    if reason == "cooldown_limit_reached":
        wait_time = ""
        if user_sub.cooldown_ends_at:
            delta = user_sub.cooldown_ends_at - datetime.now(timezone.utc).replace(tzinfo=None)
            minutes = max(1, int(delta.total_seconds() / 60))
            wait_time = f" حدود {minutes} دقیقه دیگر."
        return f"🚨 لیمیت مصرف دوره‌ای شما به پایان رسیده است.{wait_time}\nمی‌توانید صبر کنید یا با شارژ حساب (PAYG) ادامه دهید."
    elif reason == "weekly_limit_reached":
        return "🚨 لیمیت مصرف هفتگی شما به پایان رسیده است.\nمی‌توانید تا ریست شدن هفته صبر کنید یا با شارژ حساب (PAYG) ادامه دهید."
    return "🚨 لیمیت اشتراک شما به پایان رسیده است."

def _limit_reached_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تلاش مجدد", callback_data="retry_last_prompt")],
        [InlineKeyboardButton("➕ شارژ اعتبار", callback_data="toman_topup_start")]
    ])
```

- [ ] **Step 2: Update message processing to use these helpers**

Find where `charge_chat_usage_toman` is called (likely in `_process_ai_reply` or similar) and handle the new reasons.

### Task 3: Implement Retry Callback Handler

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Add callback handler for `retry_last_prompt`**
This should find the last user message in the current chat and re-trigger the bot's response logic.

### Task 4: Seed the 200,000 Toman Plan

**Files:**
- Create: `backend/seed_subscription_plan.py`

- [ ] **Step 1: Create seeding script**
```python
async def seed():
    plan = SubscriptionPlan(
        name="اشتراک ویژه (Shared)",
        plan_type="tiered_cooldown",
        monthly_price_toman=200000,
        gift_credit_toman=0,
        cooldown_limit_toman=5000, # Example: 5000 Toman usage before cooldown
        cooldown_hours=5,
        weekly_limit_toman=25000, # Example: 25000 Toman usage per week
        is_agentic=True,
        is_active=True
    )
    # ... add to DB ...
```

---
