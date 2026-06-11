# AGENTS.md — Dr. Boz Platform

This file is the single source of truth for maintaining, updating, and deploying
the Dr. Boz Platform. Read it before making any change. Every lesson from the
original build and migration is captured here.

---

## Architecture Overview

```
Internet :3000 (HTTPS)
  → nginx container (SSL, reverse proxy)
      ├─ /auth/*      → React SPA (pre-built, served by nginx)
      ├─ /api/*       → Dr. Boz API (FastAPI in Docker, port 8080)
      └─ WebSocket    → Real-time chat
           ├─ SQLite: /app/backend/data/webui.db  (users, chats, config)
           ├─ SQLite: /app/backend/data/era.db    (subscription plans, billing)
           └─ Redis:  drboz-redis:6379            (auth codes, sessions)

Dr. Boz API (:8080, Docker)
  └─ Backend code mounted from host: ./backend:/app/backend
  └─ Frontend served from container: /app/build/ (SvelteKit)

Bale Bot (Node.js, Docker)
  └─ Calls Dr. Boz API via X-Bot-Secret header

BOZ GPT (:7000, host/systemd)
  ├─ FastAPI + ChromaDB RAG + LLM tools
  └─ Bale bot (python -m app.bot)
```

## Services Map

| Service | Where | How to restart | Logs |
|---|---|---|---|
| Dr. Boz Web UI + API | Docker: `open-webui` | `docker restart open-webui` | `docker logs open-webui -f` |
| Nginx | Docker: `drboz-nginx` | `docker restart drboz-nginx` | `docker logs drboz-nginx -f` |
| Redis | Docker: `drboz-redis` | `docker restart drboz-redis` | `docker logs drboz-redis -f` |
| Bale Bot | Docker: `drboz-bale-bot` | `docker restart drboz-bale-bot` | `docker logs drboz-bale-bot -f` |
| BOZ GPT API | systemd: `pbozi-api` | `systemctl restart pbozi-api` | `journalctl -u pbozi-api -f` |
| BOZ GPT Bot | systemd: `pbozi-bot` | `systemctl restart pbozi-bot` | `journalctl -u pbozi-bot -f` |

---

## How to Update Each Component

### Backend (Python API) — INSTANT, no rebuild

```bash
# 1. Edit files in /opt/drboz/backend/open_webui/
# 2. Restart the container (takes ~30s to reload)
docker restart open-webui

# 3. Check it came up clean
docker logs open-webui --tail 5
docker exec open-webui curl -s http://localhost:8080/api/v1/billing/public/plans
```

> The backend is mounted as a volume. Any file change takes effect on restart.
> No Docker image rebuild needed. This is the biggest time-saver.

### Frontend (SvelteKit) — NEEDS BUILD, heavy

⚠️ The frontend build needs ~3.5GB RAM peak. On a 4GB server, reset swap first.

```bash
# 1. Edit source files in /opt/drboz/src/
#    (or git clone the repo to get the full src/ directory)

# 2. On a 4GB server, prepare memory:
swapoff /swapfile 2>/dev/null; sleep 2
mkswap /swapfile; swapon /swapfile
sync && echo 3 > /proc/sys/vm/drop_caches
sleep 30

# 3. Build (skip pyodide:fetch to save 2GB RAM)
cd /opt/drboz
NODE_OPTIONS="--max-old-space-size=3072" npx vite build

# 4. Deploy
docker cp build/. open-webui:/app/build/
docker restart open-webui
```

> **If build OOM-kills on a 4GB server:** use the pre-built parts from the repo:
> ```bash
> bash frontend-build-parts/reassemble.sh
> docker cp frontend-build/. open-webui:/app/build/
> docker restart open-webui
> ```
> Then rebuild on a machine with more RAM and update the parts in the repo.

> **If you modified only auth-app (the /auth login page):**
> ```bash
> cd /opt/drboz/auth-app && npm run build
> docker cp dist/. drboz-nginx:/usr/share/nginx/html/auth/
> ```
> This is a small React app, no memory issues (~2s build).

### Bale Bot (Node.js) — rebuild Docker image

```bash
cd /opt/drboz/bale-bot
# Edit index.js, api.js, or messages.js
docker compose -f /opt/drboz/docker-compose.yml build bale-bot
docker compose -f /opt/drboz/docker-compose.yml up -d bale-bot
```

### BOZ GPT Bot (Python, host) — restart systemd

```bash
# Edit files in /opt/drboz/pbozi/backend/app/
systemctl restart pbozi-api pbozi-bot

# Or just the bot (if only bot.py changed):
systemctl restart pbozi-bot
```

### Nginx config

```bash
# Edit /opt/drboz/nginx/nginx.conf
docker compose -f /opt/drboz/docker-compose.yml build nginx
docker compose -f /opt/drboz/docker-compose.yml up -d nginx
```

---

## Critical Files — Complete Map

### Backend: Our Custom Additions

| File | What It Does | Touches |
|---|---|---|
| `backend/open_webui/main.py` | FastAPI entry point, registers ALL routers | Billing, auth, credits |
| `backend/open_webui/routers/otp_auth.py` | Phone OTP: /request, /verify, 123456 bypass | Auth flow |
| `backend/open_webui/routers/bot_auth.py` | Bale/Telegram mini-app + code login | Auth flow |
| `backend/open_webui/routers/billing.py` | 12 endpoints for bot payment flow | Bale bot |
| `backend/open_webui/routers/credits.py` | Credit balance, transactions | User wallet |
| `backend/open_webui/routers/subscriptions.py` | Subscription CRUD, user status | Plans |
| `backend/open_webui/routers/account.py` | ERA billing integration, plan/usage data | Dashboard |
| `backend/open_webui/models/users.py` | Added phone column, get_user_by_phone() | Auth |
| `backend/open_webui/models/user_credits.py` | Credit balance + transaction tables | Wallet DB |
| `backend/open_webui/models/payment_orders.py` | Payment order lifecycle table | Bot payments |
| `backend/open_webui/models/era_db.py` | ERA billing models (plans, billing accounts) | Plans DB |
| `backend/open_webui/models/subscriptions.py` | Subscription table | Plans DB |
| `backend/open_webui/utils/spending.py` | Token cost → toman calculator | Billing |
| `backend/open_webui/utils/era_db.py` | Async connection to era.db | Billing |
| `backend/open_webui/utils/telegram_auth.py` | HMAC-SHA256 initData verification | Auth |
| `backend/open_webui/utils/bale_auth.py` | Bale initData verification | Auth |
| `backend/open_webui/config.py` | PersistentConfig for bot tokens + model pricing | Config |
| `backend/open_webui/env.py` | Fixed bool.lower() type cast error | Config |

### Frontend: Our Custom Components

| File | What It Does |
|---|---|
| `src/lib/components/layout/Sidebar.svelte` | Subscription badge |
| `src/lib/components/layout/Sidebar/UserMenu.svelte` | Plan/usage in user menu |
| `src/lib/components/chat/Chat.svelte` | Credit limits in chat |
| `src/lib/components/chat/LimitReachedState.svelte` | Limit-reached UI |
| `src/lib/components/admin/Users/UserList.svelte` | Admin plan dropdown |
| `src/lib/components/admin/Settings/General.svelte` | Admin billing settings |
| `src/lib/apis/index.ts` | API client |
| `src/lib/apis/auths/index.ts` | Auth API |
| `src/lib/i18n/locales/fa-IR/translation.json` | Persian translations |
| `src/app.html` | RTL direction, Persian fonts |
| `src/routes/+layout.svelte` | Root layout |
| `src/routes/auth/+page.svelte` | Auth page |

### Auth App (separate React SPA at /auth)

| File | What It Does |
|---|---|
| `auth-app/src/App.jsx` | Login: phone OTP + email/password |
| `auth-app/src/api.js` | API client, digit normalization |

### Bale Bot

| File | What It Does |
|---|---|
| `bale-bot/index.js` | Bot logic: plans, orders, wallet, card |
| `bale-bot/api.js` | HTTP client with X-Bot-Secret auth |
| `bale-bot/messages.js` | Persian message templates |

### BOZ GPT Bot

| File | What It Does |
|---|---|
| `pbozi/backend/app/bot.py` | Main chatbot, onboarding, menus |
| `pbozi/backend/app/llm.py` | LLM orchestration, providers, tools |
| `pbozi/backend/app/rag.py` | ChromaDB indexing + search |
| `pbozi/backend/app/main.py` | FastAPI app (port 7000) |
| `pbozi/backend/app/admin_routes.py` | Admin panel CRUD |
| `pbozi/backend/app/main_routes.py` | Web chat + projects + file upload |
| `pbozi/backend/app/payment_routes.py` | Payment approval flow |
| `pbozi/backend/app/transactions_bot.py` | Separate payment bot |
| `pbozi/backend/app/models.py` | All DB models (800+ lines) |

---

## Database Layout

| Database | Location | Engine | Tables |
|---|---|---|---|
| `webui.db` | `/opt/drboz/backend/data/webui.db` | SQLite, async | Users, chats, messages, config, files, credit_transactions, user_credits, subscription |
| `era.db` | `/opt/drboz/backend/data/era.db` | SQLite, async (separate engine) | user_preferences, subscription_plans, user_subscriptions, user_billing_accounts, toman_ledger_entries |
| `jgpti.db` | `/opt/drboz/pbozi/backend/jgpti.db` | SQLite, async | BOZ GPT users, chats, projects, models, providers, tools, payments |
| ChromaDB | `/opt/drboz/pbozi/backend/chroma_data/` | File-based | RAG embeddings |
| Redis | Container `drboz-redis:6379` | In-memory + AOF | auth codes, OTP codes, sessions, bot phone cache |
| Uploads (API) | `/opt/drboz/backend/data/uploads/` | Filesystem | User file uploads |
| Uploads (BOZ GPT) | `/opt/drboz/pbozi/backend/uploads/` | Filesystem | Bot file uploads |

---

## Environment Variables Reference

All set by `setup.sh` in `/opt/drboz/.env`:

| Variable | Default | Where Used |
|---|---|---|
| `BOT_SHARED_SECRET` | (generated) | API ↔ Bale bot auth |
| `TELEGRAM_BOT_TOKEN` | hardcoded | @drboz_bot |
| `TELEGRAM_BOT_USERNAME` | drboz_bot | Telegram integration |
| `BALE_BOT_TOKEN` | hardcoded | @drboz_bale |
| `BALE_BOT_USERNAME` | drboz_bale | Bale integration |
| `BOT_ADMIN_IDS` | comma-separated | Admin approval for card payments |
| `BALE_SAFIR_CLIENT_ID` | (empty) | Safir payment gateway |
| `BALE_SAFIR_CLIENT_SECRET` | (empty) | Safir payment gateway |
| `CARD_HOLDER_NAME` | Persian name | Card-to-card receipt |
| `CARD_NUMBER` | card number | Card-to-card payment |
| `REDIS_URL` | redis://drboz-redis:6379/0 | Cache |
| `WHISPER_MODEL` | base or empty | Speech-to-text |
| `WEBUI_SECRET_KEY` | (auto) | JWT signing |
| `WEBUI_NAME` | Dr. Boz | App title |

BOZ GPT env (`/opt/drboz/pbozi/backend/.env`):

| Variable | Default |
|---|---|
| `BOT_TOKEN` | Bale bot token |
| `BOT_PLATFORM` | bale |
| `ADMIN_PASSWORD` | admin123 |
| `OPENROUTER_API_KEY` | (set) |
| `DATABASE_URL` | sqlite+aiosqlite:///./jgpti.db |
| `REDIS_URL` | redis://127.0.0.1:6379/0 |

---

## Deploying to a New Server — The Full Recipe

This is exactly what `setup.sh` does. Know this in case you need to do it manually.

### Prerequisites
- Ubuntu/Debian, 4GB+ RAM, 20GB+ disk, root access
- Domain pointing to the server

### Step-by-step

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | bash

# 2. Clone the repo
git clone https://github.com/alitekin1/dr-boz-platform.git /opt/drboz
cd /opt/drboz

# 3. Generate .env (or run setup.sh which does this interactively)
# setup.sh writes BOT_SHARED_SECRET and all other env vars

# 4. Generate self-signed SSL
mkdir -p ssl/live
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/live/privkey.pem \
  -out ssl/live/fullchain.pem \
  -subj "/CN=YOUR_DOMAIN"

# 5. Pull images and build
docker compose pull redis
docker compose build nginx bale-bot

# 6. Start
docker compose up -d

# 7. Reassemble frontend (pre-built parts in repo)
bash frontend-build-parts/reassemble.sh
docker cp frontend-build/. open-webui:/app/build/
docker restart open-webui

# 8. Setup BOZ GPT (if needed)
sudo bash pbozi/setup-pbozi.sh

# 9. Get real SSL (after DNS propagates)
sudo bash get-letsencrypt.sh
```

---

## Known Issues & Fixes

### "Billing endpoints return 404"
→ `routers/billing.py` was missing. Fixed in commit `c1a9e41`. Make sure main.py imports `billing` and has `app.include_router(billing.router, prefix='/api/v1/billing')`.

### "Subscription UI not showing"
→ Frontend not deployed. The Docker image has the stock frontend. Must deploy our custom build: `bash frontend-build-parts/reassemble.sh && docker cp frontend-build/. open-webui:/app/build/ && docker restart open-webui`.

### "era.db not found"
→ Copy from old server: `backend/data/era.db`. Without it, billing API returns empty plans.

### "Bale bot Redis connection refused"
→ Redis container must be named `drboz-redis` and on the `drboz-net` network. Check `docker compose ps`.

### "Frontend build OOM-kills on 4GB server"
→ Reset swap, drop caches, wait 30s, use `NODE_OPTIONS="--max-old-space-size=3072"`, skip pyodide. If still fails, use pre-built parts from the repo.

### "BOZ GPT bot not starting"
→ Check `systemctl status pbozi-api pbozi-bot`. The Python venv at `/opt/drboz/pbozi/backend/venv` must exist with all dependencies. Run `bash /opt/drboz/pbozi/setup-pbozi.sh` to recreate.

### "git push fails with Missing or invalid credentials"
→ The git credential manager can break if VSCode socket is missing. Use token in URL:
```bash
git remote set-url origin https://TOKEN@github.com/alitekin1/dr-boz-platform.git
git -c credential.helper="" push origin main
```

---

## Testing Checklist After Any Change

```bash
# 1. Backend: did it restart clean?
docker logs open-webui --tail 5 | grep -i error || echo "clean"

# 2. Billing API works?
docker exec open-webui curl -s http://localhost:8080/api/v1/billing/public/plans | head -1

# 3. OTP endpoint works?
curl -s -X POST http://localhost:8080/api/v1/otp-auth/request \
  -H "Content-Type: application/json" \
  -d '{"phone":"+989123456789"}'

# 4. Frontend serves?
curl -s -o /dev/null -w "%{http_code}" https://localhost:3000/

# 5. Auth page works?
curl -s -o /dev/null -w "%{http_code}" https://localhost:3000/auth/

# 6. Bale bot connected?
docker logs drboz-bale-bot --tail 3 | grep -i "started" && echo "ok" || echo "check logs"

# 7. BOZ GPT running?
systemctl is-active pbozi-api pbozi-bot
```

---

## Commands Cheat Sheet

```bash
# Deploy directory
cd /opt/drboz

# All Docker management
docker compose ps                          # list containers
docker compose logs -f webui               # watch API logs
docker compose restart                     # restart all
docker compose down && docker compose up -d # full restart
docker compose build --no-cache nginx      # rebuild nginx image

# Backend edits (instant deploy)
vim backend/open_webui/routers/whatever.py
docker restart open-webui

# Frontend edits (needs build)
vim src/lib/components/chat/Chat.svelte
# then build + docker cp (see above)

# BOZ GPT
systemctl restart pbozi-api pbozi-bot
journalctl -u pbozi-bot -n 50

# SSL
sudo bash get-letsencrypt.sh

# Database backup
docker exec open-webui cp /app/backend/data/webui.db /app/backend/data/webui.db.bak
docker exec open-webui cp /app/backend/data/era.db /app/backend/data/era.db.bak
```

---

## Secrets — Never Commit

These files are in `.gitignore`:
- `.env` (all env vars with real tokens)
- `backend/.env`
- `pbozi/backend/.env`
- `*.secret`, `*.key`
- `backend/data/` (databases)
- `ssl/live/` (certificates)

Templates with `YOUR_*_HERE` placeholders are safe to commit.
The setup.sh writes real values at deploy time.
