# Trial Granting Logic Design

## Overview
Implement the logic and API to allow admins to manually grant a trial subscription to a user. This follows the Trial Subscriptions Implementation Plan (Task 4).

## Architecture
- **Service Layer**: `backend/app/services/trial_service.py` will contain the business logic.
- **API Layer**: `backend/app/admin_routes.py` will expose the manual grant endpoint.

## Components

### 1. TrialService (`backend/app/services/trial_service.py`)
- **Exception `TrialServiceError`**: Custom error for trial-related failures.
- **Method `grant_trial_subscription(db: AsyncSession, user_id: int) -> UserSubscription`**:
    - Validates that the user exists.
    - Checks if the user has already used their trial (`user.trial_used`).
    - Fetches and validates `TrialConfig` (must be enabled and have a `plan_id`).
    - Checks for any existing active subscription for the user.
    - Creates a new `UserSubscription` with the configured plan and duration.
    - Sets `user.trial_used = True`.
    - Records an `AdminAction`.

### 2. Admin API (`backend/app/admin_routes.py`)
- **Endpoint `POST /admin/users/{user_id}/grant-trial`**:
    - Secured by `verify_admin`.
    - Calls `TrialService.grant_trial_subscription`.
    - Handles `TrialServiceError` and returns appropriate HTTP status codes (e.g., 400 Bad Request).

## Data Models
- **UserPreference**: Uses `trial_used` field.
- **TrialConfig**: Provides `plan_id`, `duration_hours`, and `is_enabled`.
- **UserSubscription**: Created upon granting the trial.
- **AdminAction**: Recorded for audit trailing.

## Testing Strategy
- A small test script to verify the logic by mocking the database session or using a test database.
- Manual verification via the admin API once implemented.
