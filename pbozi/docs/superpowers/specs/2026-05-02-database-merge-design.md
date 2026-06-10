# Database Merge Design - 2026-05-02

## Goal
Merge two SQLite databases for the JGPTI project, ensuring no data loss and correct handling of duplicate users and records with foreign key relationships.

## Databases
- **Source:** `/root/.openclaw/workspace/projects/jgpti/backend/jgpti.db`
- **Target:** `/root/bozgpt/backend/jgpti.db`

## Merge Strategy

### 1. User Preferences (`user_preferences`)
- Match users by `telegram_user_id`.
- **Duplicate Users:** 
    - Aggregate `credit_balance_usd`.
    - Update `learning_preferences_*` if Source is newer.
- **New Users:** Insert from Source to Target.

### 2. Wallets (`wallets`)
- Maintain 1:1 relationship with `user_preferences`.
- Aggregate `balance_minor`, `available_minor`, and `held_minor` for duplicate users.

### 3. Hierarchical Data (Chats, Projects, Messages, etc.)
- Use a re-mapping strategy for all auto-incrementing Primary Keys.
- Order of operations:
    1. `providers`, `models` (Match by name/slug)
    2. `user_preferences`, `wallets`
    3. `projects`, `system_prompts`
    4. `chats`, `documents`, `uploaded_files`
    5. `messages`, `usage_events`, `credit_ledger_entries`
    6. `telegram_groups`, `telegram_group_members`, `group_usage_events`, `group_usage_shares`
    7. `tool_calls`, `feedback_entries`, `admin_actions`

### 4. Conflict Resolution
- **Universal:** If a record exists in both with a natural unique key (e.g., `telegram_user_id`, `promo_code`), merge or skip based on type.
- **Foreign Keys:** All foreign keys will be updated to point to the new IDs in the Target database.

## Safety & Validation
- **Backups:** Create `.bak` files for both databases before execution.
- **Dry Run:** The script will report planned changes before committing.
- **Verification:** Compare row counts after merge to ensure `Target_Final >= Target_Initial`.

## Tech Stack
- Python 3 with `sqlite3` module.
- Surgical SQL for specific aggregation.
