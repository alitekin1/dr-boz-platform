# Design Spec - Admin Messaging and User List Enhancements

Enhance the Admin UI to support phone number visibility and search, and improve the messaging (broadcast) system to be more user-friendly by supporting phone number resolution and direct messaging from the user list.

## 1. Problem Statement
- The current messaging system requires internal Database IDs, which are not user-friendly for admins.
- Searching for users is limited and doesn't include phone numbers.
- Sending a message to a specific user is a multi-step process (find ID -> copy -> go to messaging -> paste).
- The messaging logic was reported as "not working" (likely due to ID mismatch).

## 2. Proposed Solution

### 2.1 Frontend Enhancements
- **User List (`UserTable.tsx` & `Users.tsx`):**
    - Add a "Phone" column to the user table.
    - Update search logic to include the `phone_number` field.
    - Add a "Message" button to each user row. Clicking this will navigate to the Messaging page with that user's identifiers pre-filled.
- **Messaging Page (`Messaging.tsx`):**
    - Update the "Individual" input to handle pre-filled data (e.g., from URL query params).
    - Support both Telegram ID and Phone Number as valid inputs for specific targeting.

### 2.2 Backend Enhancements
- **Broadcast Endpoint (`admin_routes.py`):**
    - Modify the logic to resolve target identifiers. It will now attempt to find users by:
        1.  Telegram User ID (numeric match)
        2.  Phone Number (string match)
    - Ensure the Bale/Telegram API call uses the correct `telegram_user_id`.
    - Improve error logging and response details.

### 2.3 Safety & Testing
- Implement a temporary "dry run" mechanism for internal verification (logs the payload instead of sending).
- Final delivery will have the real API calls active for user testing.

## 3. Implementation Plan
1.  **Phase 1: Backend Refactor**
    - Update `broadcast_message` in `admin_routes.py` to resolve identifiers.
2.  **Phase 2: Frontend User List**
    - Update `UserTable.tsx` for Phone Number column and Message button.
    - Update `Users.tsx` for phone-based searching.
3.  **Phase 3: Frontend Messaging**
    - Update `Messaging.tsx` to handle pre-filled state and improved input.
4.  **Phase 4: Validation**
    - Verify all UI components render correctly.
    - Verify search and navigation flows.
    - Verify backend resolution logic via logs.

## 4. Success Criteria
- Admin can find a user by phone number.
- Admin can click "Message" on a user to start a broadcast to them.
- Messaging works using Telegram IDs and/or Phone Numbers.
