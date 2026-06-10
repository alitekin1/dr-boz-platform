# Toman Subscription Wallet Design

## Overview
Dr Boz subscriptions use a separate toman-denominated credit wallet while global model API pricing remains USD-based. Admins can change the subscription price, gift credit, API markup, first-topup discount, first-topup cap, and USD-to-toman conversion rate without code changes.

## Billing Rules
- Buying a monthly subscription records a toman payment and credits gift balance. Default: 80,000 toman payment, 100,000 toman gift credit.
- Chat usage is calculated from the model's global USD API price using input and output tokens. The USD cost is converted to toman and then marked up. Default markup is 25%.
- User chat cost is debited from gift balance first, then from paid topup balance. Gift credit is not revenue.
- The first paid topup after a subscription receives a discount on the payment amount up to the configured credit cap. Default: 50% discount on up to 300,000 toman credit. The credited amount remains the requested credit amount.
- Later topups use normal payment rules unless a future rule is added.

## Data Model
- Keep existing USD wallet and model pricing fields unchanged for old flows.
- Add `UserBillingAccount` for toman balances and lifetime counters:
  - `gift_balance_toman`, `paid_balance_toman`, `total_gift_granted_toman`, `total_gift_spent_toman`, `total_paid_topup_toman`, `total_paid_spent_toman`, `total_subscription_paid_toman`, `first_topup_discount_used`.
- Add `TomanLedgerEntry` for auditable toman movements:
  - `entry_type`, `amount_toman`, split balances after posting, `usage_event_id`, idempotency key, metadata.
- Extend `SubscriptionConfig` with admin-managed defaults:
  - `monthly_price_toman`, `gift_credit_toman`, `api_markup_percent`, `first_topup_discount_percent`, `first_topup_discount_cap_toman`, `usd_to_toman_rate`.
- Store per-chat billing snapshots in `UsageEvent.metadata_json`:
  - `global_api_cost_usd`, `usd_to_toman_rate`, `api_markup_percent`, `billable_cost_toman`, and the gift/paid split.

## APIs and UI
- Extend admin subscription config endpoints to expose and update all new billing settings.
- Add backend service functions for subscription purchase, topup quote/apply, usage quote, and usage charge.
- Add admin user billing summary endpoint so reports can show gift consumed, topups purchased, subscription payments, and per-chat costs.
- Update frontend-v2 subscription settings to edit toman billing settings instead of free-chat rules.

## Compatibility
Existing USD credit, promo code, and legacy wallet paths remain in place. The new toman wallet is used only by the Dr Boz subscription billing path and can coexist with old USD reports until those flows are migrated separately.
