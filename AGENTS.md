# AGENTS.md — Dr. Boz Platform

Guidance for coding agents working in this repository.

## Golden Rules

1. **Commit every change** — Never leave work uncommitted.
2. **Test before reporting** — Verify changes work before telling the user "done."
3. **Surgical changes** — Touch only what the task requires.

## Repo Shape

- `backend/open_webui/` — Dr. Boz API (customized Open WebUI backend)
- `pbozi/backend/app/` — BOZ GPT chatbot
- `auth-app/` — React login SPA source (build output in `dist/`)
- `bale-bot/` — Node.js Bale payments bot
- `nginx/` — Nginx config + Dockerfile
- `docker-compose.yml` — All Docker services
- `setup.sh` — One-command deploy script

## Key Backend Files (Dr. Boz API)

| File | Notes |
|---|---|
| `backend/open_webui/routers/otp_auth.py` | Phone OTP, mock SMS (logs to console) |
| `backend/open_webui/routers/bot_auth.py` | Bale/Telegram login |
| `backend/open_webui/routers/credits.py` | Credit balance + transactions |
| `backend/open_webui/routers/subscriptions.py` | Subscription management |
| `backend/open_webui/utils/spending.py` | Token cost calculation |
| `backend/open_webui/utils/era_db.py` | ERA database connection |
| `backend/open_webui/models/era_db.py` | ERA billing models |
| `backend/open_webui/models/user_credits.py` | Credit tables |
| `backend/open_webui/models/users.py` | Added phone column |

## Key Backend Files (BOZ GPT)

| File | Notes |
|---|---|
| `pbozi/backend/app/bot.py` | Main bot, keep aligned with web chat |
| `pbozi/backend/app/llm.py` | Centralized LLM client + providers |
| `pbozi/backend/app/rag.py` | ChromaDB-based RAG |
| `pbozi/backend/app/main_routes.py` | Web chat + projects |
| `pbozi/backend/app/admin_routes.py` | Admin CRUD |

## Development Commands

### Dr. Boz API (requires the Docker container running)

```bash
# Edit files in backend/open_webui/, then:
docker restart open-webui
```

### BOZ GPT

```bash
cd pbozi/backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 7000
python -m app.bot
```

### Auth app

```bash
cd auth-app
npm run build
# Then deploy: docker cp dist/ drboz-nginx:/usr/share/nginx/html/auth/
```

### Bale bot

```bash
cd bale-bot
docker build -t drboz-bale-bot .
```

## Testing

- Backend Python changes: run import check (`python -c "import module"`), verify startup
- Frontend changes: `npm run build`
- Bot changes: test both web and bot paths

## Secrets

- Never commit `.env` files, tokens, or API keys
- Template files use `YOUR_*_HERE` placeholders
- Real values are set by `setup.sh` at deploy time
