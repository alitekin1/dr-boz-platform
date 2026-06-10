# Rules — JGPTi BozGPT Project

## Project Context
- **Name:** JGPTi / BozGPT
- **Path:** `/root/bozgpt`
- **Platform:** Bale (similar to Telegram, different API base URL)
- **Users:** ~70-80 test users
- **Goal:** AI chatbot like ChatGPT with admin panel, RAG, tools, credit system

## Critical Rules
1. **NEVER touch the production app** running from `/root/.openclaw/workspace/projects/jgpti/`. This workspace is for development/testing only.
2. **NEVER restart the server** — the production app must stay online.
3. All changes happen in `/root/bozgpt` first, then get deployed/replaced after testing.
4. **Surgical changes only** — touch only what the task requires.

## Ports (Development Instance)
- **Backend API:** 8001 (was 8000 — changed to avoid conflict with production)
- **Frontend Admin:** 3001 (was 3000 — changed to avoid conflict with production)
- **Production instance uses 8000/3000** — DO NOT interfere with those.

## API Keys & Secrets
- **Bale Bot Token:** `1346701489:1yT6_JcZF4hOoPmDXl5n5SaUnXR_aRSe9Es` (updated)
- **Bot Platform:** `bale`
- **Bale API Base:** `https://tapi.bale.ai/`
- Never commit keys. Use `.env` only.

## Architecture
- `backend/`: FastAPI, async SQLAlchemy, SQLite, OpenAI-compatible completions, ChromaDB RAG
- `frontend-v2/`: Next.js 16, Persian/RTL admin panel + chat UI
- `docs/`: Architecture notes

## Key Files
- `backend/app/main.py`: FastAPI setup
- `backend/app/main_routes.py`: Web chat + projects + RAG
- `backend/app/admin_routes.py`: Admin CRUD
- `backend/app/llm.py`: LLM client, providers, tools
- `backend/app/bot.py`: Bale/Telegram bot
- `backend/app/models.py` & `schemas.py`: DB models + Pydantic
- `frontend-v2/src/lib/config.ts`: API URL config
- `frontend-v2/src/lib/api.ts`: REST client

## Startup Commands (Dev)
```bash
# Backend
cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8001
# Bot
cd backend && source venv/bin/activate && python -m app.bot
# Frontend
cd frontend-v2 && npm run dev -- --host 0.0.0.0 --port 3001
```

## Coding Agent Instructions
- When fixing a bug or adding a feature, first understand the full context.
- If anything is ambiguous, ASK before coding.
- Write minimal code that solves the problem. No speculative features.
- Keep web chat and bot behavior aligned. Don't duplicate logic.
- Backend owns tool execution — frontend/bot never execute tools.
- Validate inputs before execution (tool names, JSON schema, admin-only paths).
- Keep tool results compact and JSON-safe.
- Use SQLAlchemy/Pydantic, avoid ad-hoc dict manipulation.
- Persian/RTL text must be preserved in UI.

## Testing Before Deploy
1. Run `npm run lint` and `npm run build` for frontend changes.
2. Run import/startup check for backend changes.
3. Test both web chat AND bot paths if shared logic changed.
4. Verify tool calling + RAG if those modules touched.

## Deployment Flow
1. Develop and test in `/root/bozgpt`.
2. Once verified, replace production files (do NOT restart server — use hot-reload or watchers).
3. Monitor logs after deployment.
