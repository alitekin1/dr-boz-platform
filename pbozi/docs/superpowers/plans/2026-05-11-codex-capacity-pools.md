# Codex Capacity Pools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add capacity pools for Codex subscription accounts, including purchase-time pool assignment, runtime account routing, admin controls, and fallback behavior.

**Architecture:** Keep capacity logic in a backend service module consumed by billing and Codex runtime. Extend existing SQLAlchemy models and SQLite compatibility migrations, then expose admin APIs and a compact admin UI.

**Tech Stack:** FastAPI, async SQLAlchemy, SQLite compatibility migrations, pytest, React/Vite, TanStack Query.

---

### Task 1: Backend Capacity Service

**Files:**
- Create: `backend/app/services/codex_capacity_service.py`
- Modify: `backend/tests/test_codex_capacity_service.py`

- [ ] Write failing tests for pool assignment, active-user recalculation, account selection with safety buffer, and fallback metadata.
- [ ] Implement service functions that create deterministic DB queries and do not execute arbitrary account logic.
- [ ] Run targeted pytest for the new service tests.

### Task 2: Models, Schemas, Migrations

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/database.py`

- [ ] Add `CapacityPool`, relationships, and new capacity columns.
- [ ] Add Pydantic create/update/out schemas.
- [ ] Add SQLite compatibility DDL for existing databases.
- [ ] Run model import/startup checks.

### Task 3: Purchase And Runtime Integration

**Files:**
- Modify: `backend/app/services/toman_billing_service.py`
- Modify: `backend/app/services/subscription_service.py`
- Modify: `backend/app/services/codex_runtime.py`
- Modify: `backend/app/llm.py`
- Modify: `backend/app/admin_subscription_routes.py`

- [ ] Assign pools during subscription purchase before money/credit mutations.
- [ ] Recalculate active pool users on cancel/reactivate.
- [ ] Route Codex requests through selected pool account when user context is available.
- [ ] Increment account five-hour and weekly usage after successful runs.
- [ ] Return fallback metadata for callers when no account has capacity.

### Task 4: Admin APIs And Frontend

**Files:**
- Modify: `backend/app/admin_routes.py`
- Modify: `frontend-v2/src/lib/types.ts`
- Modify: `frontend-v2/src/lib/api.ts`
- Modify: `frontend-v2/src/components/config/CodexAccountList.tsx`
- Modify: `frontend-v2/src/components/config/SubscriptionList.tsx`

- [ ] Add capacity pool CRUD routes.
- [ ] Extend Codex account routes for editable pool and capacity fields.
- [ ] Add frontend types and API functions.
- [ ] Add admin controls for pool and account capacity settings.

### Task 5: Verification

**Files:**
- No code changes expected.

- [ ] Run targeted backend pytest.
- [ ] Run backend import/startup check.
- [ ] Run frontend lint and build if UI structure changed.
