# Account & Onboarding API

Handles user creation, profile management, and learning preferences onboarding.

## Endpoints

### 1. Normalize Phone Number
Previews how a phone number will be normalized.
- **URL:** `GET /account/normalize-phone`
- **Query Params:** `phone` (string)
- **Response:**
  ```json
  {
    "normalized": true,
    "phone_number": "*******1234"
  }
  ```

### 2. Get Account Status (by Telegram)
Checks if a user exists and their onboarding status.
- **URL:** `GET /account/status/by-telegram/{telegram_user_id}`
- **Response:**
  ```json
  {
    "exists": true,
    "user_id": 1,
    "telegram_user_id": 123456,
    "account_status": "active",
    "onboarding": {
      "missing_phone": false,
      "missing_preferred_name": false,
      "completed": true
    }
  }
  ```

### 3. Get Account Summary
Returns full details for a specific user ID.
- **URL:** `GET /account/summary/{user_id}`

### 4. Learning Preferences Onboarding
A multi-turn conversation to build a user profile.
- **Start:** `POST /account/learning-preferences/by-telegram/{telegram_user_id}/start`
- **Next Turn:** `POST /account/learning-preferences/by-telegram/{telegram_user_id}/turn` (Body: `{"message": "user response"}`)
- **Skip:** `POST /account/learning-preferences/by-telegram/{telegram_user_id}/skip`
- **Finalize:** `POST /account/learning-preferences/by-telegram/{telegram_user_id}/finalize`

### 5. Redeem Promo Code
Redeems a code for a specific user.
- **URL:** `POST /account/promo-codes/by-telegram/{telegram_user_id}/redeem`
- **Body:** `{"code": "PROMO2026", "charge_amount": 0.0}`
