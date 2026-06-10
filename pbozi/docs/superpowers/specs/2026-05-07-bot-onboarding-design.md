# Bot Onboarding & Admin Features Design Specification

## Overview
This document specifies the design for improving the Telegram bot onboarding experience and adding targeted messaging features to the admin panel.

## Features
1. **Scenario-Based Onboarding:** Users clicking `/start` will see inline buttons with predefined scenarios. Clicking a button silently sends a configured prompt to the LLM.
2. **Targeted Referral Messaging:** Admins can send broadcast messages specifically to users who joined via a specific referral campaign.
3. **Custom Buttons for Admin Messages:** Admins can attach inline buttons to broadcast messages. Buttons can either open a URL or execute a hidden prompt via the LLM.

## Architecture & Database Changes

### 1. Scenario-Based Onboarding
**Database:**
- Create a new table `BotStartScenario`:
  - `id`: Integer, Primary Key
  - `label`: String (Button text)
  - `prompt`: Text (Hidden prompt sent to LLM)
  - `order`: Integer (Display order)
  - `is_active`: Boolean (Default: True)

**Backend API:**
- `GET /admin/start-scenarios`: List all scenarios.
- `POST /admin/start-scenarios`: Create a new scenario.
- `PUT /admin/start-scenarios/{id}`: Update a scenario.
- `DELETE /admin/start-scenarios/{id}`: Delete a scenario.

**Telegram Bot:**
- Update `cmd_start` in `bot.py` to fetch active `BotStartScenario` entries.
- Add `InlineKeyboardMarkup` to the welcome message. Callback data format: `scenario_start_{id}`.
- Create a callback query handler for `scenario_start_.*` that fetches the prompt, creates a user message, and processes it via the LLM (simulating a user typing the prompt).

### 2. Targeted Referral Messaging
**Admin Panel UI:**
- In the existing Broadcast Message form, add a dropdown "Target Audience": "All Users" or specific Referral Campaigns (fetched from the API).

**Backend API:**
- Update the broadcast endpoint to accept an optional `referral_campaign_id`.
- Modify the background task that sends messages to filter users by `referral_campaign_id` if provided.

### 3. Custom Buttons for Admin Messages
**Admin Panel UI:**
- In the Broadcast Message form, add a dynamic list builder for "Buttons".
- Each button has:
  - `label`: String
  - `type`: "url" or "prompt"
  - `value`: String (URL or prompt text)

**Backend API:**
- Update the broadcast endpoint payload to accept an optional `buttons` list.
- Since Telegram callback data is limited to 64 bytes, we cannot store the raw prompt in the button.
- **Database Addition:** Create `AdminMessageButton` table:
  - `id`: Integer, Primary Key
  - `prompt`: Text
  - The broadcast endpoint saves "prompt" buttons to this table before sending messages.
- The background task constructs an `InlineKeyboardMarkup`.
  - For URL buttons: `url=value`
  - For Prompt buttons: `callback_data=admin_btn_{id}`.

**Telegram Bot:**
- Create a callback query handler for `admin_btn_.*` that fetches the prompt from `AdminMessageButton`, creates a user message, and processes it via the LLM.

## Security & Error Handling
- Only Admins can access the management endpoints.
- Callback data handlers must handle cases where the scenario or button ID is deleted (e.g., respond with an alert).
- LLM processing from buttons uses the standard rate-limiting and cost-tracking logic.
