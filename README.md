# Dr. Boz Platform

Persian AI platform with phone OTP auth, Bale/Telegram bot integration, credit billing, and an AI chatbot (BOZ GPT).

## Architecture

```
Internet (HTTPS :3000)
  → nginx (SSL, reverse proxy)
      ├─ /auth/*    → React login SPA
      ├─ /api/*     → Dr. Boz API (FastAPI :8080, Docker)
      │                ├─ SQLite (webui.db + era.db)
      │                └─ Redis (session cache, auth codes)
      └─ WebSocket  → Real-time chat

Bale Bot (Node.js, Docker)
  └─ Plan purchases, wallet/card payments → Dr. Boz API

BOZ GPT (Python, host/systemd, :7000)
  └─ AI chatbot, RAG (ChromaDB), tools, admin panel
```

## Quick Deploy

**Requirements:** Ubuntu/Debian, 4GB+ RAM, 20GB+ disk, root access.

```bash
# Clone
git clone https://github.com/alitekin1/dr-boz-platform.git
cd dr-boz-platform

# Run — handles Docker, Python venv, SSL, everything
sudo bash setup.sh
```

The script asks for your domain name and email, then sets up all services automatically.

After DNS points to the server, get real SSL:
```bash
sudo bash /opt/drboz/get-letsencrypt.sh
```

## Services

| Service | Port | Runtime | RAM |
|---|---|---|---|
| Dr. Boz API + Web UI | 8080 (internal) | Docker | ~1.5 GB |
| Nginx SSL proxy | 3000 (public) | Docker | ~50 MB |
| Redis cache | 6379 (internal) | Docker | ~30 MB |
| Bale payments bot | — | Docker | ~80 MB |
| BOZ GPT chatbot | 7000 | systemd | ~200 MB |

**Total:** ~2 GB peak, fits on 4 GB servers.

## Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy (async), SQLite, Redis
- **Frontend:** SvelteKit (built into Docker image)
- **Auth UI:** React 18 + Vite (served by nginx at `/auth`)
- **Payments bot:** Node.js, ioredis, Bale API
- **BOZ GPT bot:** Python, python-telegram-bot, LangChain, ChromaDB, langgraph
- **Infra:** Docker Compose, systemd, nginx, Let's Encrypt

## Auth Methods

| Method | Endpoint | Description |
|---|---|---|
| Phone OTP | `/api/v1/otp-auth/request` | Sends 6-digit code (mock SMS, logs to console) |
| Phone OTP verify | `/api/v1/otp-auth/verify` | Code `123456` always works (dev bypass) |
| Bale mini-app | `/api/v1/bot-auth/bale/miniapp` | HMAC-SHA256 initData verification |
| Telegram mini-app | `/api/v1/bot-auth/telegram/miniapp` | HMAC-SHA256 initData verification |
| Bot code | `/api/v1/bot-auth/code` | 8-char code from Redis, set by bot daemon |
| Email/password | `/api/v1/auths/signin` | Standard login |

## Billing

- Credit balance per user (toman), stored in `user_credits` table
- Token spending tracked via `utils/spending.py`, calculates toman from model costs
- ERA DB (`era.db`) for subscription plans, billing accounts, ledger entries
- Bale bot handles plan purchases via wallet invoices or card-to-card with admin approval

## Key Custom Files

### Dr. Boz API (Open WebUI fork)

| File | What it does |
|---|---|
| `backend/open_webui/routers/otp_auth.py` | Phone OTP request/verify, mock SMS |
| `backend/open_webui/routers/bot_auth.py` | Bale/Telegram login, code verification |
| `backend/open_webui/routers/credits.py` | Credit balance + transactions |
| `backend/open_webui/routers/subscriptions.py` | Subscription plans + orders |
| `backend/open_webui/models/user_credits.py` | Credit + transaction SQLAlchemy tables |
| `backend/open_webui/models/era_db.py` | ERA billing models (plans, billing accounts, ledger) |
| `backend/open_webui/models/subscriptions.py` | Subscription table |
| `backend/open_webui/utils/spending.py` | Token cost → toman calculator |
| `backend/open_webui/utils/telegram_auth.py` | HMAC-SHA256 initData verification |
| `backend/open_webui/utils/bale_auth.py` | Bale initData verification |
| `backend/open_webui/utils/era_db.py` | Async connection to era.db |
| `backend/open_webui/main.py` | Register our custom routers |
| `backend/open_webui/config.py` | PersistentConfig for bot tokens |
| `backend/open_webui/models/users.py` | Added `phone` column, `get_user_by_phone()` |
| `backend/open_webui/env.py` | Fixed `bool.lower()` type cast on non-string env |

### BOZ GPT Bot

| File | What it does |
|---|---|
| `pbozi/backend/app/bot.py` | Main Bale bot — chat, onboarding, menu, state machine |
| `pbozi/backend/app/main.py` | FastAPI app (port 7000), CORS, router registration |
| `pbozi/backend/app/llm.py` | OpenAI-compatible client, providers, tools, system prompts |
| `pbozi/backend/app/rag.py` | Document loading, ChromaDB indexing, RAG queries |
| `pbozi/backend/app/models.py` | SQLAlchemy models (800+ lines) |
| `pbozi/backend/app/admin_routes.py` | Admin CRUD for models, providers, tools, users |
| `pbozi/backend/app/main_routes.py` | Web chat + project management |
| `pbozi/backend/app/payment_routes.py` | Payment request CRUD, receipt uploads |
| `pbozi/backend/app/transactions_bot.py` | Separate bot for payment approvals |
| `pbozi/backend/app/services/` | Billing, trial grants, subscriptions, wallet, referrals |

### Infrastructure

| File | What it does |
|---|---|
| `docker-compose.yml` | All Docker services with memory limits |
| `setup.sh` | One-command deploy (interactive) |
| `migrate-data.sh` | Copy databases/uploads from old server |
| `nginx/nginx.conf` | SSL proxy, `/auth` SPA routing, Bale iframe CSP |
| `auth-app/dist/` | Pre-built Persian login page |
| `bale-bot/index.js` | Bale payments bot |
| `pbozi/setup-pbozi.sh` | BOZ GPT host setup (venv, systemd) |
| `pbozi/bot_watcher.py` | Auto-restart bot on crash |

## Management

```bash
# View all container status
docker compose -f /opt/drboz/docker-compose.yml ps

# View logs
docker compose -f /opt/drboz/docker-compose.yml logs -f webui

# BOZ GPT logs
journalctl -u pbozi-api -f
journalctl -u pbozi-bot -f

# Restart
docker compose -f /opt/drboz/docker-compose.yml restart
systemctl restart pbozi-api pbozi-bot

# Stop
docker compose -f /opt/drboz/docker-compose.yml down
systemctl stop pbozi-api pbozi-bot
```

## Data Migration

Copy from old server:

```bash
# On OLD server — pack data
cd /root/bozi/open-webui/backend
tar czf /tmp/drboz-data.tar.gz data

cd /bozi/pbozi/backend
tar czf /tmp/pbozi-data.tar.gz jgpti.db* chroma_data/ uploads/

# SCP to new server
scp /tmp/drboz-data.tar.gz root@NEW_IP:/opt/drboz/drboz-data-backup.tar.gz
scp /tmp/pbozi-data.tar.gz root@NEW_IP:/opt/drboz/pbozi-data-backup.tar.gz

# On NEW server — restore
ssh root@NEW_IP
bash /opt/drboz/migrate-data.sh
```

## Environment Variables

Set by `setup.sh` automatically. Key variables in the generated `.env`:

| Variable | Purpose |
|---|---|
| `BOT_SHARED_SECRET` | Shared auth between API and bots |
| `TELEGRAM_BOT_TOKEN` | @drboz_bot token |
| `BALE_BOT_TOKEN` | @drboz_bale token |
| `BOT_ADMIN_IDS` | Admin user IDs (comma-separated) |
| `REDIS_URL` | Redis connection string |
| `WHISPER_MODEL` | Set to `base` or empty to disable |
| `WEBUI_SECRET_KEY` | JWT signing key (auto-generated) |

## Building a Standalone Docker Image

The Dockerfile bakes our backend into a custom image:
```bash
docker build -t ghcr.io/alitekin1/dr-boz-platform:latest .
docker push ghcr.io/alitekin1/dr-boz-platform:latest
```
Then update `docker-compose.yml` to use `image: ghcr.io/alitekin1/dr-boz-platform:latest`
and remove the `./backend:/app/backend` volume mount.

Note: building from source (including SvelteKit frontend) requires 8GB+ RAM.
The Dockerfile above only layers our backend on top of the pre-built base image.

## License

This project is derived from Open WebUI (BSD 3-Clause). All custom Dr. Boz modifications
are also BSD 3-Clause.
