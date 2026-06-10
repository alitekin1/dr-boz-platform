# Auto Routing Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add selectable Auto Router models that classify each message and route the actual response to configured normal models.

**Architecture:** Store auto-router configuration in `models.capabilities`, keep normal provider/model execution in `backend/app/llm.py`, and expose the virtual model through the existing admin Models UI. Runtime chat code resolves a selected model into an execution model before calling the provider.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, pytest, Vite React, TanStack Query, TypeScript.

---

### File Structure
- Modify `backend/app/schemas.py`: allow nullable provider ID, add model type validation inputs through `capabilities`.
- Modify `backend/app/admin_routes.py`: validate normal vs auto-router model saves.
- Modify `backend/app/llm.py`: add auto-router helpers, JSON parsing, target validation, and selected-model resolution.
- Modify `backend/app/main_routes.py`: use resolver before web chat completion and title generation.
- Modify `backend/app/bot.py`: use resolver in Telegram text/image paths where selected model is resolved for completion.
- Add `backend/tests/test_auto_router.py`: backend routing behavior tests.
- Modify `frontend-v2/src/lib/types.ts`: nullable provider ID and typed auto-router capability shape.
- Modify `frontend-v2/src/components/config/ModelForm.tsx`: model type selector and auto-router model selectors.
- Modify `frontend-v2/src/components/config/ModelList.tsx`: Auto badge and nullable provider display.

### Task 1: Backend Router Helpers
- [ ] Write failing tests in `backend/tests/test_auto_router.py` for auto-router config detection, fenced JSON parsing, precedence, fallback, and nested target rejection.
- [ ] Run `cd backend && source venv/bin/activate && pytest tests/test_auto_router.py -q` and verify tests fail because helpers do not exist.
- [ ] Implement helpers in `backend/app/llm.py`.
- [ ] Run the same pytest command and verify it passes.

### Task 2: Admin Validation And Schemas
- [ ] Write failing tests for creating/updating auto-router models with nullable provider and required target config.
- [ ] Run targeted pytest and verify failure.
- [ ] Update `backend/app/schemas.py` and `backend/app/admin_routes.py`.
- [ ] Run targeted pytest and verify pass.

### Task 3: Web Chat Runtime Resolution
- [ ] Write failing tests or import-level checks for resolving Auto selected model before completion.
- [ ] Run targeted check and verify failure.
- [ ] Update `backend/app/main_routes.py` to use the resolver and target model metadata.
- [ ] Run backend tests/import check and verify pass.

### Task 4: Telegram Runtime Resolution
- [ ] Update `backend/app/bot.py` selected-model completion paths to use the same resolver.
- [ ] Run Python import check for `app.bot`.

### Task 5: Admin UI
- [ ] Update `frontend-v2/src/lib/types.ts`.
- [ ] Update `frontend-v2/src/components/config/ModelForm.tsx` with Normal/Auto Router mode and target selectors.
- [ ] Update `frontend-v2/src/components/config/ModelList.tsx` with Auto badge.
- [ ] Run `cd frontend-v2 && npm run lint` and `npm run build`.

### Task 6: Final Verification
- [ ] Run backend targeted tests.
- [ ] Run backend import/startup check.
- [ ] Run frontend lint/build if dependencies are available.
- [ ] Review `git diff --stat` and ensure unrelated dirty files were not changed.
