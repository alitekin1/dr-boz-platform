# Codex Capacity Pools Design

## Goal

Implement pool-based routing for Codex subscription accounts so users buy capacity from a pool, not from a direct Codex account, and runtime requests select an active account with available five-hour and weekly capacity.

## Data Model

- `capacity_pools` stores sellable Codex capacity groups: `name`, `max_users`, `active_users`, `status`, `fallback_behavior`, and optional `fallback_model_id`.
- `codex_accounts` keeps its existing login/runtime fields and adds `pool_id`, `status`, `five_hour_limit`, `five_hour_used`, `weekly_limit`, `weekly_used`, `safety_buffer_percent`, and `max_users`.
- `user_subscriptions` adds `pool_id` so an active subscription is attached to one capacity pool for its lifetime.

## Purchase Flow

When a subscription purchase is created, the billing service assigns the new subscription to the first active pool with available user capacity. A pool is available when `status = active` and `active_users < max_users`. If no pool is available, the purchase fails with `codex_capacity_unavailable` before charging or granting subscription credit.

`active_users` is recalculated from active, unexpired subscriptions when subscriptions are created, cancelled, or reactivated.

## Runtime Flow

For Codex subscription providers, runtime selection requires an active user subscription with a `pool_id`. From that pool, the system chooses an authenticated active account with remaining five-hour and weekly capacity after safety buffer is applied. The selected account is the one with the largest effective remaining capacity.

Effective limit is:

```text
limit * (1 - safety_buffer_percent / 100)
```

If no account has capacity, pool fallback behavior is used:

- `reject`: return a capacity error to the caller.
- `fallback_model`: run the same request against `fallback_model_id` when configured.

After a successful Codex CLI call, runtime usage is stored on the account and five-hour/weekly usage counters are incremented from provider usage when available.

## Admin

Admin APIs expose pool CRUD and extend Codex account CRUD with capacity fields. The admin UI shows pools, lets admins set max users and fallback behavior, and lets admins assign accounts to pools and edit account limits, status, safety buffer, and enabled state.

## Verification

- Unit tests cover pool assignment, active user recalculation, account selection with safety buffer, and fallback decision metadata.
- Backend verification runs targeted pytest tests and an import/startup check.
- Frontend verification runs `npm run lint`; `npm run build` is run when UI structure changes.
