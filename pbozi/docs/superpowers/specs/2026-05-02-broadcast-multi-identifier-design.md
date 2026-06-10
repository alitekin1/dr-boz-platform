# Design Doc - Broadcast Multi-Identifier Resolution

## Goal
Refactor the `broadcast_message` endpoint to support targeting users by internal ID, Telegram ID, or phone number.

## Current State
- The `broadcast_message` endpoint only supports internal database IDs.
- It parses `target_user_ids` from a JSON string.

## Proposed Changes
- Refactor `broadcast_message` in `backend/app/admin_routes.py`.
- Parse `target_user_ids` into a list of generic identifiers.
- Separate identifiers into `id_list` (integers) and `phone_list` (strings).
- Update the SQLAlchemy query to use `or_` across `UserPreference.id`, `UserPreference.telegram_user_id`, and `UserPreference.phone_number`.
- Ensure `UserPreference.telegram_user_id.is_not(None)` is still enforced.

## Implementation Details
- Import `or_`, `cast`, `String` from `sqlalchemy`.
- Iterate through `identifiers` and categorize them based on type and content (numeric vs non-numeric).
- Update the `where` clause.

## Testing Strategy
- Create a test script `backend/app/test_broadcast_query.py`.
- Mock `AsyncSession` and `UserPreference`.
- Verify the query logic correctly filters users based on different identifier types.
- Ensure only users with `telegram_user_id` are included.

## Success Criteria
- Admins can send broadcasts by providing a list of internal IDs, Telegram IDs, or phone numbers.
- The system correctly resolves these to `telegram_user_id` for message delivery.
- Existing functionality (filtering by groups, sending photos) remains intact.
