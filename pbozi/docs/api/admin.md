# Admin API

Restricted endpoints for system management. All require `Authorization: Bearer <ADMIN_PASSWORD>`.

## System Management

### 1. Telegram Bot Control
- **Status:** `GET /admin/telegram-bot/status`
- **Start:** `POST /admin/telegram-bot/start`
- **Stop:** `POST /admin/telegram-bot/stop`

### 2. Broadcast Message
Sends a message (with optional photo/buttons) to all or targeted users via the Telegram bot.
- **URL:** `POST /admin/broadcast`
- **Form Data:** `message`, `target_groups`, `photo` (file), `buttons` (JSON).

## AI Configuration

### 1. Providers
Manage LLM providers (OpenAI, Anthropic, Google, etc.).
- **List:** `GET /admin/providers`
- **Discover Models:** `POST /admin/providers/discover-models` (Scans the provider's `/models` endpoint).

### 2. Models
Configure specific models, pricing, and capabilities.
- **List:** `GET /admin/models`
- **Create:** `POST /admin/models`
- **Import via CSV:** `POST /admin/models/import-csv`

### 3. Tools & Bindings
Manage AI tool availability (e.g., Python runtime, web search).
- **List Tools:** `GET /admin/tools`
- **Bindings:** `GET /admin/tool-bindings` (Control which tools are enabled for which projects/chats).

## Monitoring

### 1. Global Stats
- **URL:** `GET /admin/stats`
- **Returns:** Counts of providers, models, users, messages, etc.

### 2. Error Logs
- **URL:** `GET /admin/error-logs`
