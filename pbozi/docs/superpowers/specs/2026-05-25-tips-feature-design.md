# Tips Feature Design Specification

## Overview
A dynamic, step-by-step guidance system (Tips) for the Telegram bot. It acts as an educational companion, providing users with contextual tips based on their actions (Event-Driven) or scheduled "Did you know?" insights (Smart Scheduled). Administrators can manage these tips via the admin panel.

## 1. Database Architecture
Two new tables will be added to `backend/app/models.py`.

### `Tip` Table
Stores the content and configuration of each tip.
- `id`: Integer, Primary Key
- `trigger_key`: String, Unique (e.g., `model_menu`, `daily_did_you_know`)
- `tip_type`: String (Enum: `event`, `scheduled`)
- `content`: Text (The message sent to the user)
- `is_active`: Boolean (Default: True)
- `delay_seconds`: Integer (Delay before sending after an event, Default: 0)
- `auto_delete_seconds`: Integer (Delay before automatic deletion if ignored, Default: 30)
- `min_account_age_days`: Integer (For scheduled tips, minimum days since registration, Default: 0)
- `created_at`: DateTime
- `updated_at`: DateTime

### `UserTipDismissal` Table
Tracks which users have opted out of specific tips to prevent reappearance.
- `id`: Integer, Primary Key
- `user_id`: Integer, ForeignKey(`user_preferences.id`)
- `tip_id`: Integer, ForeignKey(`tips.id`)
- `dismissed_at`: DateTime
- *Unique Constraint* on (`user_id`, `tip_id`)

## 2. Backend APIs & Admin Panel
- **Admin Routes:** Create `backend/app/admin_tips_routes.py` with full CRUD endpoints for the `Tip` model.
- **Admin UI:** The frontend admin panel will consume these APIs to list, create, edit, and toggle the status of tips.

## 3. Bot Logic & User Interaction
- **Trigger Function:** A helper function `maybe_send_tip(user_id, trigger_key)` will be invoked at specific user actions in the bot.
- **Validation:** It checks if the tip is active, if the user exists, and if the user has a record in `UserTipDismissal` for this tip.
- **Inline Buttons:** 
  - `tip_got_it_{tip_id}`: Immediately deletes the tip message from the chat.
  - `tip_dismiss_{tip_id}`: Deletes the message AND creates a record in `UserTipDismissal`.
- **Auto-Delete:** If the user does not interact with the buttons, an asynchronous background task (`asyncio.sleep`) will automatically delete the message after `auto_delete_seconds`.

## 4. Smart Scheduled Tips
- **Background Task:** A scheduled task will periodically evaluate active `scheduled` tips.
- **Targeting:** It will select users who have not dismissed the tip and meet criteria such as `min_account_age_days` to prevent spamming new users. Rate-limiting logic (e.g., max 1 scheduled tip per day per user) will be applied.

## 5. Security & Error Handling
- Admin endpoints will be secured with existing admin authentication middleware.
- Missing trigger keys in `maybe_send_tip` will silently fail or log a warning without disrupting the main bot flow.
- Message deletion errors (e.g., if the user deleted the chat) will be caught and ignored gracefully.