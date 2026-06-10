# Referral System Implementation Design

## Context
We need to track user acquisition from different marketing campaigns or groups by generating specialized Telegram start links (e.g., `t.me/bot?start=ref_QWERT`). We need to track the exact timestamps for when a user starts the bot, signs up (completes onboarding), and purchases a subscription (wallet top-up). 

## Architecture & Database

1. **New Table: `ReferralCampaign`**
   - `id`: Integer
   - `code`: String (Unique, e.g., 'ref_QWERT')
   - `description`: Text (e.g., "Group A Ad Campaign")
   - `created_by_admin_id`: Integer (Foreign Key to UserPreference)
   - `created_at`: DateTime
   - `is_active`: Boolean

2. **New Table: `ReferralEvent`**
   - `id`: Integer
   - `campaign_id`: Integer (Foreign Key to ReferralCampaign)
   - `user_id`: Integer (Foreign Key to UserPreference)
   - `event_type`: String (enum: `start`, `signup`, `purchase`)
   - `amount_usd`: Float (Nullable, populated on purchase)
   - `created_at`: DateTime

3. **Modified Table: `UserPreference`**
   - Add `referral_campaign_id`: Integer (Foreign Key to ReferralCampaign, Nullable). This ensures future purchases know which campaign acquired the user.

## Core Bot Logic Modifications

1. **`backend/app/bot.py` -> `cmd_start`**
   - Parse the `start` payload. If it matches `ref_*`:
     - Lookup the campaign by `code`.
     - If valid and `user.referral_campaign_id` is null, set `user.referral_campaign_id = campaign.id`.
     - Insert `ReferralEvent(event_type='start')`.

2. **`backend/app/bot.py` -> Onboarding Completion**
   - Locate where `account_status` changes from pending to `active` (`_mark_onboarding_complete` or similar).
   - If `user.referral_campaign_id` is set, insert `ReferralEvent(event_type='signup')`.

3. **`backend/app/bot.py` or Wallet Logic -> Top-up Success**
   - Locate `_apply_topup_credit` where wallet balance increases.
   - If `user.referral_campaign_id` is set, insert `ReferralEvent(event_type='purchase', amount_usd=amount_usd)`.

## API Endpoints (FastAPI)

Add `backend/app/admin_routes.py` (or a dedicated `referral_routes.py`) endpoints:
1. `GET /admin/referrals`: List all active referral campaigns with aggregate stats.
   - Response: `[{ id, code, description, stats: { starts: 10, signups: 5, purchases: 2, revenue_usd: 15.5 } }]`
2. `POST /admin/referrals`: Create a new referral campaign.
   - Request: `{ description: str }`
   - Generates unique `code` and returns it.
3. `GET /admin/referrals/{campaign_id}/events`: Get detailed funnel timestamps.

## Trade-offs & Scope
- **Time-series focus:** We opted for an Event-Driven architecture instead of simply counting aggregates. This is more resilient, auditable, and allows funnel time-gap analysis.
- **Scope limitation:** Currently purely analytics, no credit rewards are granted to referrers automatically.

## Testing Strategy
- Create a mock campaign in the DB.
- Trigger `cmd_start` with the mock `ref_` code and verify event insertion.
- Complete onboarding and verify the `signup` event.
- Trigger a mock top-up and verify the `purchase` event.
- Ensure API endpoints return correct aggregates.