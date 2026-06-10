# Subscription Model Design

## Overview
Implement a subscription-based pricing model where users can purchase a fixed monthly subscription. Subscriptions grant users a set of free chats with specific token limits per chat, and a flat percentage discount on API costs for subsequent usage once free chats are exhausted.

## Data Architecture
We will use a "Pre-allocated Quotas" (Wallet-style) approach to track usage efficiently.

### New Database Models
1. **`SubscriptionPlan`**
   - `id`: Integer
   - `name`: String (e.g., "Pro")
   - `monthly_price_usd`: Float
   - `is_active`: Boolean
   - `created_at` / `updated_at`

2. **`SubscriptionPlanRule`**
   - `id`: Integer
   - `plan_id`: ForeignKey to `SubscriptionPlan`
   - `model_id`: ForeignKey to `Model`
   - `free_chats_count`: Integer (e.g., 2 free chats)
   - `free_tokens_per_chat`: Integer (e.g., 100,000 tokens limit per free chat)
   - `discount_percent`: Float (e.g., 75.0 for a 75% discount on paid chats)
   - `is_active`: Boolean

3. **`UserSubscription`**
   - `id`: Integer
   - `user_id`: ForeignKey to `UserPreference`
   - `plan_id`: ForeignKey to `SubscriptionPlan`
   - `status`: String ("active", "expired")
   - `purchased_at`: DateTime
   - `expires_at`: DateTime (manual renewal required after 30 days)

4. **`UserSubscriptionQuota`**
   - `id`: Integer
   - `user_subscription_id`: ForeignKey to `UserSubscription`
   - `model_id`: ForeignKey to `Model`
   - `free_chats_remaining`: Integer
   - `chat_token_quotas_json`: JSON (Dictionary mapping `chat_id` to `tokens_remaining`)
   - `discount_percent`: Float (Copied from rule at time of purchase)

## Core Logic (`usage_metering.py`)
1. **Purchase**: When a user purchases a plan, deduct the `monthly_price_usd` from their `credit_balance_usd`. Create a `UserSubscription` active for 30 days. Read all active `SubscriptionPlanRule`s for that plan, and pre-allocate `UserSubscriptionQuota` records.
2. **Pricing Evaluation**: During `chat_completion`, check if the user has an active `UserSubscription`.
   - If active, find the `UserSubscriptionQuota` for the chosen model.
   - **Free Chat Logic**: 
     - If the `chat_id` exists in `chat_token_quotas_json`, deduct tokens from its specific allowance. If the allowance runs out mid-request, charge the remainder at the `discount_percent` rate.
     - If the `chat_id` is NOT in the JSON and `free_chats_remaining > 0`: decrement `free_chats_remaining`, add the new `chat_id` to JSON with max tokens, and evaluate the request against it.
   - **Paid Chat Logic**: If no free chats remain (and the chat isn't an existing free chat slot), apply the `discount_percent` to the standard model cost.
3. **Billing**: If a charge is required (either discounted rate or standard rate), attempt to debit `credit_balance_usd`. If insufficient, fail the request and prompt the user to recharge.

## User Interface & Bot
1. **Admin Panel**: Add a "Subscriptions" settings view to manage `SubscriptionPlan` and `SubscriptionPlanRule` entries.
2. **Telegram Bot / UI**: 
   - When displaying model prices to a subscribed user, strike through the standard price and show the new price calculated using `discount_percent` (e.g., "$1.00 $0.25").
   - Display a "You used X/Y free chats" indicator if applicable.

## Edge Cases & Error Handling
- **Mid-month Rule Changes**: Since `UserSubscriptionQuota` is pre-allocated upon purchase, changes to `SubscriptionPlanRule` will only affect *future* purchases, protecting the current users from sudden contract changes.
- **Token Overage**: The backend usage metering will accurately split a single request's cost if it straddles the boundary of the `free_tokens_per_chat` limit.
