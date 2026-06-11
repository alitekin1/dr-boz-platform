# Dr. Boz Platform — Complete Deployment Guide

This document contains everything needed to deploy the Dr. Boz Platform on a new server.

## Repo

```
https://github.com/alitekin1/dr-boz-platform   (private)
```

Clone with GitHub token or make public temporarily for initial deploy.

---

## Quick Deploy (fresh server, 4GB+ RAM)

### 1. Install

```bash
git clone https://github.com/alitekin1/dr-boz-platform.git /opt/drboz
cd /opt/drboz
sudo bash setup.sh
```

The script asks for:
- Domain name
- Email (for SSL)
- Disable Whisper? (recommended for 4GB: YES)
- Install BOZ GPT bot? (YES if you want the AI chatbot)

### 2. Deploy custom frontend

The Docker image has the stock Open WebUI frontend — **you must deploy our custom frontend** to see subscription UI, upgrade pages, limit bars, Persian labels, etc.

```bash
cd /opt/drboz

# Reassemble the pre-built frontend (split into 2 parts for GitHub)
cat frontend-build-parts/frontend-build-part-* | tar xzf -

# Deploy into container
docker cp frontend-build/. open-webui:/app/build/
docker restart open-webui
```

### 3. Fix billing (if subscription API returns nothing)

The billing router was missing from early deploys:

```bash
cp /opt/drboz/backend/open_webui/routers/billing.py \
   /opt/drboz/backend/open_webui/routers/billing.py  # already there in latest
docker restart open-webui
```

### 4. Verify

```bash
# Check billing API
docker exec open-webui curl -s http://localhost:8080/api/v1/billing/public/plans

# Check frontend has our files
docker exec open-webui ls /app/build/upgrade-bg.svg

# Open in browser
https://YOUR_DOMAIN:3000
https://YOUR_DOMAIN:3000/auth
```

---

## Services Running After Deploy

| Service | Port | Runtime | Logs |
|---|---|---|---|
| Dr. Boz API + Web UI | 8080 (internal) | Docker | `docker logs open-webui -f` |
| Nginx SSL proxy | 3000 (public) | Docker | `docker logs drboz-nginx -f` |
| Redis | 6379 (internal) | Docker | `docker logs drboz-redis -f` |
| Bale payments bot | — | Docker | `docker logs drboz-bale-bot -f` |
| BOZ GPT API | 7000 | systemd | `journalctl -u pbozi-api -f` |
| BOZ GPT Bot | — | systemd | `journalctl -u pbozi-bot -f` |

---

## What We Customized (vs stock Open WebUI)

### Backend (Python)

| File | Feature |
|---|---|
| `routers/otp_auth.py` | Phone OTP login (6-digit code, `123456` bypass) |
| `routers/bot_auth.py` | Bale/Telegram mini-app + code login |
| `routers/billing.py` | 12 endpoints for Bale bot payment flow |
| `routers/credits.py` | Credit balance + transaction history |
| `routers/subscriptions.py` | Subscription status + admin CRUD |
| `routers/account.py` | ERA billing integration, plan/usage data |
| `models/user_credits.py` | Credit + transaction SQL tables |
| `models/payment_orders.py` | Payment order lifecycle table |
| `models/era_db.py` | ERA billing models (plans, billing accounts) |
| `models/subscriptions.py` | Subscription table |
| `models/users.py` | Added phone column, phone lookup |
| `utils/spending.py` | Token cost → toman calculator |
| `utils/era_db.py` | Async connection to era.db |
| `utils/telegram_auth.py` | HMAC-SHA256 initData verification |
| `utils/bale_auth.py` | Bale initData verification |
| `main.py` | Register all our custom routers |
| `config.py` | PersistentConfig for bot tokens, pricing |
| `env.py` | Fixed bool.lower() type cast error |

### Frontend (SvelteKit)

| File | Feature |
|---|---|
| `src/lib/apis/index.ts` | API client with our custom endpoints |
| `src/lib/apis/auths/index.ts` | Auth API with OTP support |
| `src/lib/components/chat/Chat.svelte` | Chat with credit limits |
| `src/lib/components/chat/LimitReachedState.svelte` | Limit-reached UI card |
| `src/lib/components/layout/Sidebar.svelte` | Subscription badge in sidebar |
| `src/lib/components/layout/Sidebar/UserMenu.svelte` | Plan/usage in user menu |
| `src/lib/components/admin/Settings/General.svelte` | Admin billing settings |
| `src/lib/components/admin/Users/UserList.svelte` | Admin user plan management |
| `src/routes/+layout.svelte` | Root layout with RTL |
| `src/routes/auth/+page.svelte` | Custom auth page |
| `src/lib/i18n/locales/fa-IR/translation.json` | Persian translations |
| `src/app.html` | RTL direction, Persian fonts |

### Auth App (`/auth`)

| File | Feature |
|---|---|
| `auth-app/src/App.jsx` | React login: phone OTP + email/password |
| `auth-app/src/api.js` | API client, Persian digit normalization |

### Bale Bot

| File | Feature |
|---|---|
| `bale-bot/index.js` | Plan browsing, wallet + card payments |
| `bale-bot/api.js` | API client with bot-secret auth |

### BOZ GPT Bot

| File | Feature |
|---|---|
| `pbozi/backend/app/bot.py` | Main AI chatbot, onboarding, menus |
| `pbozi/backend/app/llm.py` | LLM client, providers, tools |
| `pbozi/backend/app/rag.py` | ChromaDB RAG |
| `pbozi/backend/app/main.py` | FastAPI on port 7000 |
| `pbozi/backend/app/admin_routes.py` | Admin panel (models, providers, users) |

---

## Common Issues

### Subscription UI not showing
→ Frontend not deployed. Run step 2 above.

### Billing API returns 404
→ Billing router missing. Run step 3 above.

### Bale bot can't connect to Redis
→ Check `docker logs drboz-bale-bot`. Redis container name must be `drboz-redis`.

### era.db not found
→ The ERA database should be at `/opt/drboz/backend/data/era.db`. If missing, copy from old server:
```bash
scp root@OLD_SERVER:/root/bozi/open-webui/backend/data/era.db /opt/drboz/backend/data/
docker restart open-webui
```

### BOZ GPT bot not running
```bash
systemctl status pbozi-api pbozi-bot
journalctl -u pbozi-bot -n 50
```

---

## Management Commands

```bash
# All Docker services
docker compose -f /opt/drboz/docker-compose.yml ps
docker compose -f /opt/drboz/docker-compose.yml restart
docker compose -f /opt/drboz/docker-compose.yml down
docker compose -f /opt/drboz/docker-compose.yml up -d

# BOZ GPT
systemctl restart pbozi-api pbozi-bot
systemctl status pbozi-api pbozi-bot

# SSL renewal
sudo bash /opt/drboz/get-letsencrypt.sh
```

---

## Data Migration from Old Server

```bash
# On OLD server
cd /root/bozi/open-webui/backend
tar czf /tmp/webui-data.tar.gz data/
scp /tmp/webui-data.tar.gz root@NEW_IP:/opt/drboz/

cd /bozi/pbozi/backend
tar czf /tmp/pbozi-data.tar.gz jgpti.db* chroma_data/ uploads/
scp /tmp/pbozi-data.tar.gz root@NEW_IP:/opt/drboz/

# On NEW server
cd /opt/drboz
sudo bash migrate-data.sh
```

---

## Environment Variables (in .env)

| Variable | Purpose |
|---|---|
| `BOT_SHARED_SECRET` | Shared auth key (API ↔ bots) |
| `TELEGRAM_BOT_TOKEN` | @drboz_bot token |
| `TELEGRAM_BOT_USERNAME` | drboz_bot |
| `BALE_BOT_TOKEN` | @drboz_bale token |
| `BALE_BOT_USERNAME` | drboz_bale |
| `BOT_ADMIN_IDS` | Admin Bale user IDs |
| `BALE_SAFIR_CLIENT_ID` | Safir payment gateway |
| `BALE_SAFIR_CLIENT_SECRET` | Safir payment gateway |
| `CARD_HOLDER_NAME` | Card owner name for card-to-card |
| `CARD_NUMBER` | Card number for card-to-card |
| `WHISPER_MODEL` | `base` or empty to disable |
| `WEBUI_SECRET_KEY` | JWT signing key |
| `REDIS_URL` | Redis connection |
