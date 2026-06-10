# Tiered Subscription & Usage Report Design

## 1. Overview
Introduce a third business model: "Tiered Cooldown Subscriptions".
Users purchase a time-bound package that grants access to specific models, constrained by token cost limits (e.g., 50,000 Toman worth of tokens every 5 hours, and a weekly limit). When a user exceeds the 5-hour limit, they enter a "cooldown" phase for 5 hours. During cooldown, they can continue using the service by paying from their primary wallet (`UserBillingAccount` / Pay-As-You-Go).
Additionally, a "Usage Report" (گزارش مصرف) will be added to the Telegram bot to show active limits, cooldown timers, and token usage.

## 2. Database Architecture (Extending Existing Models)

### `SubscriptionPlan` Updates
Add new fields to distinguish standard plans from tiered plans:
- `plan_type` (String, default: `monthly_credit`): Values can be `monthly_credit` or `tiered_cooldown`.
- `cooldown_limit_toman` (Integer, default: 0): e.g., 50,000.
- `cooldown_hours` (Integer, default: 0): e.g., 5.
- `weekly_limit_toman` (Integer, default: 0): e.g., 200,000.

### `UserSubscription` Updates
Add fields to track the user's active consumption and cooldown state:
- `cooldown_spent_toman` (Integer, default: 0): Total spent in the current 5-hour window.
- `cooldown_ends_at` (DateTime, nullable): If set and > `now()`, the user is currently locked out of the free quota and must pay from wallet.
- `weekly_spent_toman` (Integer, default: 0): Total spent in the current week.
- `week_resets_at` (DateTime, nullable): The time when the weekly limit resets.

## 3. Core Logic & Routing

When a user initiates an action that consumes tokens:
1. **Check Subscription:** If the user has an active `tiered_cooldown` subscription:
   - Check if `now() < cooldown_ends_at`.
     - **If YES (in cooldown):** Route payment to `UserBillingAccount` (Pay-As-You-Go).
     - **If NO (not in cooldown):** Proceed with subscription quota.
2. **Quota Deduction:**
   - Calculate token cost in Toman.
   - Add cost to `cooldown_spent_toman` and `weekly_spent_toman`.
3. **Limit Evaluation:**
   - If `cooldown_spent_toman >= cooldown_limit_toman`:
     - Set `cooldown_ends_at = now() + cooldown_hours`.
     - Reset `cooldown_spent_toman = 0` (or we can leave it at max and reset it when cooldown ends). *Decision: Set `cooldown_ends_at` and reset `cooldown_spent_toman` to 0.*
     - Trigger "Limit Reached" notification.
   - Similar check for `weekly_limit_toman` -> sets a separate `weekly_ends_at` or similar lock.

## 4. Telegram Bot Features

### Notifications
- **Limit Reached:** When the user hits the 50k Toman limit, send a message: "شما به سقف مصرف ۵ ساعته خود (۵۰ هزار تومان) رسیدید. تا ۵ ساعت آینده (ساعت X) هزینه استفاده شما از شارژ اصلی‌تان کسر خواهد شد."
- **Cooldown Expiry:** Handled passively upon the next message; if `now() > cooldown_ends_at`, the system simply routes back to the subscription quota.

### Usage Report (گزارش مصرف)
- Add a new button in the Profile/Settings menu: `📊 گزارش مصرف`.
- Output:
  - **Plan Details:** Plan name and type.
  - **5-Hour Quota:** `Current Spent / Limit` (e.g., 48,000 / 50,000).
  - **Cooldown Status:** If locked, "زمان باز شدن قفل: X ساعت و Y دقیقه دیگر".
  - **Weekly Quota:** `Current Weekly Spent / Weekly Limit`.
  - **Pay-As-You-Go Stats:** Total Toman spent from primary balance.
  - **Token Stats:** Total tokens used.

## 5. Self-Review
- *Ambiguity:* How are tokens counted across multiple models for the "Token Stats" in the report? The report will likely aggregate from `usage_events` or similar existing tracking. We will use `UsageEvent` for token sums.
- *Ambiguity:* What happens to `cooldown_spent_toman` when cooldown expires? It's better to explicitly reset it to 0 when evaluating a new request if `now() > cooldown_ends_at`.
- *Scope:* The scope is contained to adding plan fields, updating billing logic in `group_billing_service` or equivalent, and adding the bot UI elements.

## 6. Testing
- Test regular monthly plan to ensure no regressions.
- Test tiered plan before 50k limit.
- Test tiered plan crossing 50k limit (should set cooldown and notify).
- Test tiered plan during cooldown (should deduct from wallet).
- Test tiered plan after cooldown expiry (should reset and deduct from quota).
- Verify the Usage Report displays correct numbers in all states.
