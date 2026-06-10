# BOZGPT (Dr. Bose) API Reference

This reference documents the primary API endpoints used to control BOZGPT.

## 1. Connection & Authentication

- **Base URL**: `http://localhost:7000/api`
- **Port**: 7000 (standard backend port)
- **Auth**: Most admin endpoints require `Authorization: Bearer <ADMIN_PASSWORD>`.
- **Default Admin Password**: `admin123` (Verify in `backend/app/config.py` or `.env`)

## 2. Messaging

### Individual Message
Send a message to a specific chat session.
- **URL**: `POST /chats/{chat_id}/messages`
- **Body**:
```json
{
  "content": "Message text",
  "model_id": 1,
  "telegram_user_id": 123456
}
```

### Admin Broadcast
Send a message to multiple users via the Telegram bot.
- **URL**: `POST /admin/broadcast` (Requires Admin Auth)
- **Form Data**:
  - `message`: (string) The text to send.
  - `target_groups`: (JSON string) e.g., `["all"]`, `["active"]`.
  - `photo`: (file, optional)
  - `buttons`: (JSON string, optional) Inline buttons.

## 3. User & Account Management

### List All Users
- **URL**: `GET /admin/users` (Requires Admin Auth)
- **Returns**: A list of user profiles including IDs and Telegram IDs.

### Check User Status
- **URL**: `GET /account/status/by-telegram/{telegram_user_id}`

### Learning Preferences Turn
Submit a turn in the multi-step onboarding conversation.
- **URL**: `POST /account/learning-preferences/by-telegram/{telegram_user_id}/turn`
- **Body**: `{"message": "user response"}`

## 4. Projects & Documents

### List Projects
- **URL**: `GET /projects`

### Upload Document
- **URL**: `POST /projects/{project_id}/documents`
- **Form Data**: `file` (Multipart)

## 5. System Stats
- **URL**: `GET /admin/stats` (Requires Admin Auth)
- **Returns**: Global counts of messages, users, etc.
