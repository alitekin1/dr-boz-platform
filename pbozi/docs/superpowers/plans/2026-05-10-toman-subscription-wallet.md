# Toman Subscription Wallet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a toman-denominated Dr Boz subscription wallet while preserving USD model pricing and legacy USD flows.

**Architecture:** Add focused billing models and service functions, then wire them into subscription admin config, reporting, and chat usage metadata. Existing `models.pricing_input/output` remain USD per 1M tokens; the new billing service converts USD usage to toman with an admin-managed rate and markup.

**Tech Stack:** FastAPI, async SQLAlchemy, SQLite compatibility migrations, pytest, React/Vite admin UI.

---

### Task 1: Billing Model and Service

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/database.py`
- Create: `backend/app/services/toman_billing_service.py`
- Test: `backend/tests/test_toman_billing_service.py`

- [ ] Write failing service tests for subscription purchase, first discounted topup, and usage split from gift then paid balance.
- [ ] Add `UserBillingAccount` and `TomanLedgerEntry` models plus SQLite compatibility creation.
- [ ] Implement service helpers for config defaults, purchase, topup quote/apply, chat quote, and debit.
- [ ] Run `pytest backend/tests/test_toman_billing_service.py -q` from repo root.

### Task 2: Admin Config and Reports

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/admin_subscription_routes.py`
- Modify: `backend/app/admin_routes.py`
- Test: `backend/tests/test_admin_subscriptions.py`

- [ ] Update schemas to expose toman config fields.
- [ ] Update subscription config routes to validate and persist billing settings.
- [ ] Add per-user toman billing summary endpoint.
- [ ] Run `pytest backend/tests/test_admin_subscriptions.py -q`.

### Task 3: Chat Billing Integration

**Files:**
- Modify: `backend/app/bot.py`
- Test: `backend/tests/test_toman_billing_service.py`

- [ ] Replace subscription chat cost evaluation with toman billing quote where chat completion usage is charged.
- [ ] Store USD global API cost and toman billed cost in `UsageEvent.metadata_json`.
- [ ] Debit the toman wallet for final chat cost.
- [ ] Run targeted backend tests and an import check.

### Task 4: Admin UI

**Files:**
- Modify: `frontend-v2/src/lib/types.ts`
- Modify: `frontend-v2/src/lib/api.ts`
- Modify: `frontend-v2/src/components/config/SubscriptionList.tsx`

- [ ] Replace free-chat rule focused text with editable billing config fields.
- [ ] Show toman defaults, markup, discount, cap, and exchange rate.
- [ ] Run `npm run lint` and `npm run build` from `frontend-v2`.
