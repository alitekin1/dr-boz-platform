# AGENTS.md

Guidance for coding agents working in this repository. These instructions apply from the repo root unless a nested `AGENTS.md` overrides them.

## Golden Rules

1. **COMMIT EVERY CHANGE** — After every edit, feature addition, or fix, stage the changed files and commit with a clear, concise message. Never leave work uncommitted. If a commit fails or hooks reject it, fix the issue and create a new commit (do not amend the failed one).
2. **READ THE PHASE DOC FIRST** — When the user says "do phase X" (e.g., "do phase 1", "do phase 2"), you MUST read the corresponding plan document at `/root/boz/plans/phase-XX-*.md` before writing any code. Follow the plan's steps, but also check the validation report at `/root/boz/plans/plan-validation-report.md` for known critical issues that must be addressed.
3. **VERIFY BEFORE COMMITTING** — Run lint, typecheck, or import checks appropriate to the change before committing. Do not commit broken code.

## Project Shape

BOZ GPT (also known as JGPTi / دکتر بز) is evolving into a two-part platform:

- `backend/`: FastAPI app using async SQLAlchemy, SQLite by default, OpenAI-compatible chat completions, admin-managed providers/models/prompts/tools, Telegram/Bale bot support, and ChromaDB-based RAG.
- `frontend-v2/`: Vite + Svelte/React app with a chat UI and admin panel.
- `/root/boz/open-webui/`: OpenWebUI integration (SvelteKit + FastAPI) — the new web UI for BOZ GPT. Cloned from https://github.com/open-webui/open-webui.
- `/root/boz/plans/`: Implementation plans for the BOZ GPT + OpenWebUI integration (5 phases + validation report).
- `docs/`: architecture notes, especially `docs/tool-calling.md` for the backend-owned tool-calling flow.

Key backend files:

- `backend/app/main.py`: FastAPI app setup, CORS, router registration, DB init lifespan.
- `backend/app/main_routes.py`: projects, chats, messages, uploads, RAG, web chat LLM/tool orchestration.
- `backend/app/admin_routes.py`: admin CRUD for providers, models, tools, tool bindings, prompts, embeddings, users, stats.
- `backend/app/llm.py`: OpenAI-compatible client, model/provider lookup, system prompts, builtin tools, tool execution.
- `backend/app/rag.py`: document loading/chunking, Google embedding functions, ChromaDB indexing/search.
- `backend/app/models.py` and `backend/app/schemas.py`: SQLAlchemy models and Pydantic API schemas.
- `backend/app/bot.py`: Telegram bot path. Keep behavior aligned with web chat when touching shared chat/tool logic.
- `backend/app/transactions_bot.py`: Separate bot for payment approval/rejection. Runs independently.
- `backend/app/payment_routes.py`: Admin/user payment CRUD, receipt upload, approve/reject flow.

Key frontend files:

- `frontend/src/app/page.tsx`: main Persian/RTL chat experience.
- `frontend/src/app/admin/page.tsx`: admin UI for providers, models, tools, prompts, embeddings, users.
- `frontend/src/lib/api.ts`: REST client. Admin routes attach `Authorization: Bearer ${ADMIN_PASSWORD}`.
- `frontend/src/lib/config.ts`: frontend API URL and current admin password constant.

## Commands

Backend:

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 7000
```

Bots (run separately):

```bash
python bot_watcher.py              # Main chat bot
python transactions_bot_watcher.py # Payment approval bot (requires TRANSACTIONS_BOT_TOKEN)
```

Frontend:

```bash
cd frontend
npm run dev
npm run lint
npm run build
```

There is no obvious backend test suite in the repo today. When changing backend code, at minimum run import/startup checks that are appropriate for the change. When changing frontend code, run `npm run lint` and, for UI/runtime-sensitive changes, `npm run build`.

## Runtime And Data Notes

- The backend default database is `sqlite+aiosqlite:///./jgpti.db`; startup creates tables and applies a small SQLite compatibility migration for tool columns.
- ChromaDB persists to `CHROMA_PERSIST_DIR` or `./chroma_data`.
- Uploaded files go to `./uploads`.
- RAG supports `.pdf`, `.txt`, and `.md` through `backend/app/rag.py`.
- Tool execution is backend-owned. The frontend and Telegram bot should not execute model-requested tools.
- Builtin executable tools currently live in `backend/app/llm.py` and include `calculator` and `web_search`.
- Admin-created tools are metadata/configuration unless the backend ships a trusted handler. Do not implement arbitrary code execution from database records.
- The chat tool loop intentionally executes at most five tool calls and one follow-up completion. Do not turn this into an unbounded loop without explicit need and tests.

## Secrets And Config

- Do not print, commit, or expose real API keys, bot tokens, database URLs, or `.env` contents.
- Prefer environment variables for new secrets. Avoid hardcoded credentials in new code.
- Existing defaults such as `ADMIN_PASSWORD = "admin123"` and frontend `ADMIN_PASSWORD` are part of current behavior; do not broaden their exposure.
- Treat `backend/.env`, local SQLite files, uploads, and Chroma data as local runtime state, not source code.
- Transactions bot requires `TRANSACTIONS_BOT_TOKEN` and `TRANSACTIONS_BOT_ADMIN_CHAT_ID` environment variables.

## Next.js-Specific Rule

Inside `frontend/`, follow `frontend/AGENTS.md`: this is Next.js 16, and APIs/conventions may differ from older Next.js versions. Before using unfamiliar Next.js APIs, inspect the installed docs in `frontend/node_modules/next/dist/docs/` when available.

## Coding Rules

### Think Before Coding

State assumptions explicitly. If multiple interpretations exist, surface them instead of choosing silently. If the requested behavior is unclear enough that a reasonable implementation could be wrong, ask before editing.

### Simplicity First

Write the minimum code that solves the requested problem.

- No speculative features.
- No abstractions for single-use code.
- No configurability that was not requested.
- No large rewrites when a targeted fix is enough.

### Surgical Changes

Touch only what the task requires.

- Do not refactor adjacent code just because it could be cleaner.
- Match the existing style, even when it is not ideal.
- Remove imports, variables, or functions made unused by your own change.
- Do not delete pre-existing dead code unless asked.
- Mention unrelated issues rather than silently fixing them.

### Goal-Driven Execution

For non-trivial tasks, define the success criteria before editing:

```text
1. Change X -> verify with Y
2. Change Z -> verify with W
```

Loop until the relevant verification passes or explain exactly what blocked it.

## Backend Change Guidance

- Keep provider access centralized in `backend/app/llm.py` or a clearly shared runtime module.
- Keep web and Telegram chat behavior aligned. If both paths need the same behavior, avoid duplicating logic in `main_routes.py` and `bot.py`.
- Use SQLAlchemy/Pydantic models instead of ad hoc dict/string manipulation for API and DB changes.
- Validate model/tool inputs before execution, especially tool names, tool binding scope, JSON schema-like arguments, and admin-only paths.
- Keep tool results compact and JSON-safe before appending them to LLM history.
- Be careful with database migrations: this project currently uses `create_all` plus lightweight SQLite compatibility checks, not Alembic.

## Frontend Change Guidance

- Preserve the app's Persian/RTL user-facing text and existing interaction patterns unless the task asks otherwise.
- Keep `frontend/src/lib/api.ts` aligned with backend route contracts.
- Use the existing CSS/Tailwind style in `frontend/src/app/globals.css` and the current component style before introducing new patterns.
- For admin UI changes, update the corresponding backend route/schema/client types together.
- Avoid in-app instructional text unless it is necessary for the feature.
- **UI CONSISTENCY RULE** — Any new design element, UI component, page, or visual feature added to the app must match the existing design language exactly. This means using the same Tailwind classes, color palette, spacing, border radius, shadows, typography, and button/input styles already present in the codebase. Do not introduce custom gradients, colors, fonts, or layouts that deviate from the established design system. When in doubt, copy the exact class string from an adjacent element.

## Verification Expectations

- Frontend-only change: run `npm run lint` from `frontend`; run `npm run build` when behavior or Next.js structure changes.
- Backend route/schema/model change: run a Python import/startup check and exercise the changed endpoint when feasible.
- Tool-calling change: verify both the OpenAI-compatible payload shape and the stored `ToolCall` trace behavior.
- RAG/upload change: verify supported file extensions and avoid requiring network embeddings unless explicitly testing indexing with configured credentials.

If verification cannot be run because dependencies, services, credentials, or network access are missing, state that plainly in the final response.
