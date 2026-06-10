# Dr. Boz Platform

Customized AI platform with phone OTP authentication, Bale/Telegram bot integration,
credit system, ERA database billing, and BOZ GPT chatbot.

**Not affiliated with or supported by Open WebUI.** This is a standalone fork with
significant modifications.

## Architecture

| Service | Port | Container | Description |
|---|---|---|---|
| Web UI + API | 8080 (internal) | `drboz-webui` | FastAPI backend + SvelteKit frontend |
| Nginx | 3000 (public) | `drboz-nginx` | SSL reverse proxy, serves `/auth` |
| Redis | 6379 (internal) | `drboz-redis` | Auth codes, session cache |
| Bale Bot | — | `drboz-bale-bot` | Plan purchases, payments |
| BOZ GPT | 7000 (host) | systemd | AI chatbot, RAG, admin panel |

## Quick Deploy (4GB server)

```bash
tar xzf dr-boz-platform.tar.gz
cd dr-boz-platform
sudo bash setup.sh
```

The setup script installs Docker, pulls images, builds custom containers,
generates SSL certificates, and starts everything.

## Customizations vs Open WebUI

- Phone OTP login (`/api/v1/otp-auth`)
- Bale mini-app auto-login (`/api/v1/bot-auth/bale/miniapp`)
- Telegram mini-app auto-login (`/api/v1/bot-auth/telegram/miniapp`)
- Credit system (toman-based balance + transactions)
- Subscription management (plans, orders, ERA DB)
- Bale wallet payments + card-to-card approval flow
- Bot-shared-secret auth for service-to-service calls
- Persian/RTL auth UI (React SPA at `/auth`)
- BOZ GPT integrated chatbot (port 7000)

## Key Files

| File | Purpose |
|---|---|
| `backend/open_webui/routers/otp_auth.py` | Phone OTP request/verify |
| `backend/open_webui/routers/bot_auth.py` | Bale/Telegram login |
| `backend/open_webui/routers/credits.py` | Credit balance + transactions |
| `backend/open_webui/routers/subscriptions.py` | Subscription CRUD |
| `backend/open_webui/models/era_db.py` | ERA billing models |
| `backend/open_webui/utils/spending.py` | Token cost → toman |
| `backend/open_webui/utils/telegram_auth.py` | HMAC-SHA256 verification |
| `backend/open_webui/utils/bale_auth.py` | Bale initData verification |
| `backend/open_webui/main.py` | Includes our custom routers |
| `backend/open_webui/config.py` | PersistentConfig for bot tokens |
| `pbozi/backend/app/bot.py` | BOZ GPT main bot |
| `pbozi/backend/app/llm.py` | LLM orchestration + tools |
| `pbozi/backend/app/rag.py` | ChromaDB RAG |
