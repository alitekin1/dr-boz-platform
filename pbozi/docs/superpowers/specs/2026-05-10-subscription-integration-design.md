# Subscription Model Integration Design

## Overview
This document specifies the integration of the subscription backend logic into the Admin REST API, the React Frontend Admin Panel, and the Telegram Bot interactions.

## Backend Admin API
Create a new router `app/admin_subscription_routes.py` (and include it in `main.py`).
**Endpoints**:
1. `GET /admin/subscriptions/plans` - List all plans.
2. `POST /admin/subscriptions/plans` - Create a plan.
3. `PUT /admin/subscriptions/plans/{plan_id}` - Update a plan.
4. `GET /admin/subscriptions/plans/{plan_id}/rules` - List rules for a plan.
5. `POST /admin/subscriptions/plans/{plan_id}/rules` - Create a rule for a plan.
6. `DELETE /admin/subscriptions/rules/{rule_id}` - Delete a rule.

*Note: Deleting a plan should probably be restricted or just allow setting `is_active=False`.*

## Frontend Admin Panel (`frontend-v2`)
1. **Routing & Sidebar**: Add a new item to the sidebar: "اشتراک‌ها" (Subscriptions), pointing to `/admin/subscriptions`.
2. **Main UI**: 
   - A `PlanList` component showing cards or a table of `SubscriptionPlan`s.
   - Inside each Plan view, a `PlanRuleList` to manage `SubscriptionPlanRule`s (selecting a `Model`, setting `free_chats_count`, `free_tokens_per_chat`, `discount_percent`).
3. **API Client**: Update `src/lib/api.ts` with functions for the new subscription endpoints.

## Telegram Bot (`bot.py`)
1. **Profile/Settings Menu**: 
   - In the user's profile/wallet view (`cmd_profile` or similar), add a button "اشتراک‌ها 💎" (Subscriptions).
2. **Plan Discovery & Purchase Flow**:
   - Tapping "اشتراک‌ها 💎" lists available active plans with their price and benefits.
   - Tapping a plan shows a confirmation: "آیا از خرید اشتراک Pro به مبلغ $10.00 مطمئن هستید؟"
   - Confirming calls `purchase_subscription` and deducts from `credit_balance_usd`.
3. **Cost Evaluation Engine Integration**:
   - Replace synchronous calls to `_chat_completion_cost_usd` with `await evaluate_usage_cost(db, user_id, model_id, chat_id, standard_cost, input, output)`.
   - Update both **estimated cost** calculation (before sending to OpenAI/Anthropic) and **actual cost** calculation (after getting final token usage).
   - If a request is fully free (`cost == 0.0`), display appropriate logs to the user (if any are sent) or simply skip billing deductions without error.
