# Design Spec: Trial Subscriptions Feature

## 1. Problem Statement
The current system only offers a "Starter Credit" (monetary balance) to new users. The user wants to offer a time-limited "Trial Subscription" (e.g., 48 hours of a specific plan) either automatically upon signup or manually via the admin panel. This is intended to give users a full experience of a subscription plan to drive conversions.

## 2. Proposed Solution
Implement a "Trial Subscription" system that allows admins to configure a specific plan and duration as a "Trial". This trial can be automatically applied to new users and manually granted to existing users.

## 3. Architecture & Data Flow

### 3.1 Database Changes
Add a new model `TrialConfig` to `backend/app/models.py`:
- `id` (int, PK)
- `plan_id` (int, FK to `subscription_plans`)
- `duration_hours` (int, default 48)
- `is_enabled` (bool, default False) - overall switch for the trial system
- `apply_automatically` (bool, default False) - if True, new users get the trial on signup
- `welcome_message` (text, optional) - message to send via Telegram when trial is applied

We also need to track if a user has already used their trial. 
Add `trial_used` (bool, default False) to `UserPreference` model.

### 3.2 Backend API (FastAPI)
- **Settings Management:**
  - `GET /admin/trial-config`: Fetch current trial settings.
  - `PATCH /admin/trial-config`: Update trial settings.
- **Manual Grant:**
  - `POST /admin/users/{user_id}/grant-trial`: Manually activate the trial for a specific user (checks `trial_used` flag).

### 3.3 Business Logic
- **Granting Logic:**
  - Create a `UserSubscription` entry with `status="active"`.
  - Set `expires_at = now + duration_hours`.
  - Set `trial_used = True` on the user profile.
  - Call `assign_subscription_pool` (from `codex_capacity_service.py`) to assign the user to a pool if the plan requires it.
  - Record an `AdminAction` for the grant.
- **Automatic Application:**
  - Integrate with the account onboarding/signup flow (likely in `account_service.py` alongside `apply_starter_credit`).

### 3.4 Frontend UI (React)
- **Admin Settings:**
  - A new tab "Trial Settings" in the Subscription management area.
  - Controls to set the plan, hours, and toggles.
- **User Management:**
  - A "Grant Trial" button/icon in the User Table.

### 3.5 Telegram Integration
- Send the `welcome_message` (or a default Persian template) to the user when the trial is activated.

## 4. User Experience (UX)
- **For Admins:** Simple "one-place" configuration. Visibility into which users are on a trial.
- **For Users:** Immediate access to premium features upon joining (if automatic) or as a gift (if manual), with a notification explaining the limited duration.

## 5. Security & Edge Cases
- **Prevention of Double-Trial:** The `trial_used` flag ensures a user cannot get multiple trials even if they delete/re-add the bot or if multiple admins click the button.
- **Plan Validity:** Ensure the configured `plan_id` points to a valid, active plan.
- **Overlap with Existing Subscriptions:** If a user already has an active subscription, the trial should either extend it or (simpler) be blocked/warned about. Given the user's request, we will check if the user has *any* active subscription before granting a trial to avoid confusion.

## 6. Implementation Phases
1. **Phase 1: Database & Schemas** - Add the model and update `UserPreference`.
2. **Phase 2: Backend API** - Implement the settings and grant logic.
3. **Phase 3: Frontend UI** - Build the settings page and update the user table.
4. **Phase 4: Automation & Notification** - Hook into signup and add Telegram alerts.
