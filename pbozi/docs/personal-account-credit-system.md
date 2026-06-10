# Personal Account, Credit System, Admin Controls, Feedback, and Media UX

This document is an implementation blueprint for the Telegram bot account and billing layer. It is written for the current JGPTi shape:

- `backend/` is FastAPI with async SQLAlchemy.
- `backend/app/bot.py` owns Telegram conversation flow.
- `backend/app/main_routes.py` owns web chat and upload routes.
- `backend/app/llm.py` owns provider/model access and tool execution helpers.
- `backend/app/admin_routes.py` owns admin APIs.
- `frontend/` has an admin panel and REST client.

The design is ledger-first. Cached balances are allowed for speed, but the ledger is the accounting source of truth.

## 1. Requirement Extraction

### Product requirements

1. Every Telegram user must have a personal account before using paid AI features.
2. Telegram shared phone number is the primary account identity anchor.
3. Telegram `user_id` is a login/binding identity, not the primary account identifier.
4. New users must share phone number, then provide a preferred name.
5. Existing users sharing an already-known phone number should restore/login to the existing account.
6. Preferred name is editable profile data.
7. Advanced onboarding and personalization questions are postponed.
8. Every account has a credit wallet.
9. Paid operations must deduct credit: chat completions, embedding/indexing, file processing, image analysis, and future paid tools.
10. Pricing must support multiple providers, models, and operation types.
11. Billing must be auditable through usage records and ledger entries.
12. Admins must manage users, credit, status, usage, feedback, and low-level billing records.
13. Admin credit changes and sensitive account actions must be logged.
14. User deletion should be status-based soft deletion/deactivation.
15. The bot should occasionally ask for feedback after meaningful answers only.
16. Feedback must be linked to the user, chat, user message, and assistant answer where possible.
17. File/image captions are user instructions and should be answered naturally.
18. No-caption file/image handling should infer intent from context or ask one concise clarification.

### Non-goals for this phase

1. Payment gateway integration.
2. Invoices, taxes, and accounting export.
3. Advanced personalization questions.
4. Arbitrary code execution from admin-created tools.
5. Multi-currency wallet settlement beyond storing a wallet currency field.

### Acceptance criteria

1. A new Telegram user cannot use paid model calls until phone and preferred name are captured.
2. A returning user can restore account by sharing the same normalized phone number.
3. Every balance-changing operation creates a ledger entry with before/after traceability.
4. Every paid model or embedding operation creates a usage event linked to ledger entries.
5. Admin can add, subtract, and correct credit without mutating historical ledger rows.
6. Admin can suspend/deactivate users without deleting financial history.
7. Rating prompts are sampled and rate-limited.
8. Image/file captions are not echoed as meta text such as "you asked".
9. No-caption media prompts are concise and not repeated robotically.

## 2. Specialized Sub-Agent Workstreams

### 2.1 Product Requirement Extraction

Scope: Convert the business-critical request into clear product and engineering requirements.

Inputs:

- User request.
- Existing Telegram bot behavior.
- Existing admin and model/provider configuration.

Outputs:

- PRD-style requirements.
- MVP versus scalable version.
- Acceptance criteria.

Assumptions:

- The product will eventually accept real payments, but this phase can use manual admin credit adjustments.
- Credit is denominated in USD-equivalent value unless product chooses another currency.

Technical risks:

- Overbuilding personalization before billing correctness.
- Conflating Telegram identity with account identity.

Implementation notes:

- Keep account creation to phone plus preferred name.
- Add future onboarding fields as nullable/profile metadata only.

### 2.2 Account and Authentication Flow

Scope: Account creation, restore, Telegram identity binding, and account status gates.

Inputs:

- Telegram `effective_user.id`.
- Telegram shared contact payload.
- Existing user/profile records.

Outputs:

- `account_service.py`.
- Normalized phone lookup.
- Account status state machine.

Assumptions:

- A valid Telegram native contact share proves the phone belongs to the Telegram user when `contact.user_id == effective_user.id`.
- Phone number must be normalized before uniqueness checks.

Technical risks:

- Duplicate accounts from unnormalized phone formats.
- Account takeover if users can submit arbitrary phone text instead of Telegram native contact.
- Conflicts when one Telegram ID is already bound to another phone account.

Implementation notes:

- Accept only Telegram contact-sharing for account verification.
- Reject contacts where `contact.user_id` is present and differs from `effective_user.id`.
- Store phone in normalized E.164-like format.
- Preserve phone history for account recovery and audits.

### 2.3 Credit Ledger and Billing Architecture

Scope: Wallet, balance, ledger entries, holds, captures, refunds, and admin adjustments.

Inputs:

- User account.
- Usage event.
- Admin adjustment request.

Outputs:

- `wallet_service.py`.
- Ledger table.
- Wallet table with cached balance.
- Idempotent charge/refund APIs.

Assumptions:

- Cached wallet balance is maintained for fast reads.
- Ledger is the source of truth and must never be edited in place.

Technical risks:

- Float precision errors.
- Race conditions causing negative balance.
- Double charges on retries.

Implementation notes:

- Store money as integer minor units, for example `usd_micro` or cents. For AI usage, micro-USD is safer than cents.
- Use idempotency keys for each billable operation.
- Use database transactions and row locks where available.
- Keep old `credit_balance_usd` only as migration/display compatibility until replaced.

### 2.4 Pricing and Usage Metering

Scope: Pricing configuration, pricing snapshots, token extraction, and usage event lifecycle.

Inputs:

- Provider/model configuration.
- Provider response usage payload.
- Operation type: chat, embedding, image, file, tool.

Outputs:

- `pricing_service.py`.
- `usage_metering.py`.
- Immutable usage records.

Assumptions:

- Providers may use different usage field names.
- Some providers may omit usage data.

Technical risks:

- Historical usage becoming unexplainable after pricing edits.
- Undercharging when providers omit usage.
- Billing chat follow-up calls incorrectly when tools are used.

Implementation notes:

- Store `pricing_snapshot_json` on each usage event.
- Keep pricing configuration separate from usage records.
- Meter both initial tool-capable completion and follow-up completion.
- Mark usage source as `provider_reported`, `estimated`, or `manual`.

### 2.5 Telegram Bot UX and Conversation Flow

Scope: `/start`, account panel, insufficient credit, onboarding, media, and feedback prompts.

Inputs:

- Telegram updates.
- Account status.
- Wallet state.
- Current chat/project/model.

Outputs:

- Account gate before paid operations.
- Native contact keyboard.
- Clear onboarding state transitions.

Assumptions:

- User-facing bot language remains Persian/RTL.
- Admin bypasses some gates but still produces usage/audit logs.

Technical risks:

- Blocking legitimate users due to incomplete old account data.
- Asking repetitive clarification prompts after media uploads.

Implementation notes:

- Centralize account gating instead of duplicating checks in each handler.
- Store pending media intent once in `context.user_data`.
- Avoid sending caption echo messages before final answer.

### 2.6 Admin Management and Permissions

Scope: Admin user management, credit adjustment, audit trails, and safe user status changes.

Inputs:

- Admin token/current admin identity.
- User records.
- Wallet/ledger/usage records.

Outputs:

- Admin endpoints.
- Admin panel views.
- `admin_actions` audit log.

Assumptions:

- Current admin auth is bearer password-based.
- Future version may add real admin users/RBAC.

Technical risks:

- Admin raw balance edits bypassing ledger.
- Hard deletes breaking audit and accounting.
- Admin mistakes without reversal path.

Implementation notes:

- Remove direct balance patching from generic user update.
- Use explicit credit adjustment endpoint.
- Replace user delete with `status='deleted'` plus `deleted_at`.
- Log before/after JSON for sensitive actions.

### 2.7 AI Answer Feedback and Rating System

Scope: Feedback sampling, Telegram rating controls, storage, cooldowns, and admin review.

Inputs:

- User message.
- Assistant message.
- Recent feedback prompt history.

Outputs:

- `feedback_service.py`.
- Rating prompt rules.
- Feedback records linked to messages.

Assumptions:

- Inline thumbs-up/down buttons are acceptable for MVP.
- Telegram reactions can be added later if supported by the bot library/version.

Technical risks:

- Annoying users with frequent prompts.
- Asking for ratings after trivial greetings/errors.
- Duplicate feedback for one answer.

Implementation notes:

- Rate-limit by user and by chat.
- Store one feedback row per assistant message per user.
- Keep feedback prompt itself out of LLM context unless useful for future analytics.

### 2.8 Media, File, and Image Caption Behavior

Scope: Caption handling, no-caption fallback, media intent inference, file extraction, and media billing.

Inputs:

- Telegram document/photo message.
- Caption.
- Recent chat context.
- Current project and model capabilities.

Outputs:

- `media_service.py`.
- Natural media response behavior.
- Usage events for billable media processing.

Assumptions:

- Supported RAG file extensions remain `.pdf`, `.txt`, `.md` for now.
- Vision/image analysis depends on the selected model capability.

Technical risks:

- Charging for unsupported file processing.
- Using caption as both user-visible echo and model instruction.
- Repeating clarification messages on every no-caption upload.

Implementation notes:

- Caption should become the user instruction directly.
- No-caption media should inspect recent user intent first.
- If clarification is needed, ask exactly one concise question and store pending media.

### 2.9 Database Schema and Audit Logging

Scope: Tables, relationships, indexes, migrations, and auditability.

Inputs:

- Current SQLAlchemy models.
- Billing/accounting requirements.

Outputs:

- New SQLAlchemy models.
- SQLite compatibility migration for MVP.
- Postgres-ready schema.

Assumptions:

- SQLite is acceptable for local/demo MVP.
- Production billing should move to Postgres.

Technical risks:

- SQLite write concurrency with wallet locks.
- Missing indexes on ledger/usage tables.
- Losing historical pricing integrity.

Implementation notes:

- Add indexes on phone, Telegram ID, user/status, ledger user/date, usage user/date/status.
- Do not update or delete ledger rows except in local development resets.
- Add explicit migration/backfill script if current SQLite data matters.

### 2.10 Edge Cases and Rollout Plan

Scope: Failure modes, migration strategy, rollout stages, and monitoring.

Inputs:

- Existing user records.
- Existing partial credit/feedback implementation.

Outputs:

- Edge case handling matrix.
- Rollout checklist.
- Testing plan.

Assumptions:

- Existing users may have `phone_number` missing or incomplete.
- Existing ledger rows may use float amounts.

Technical risks:

- Blocking existing users unexpectedly.
- Double charging during retry/error paths.
- Admin UI showing stale balances.

Implementation notes:

- Start in observe-only mode.
- Backfill wallets from current `credit_balance_usd`.
- Reconcile cached wallet balances from ledger before enforcement.

## 3. Suggested System Design

### Runtime components

`AccountService`

- Creates users.
- Restores accounts by normalized phone.
- Binds Telegram identity.
- Manages statuses: `pending_phone`, `pending_name`, `active`, `suspended`, `deactivated`, `deleted`.

`WalletService`

- Owns wallet balance and ledger writes.
- Provides `authorize`, `capture`, `release_hold`, `charge`, `refund`, and `admin_adjust`.
- Enforces no negative balance by default.

`PricingService`

- Resolves active pricing for model/provider/operation.
- Creates immutable pricing snapshots.
- Calculates estimated and actual costs.

`UsageMeteringService`

- Creates usage events before paid operations.
- Updates usage with provider tokens/units.
- Links usage to ledger entries.

`AdminService`

- User lookup.
- Profile/status updates.
- Credit adjustments.
- Usage/ledger inspection.
- Soft delete/deactivation.

`AdminAuditService`

- Writes `admin_actions`.
- Stores actor, target, reason, before/after data, request metadata.

`FeedbackService`

- Decides whether to ask for rating.
- Stores feedback.
- Prevents repeated prompts.

`MediaService`

- Downloads and stores Telegram files/photos.
- Extracts supported file text.
- Builds vision payloads.
- Determines caption/no-caption behavior.

### Event flow for paid chat

1. Bot receives user message.
2. Account gate verifies active account.
3. Model/provider are resolved.
4. Pricing snapshot is created.
5. Usage event is created with estimated tokens/cost.
6. Wallet hold or pre-check confirms sufficient credit.
7. Provider call runs.
8. Provider usage is extracted.
9. Actual cost is calculated from the pricing snapshot.
10. Ledger capture/deduction is written.
11. Assistant message is stored with usage reference.
12. Optional feedback prompt is sampled.

### Event flow for embedding/indexing

1. User uploads supported file in project context.
2. Account gate verifies active account.
3. File is downloaded and text/token estimate is produced.
4. Embedding pricing snapshot is created.
5. Wallet hold/pre-check is made.
6. Indexing runs.
7. Actual/estimated embedding units are stored.
8. Ledger deduction is captured.
9. Document and uploaded file records are linked to usage.

## 4. Database Schema

### `users`

Purpose: Account identity root.

Fields:

- `id`
- `primary_phone_e164`, unique, nullable during migration only
- `status`: `pending_phone`, `pending_name`, `active`, `suspended`, `deactivated`, `deleted`
- `status_reason`
- `created_at`
- `updated_at`
- `deleted_at`

Indexes:

- unique `primary_phone_e164`
- `status`

### `user_profiles`

Purpose: Editable profile information.

Fields:

- `id`
- `user_id`, unique FK `users.id`
- `preferred_name`
- `first_name`
- `username`
- `locale`
- `timezone`
- `metadata_json`
- `created_at`
- `updated_at`

### `telegram_identities`

Purpose: Telegram login/binding records.

Fields:

- `id`
- `user_id`, FK `users.id`
- `telegram_user_id`, unique
- `telegram_chat_id`
- `telegram_username`
- `telegram_first_name`
- `is_active`
- `first_seen_at`
- `last_seen_at`
- `created_at`

Indexes:

- unique `telegram_user_id`
- `user_id`

### `phone_history`

Purpose: Auditable phone changes and account recovery history.

Fields:

- `id`
- `user_id`
- `phone_e164`
- `is_primary`
- `verified_via`: `telegram_contact`, `admin`
- `replaced_at`
- `created_at`

### `wallets`

Purpose: Cached account balance.

Fields:

- `id`
- `user_id`, unique
- `currency`, default `USD`
- `balance_minor`, integer
- `available_minor`, integer
- `held_minor`, integer
- `allow_negative`, boolean default false
- `version`, integer
- `created_at`
- `updated_at`

Note: For AI billing, use micro-USD as minor unit if tiny charges matter. If product wants user-facing cents only, still store micro-USD internally and round display values.

### `credit_ledger`

Purpose: Immutable accounting ledger.

Fields:

- `id`
- `wallet_id`
- `user_id`
- `direction`: `credit`, `debit`, `hold`, `release`
- `amount_minor`
- `balance_after_minor`
- `available_after_minor`
- `held_after_minor`
- `entry_type`: `admin_adjustment`, `chat_completion`, `rag_embedding`, `file_processing`, `image_analysis`, `refund`, `authorization_hold`, `hold_release`
- `status`: `posted`, `pending`, `voided`
- `usage_event_id`, nullable
- `admin_action_id`, nullable
- `idempotency_key`, unique
- `reason`
- `metadata_json`
- `created_at`

Rules:

- Never edit posted ledger rows.
- Corrections are new ledger rows.
- All balance-changing writes go through `WalletService`.

### `usage_events`

Purpose: Explain what was consumed and why credit changed.

Fields:

- `id`
- `user_id`
- `chat_id`
- `message_id`
- `uploaded_file_id`
- `operation_type`: `chat_completion`, `embedding`, `file_processing`, `image_analysis`, `tool_call`
- `channel`: `telegram`, `web`, `admin`
- `provider_id`
- `provider_name_snapshot`
- `model_id`
- `model_name_snapshot`
- `pricing_snapshot_json`
- `request_payload_hash`
- `provider_request_id`
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `units`
- `usage_source`: `provider_reported`, `estimated`, `manual`
- `estimated_cost_minor`
- `actual_cost_minor`
- `status`: `estimated`, `authorized`, `completed`, `failed`, `refunded`, `billing_failed`
- `error`
- `created_at`
- `completed_at`

### `model_pricing`

Purpose: Versioned pricing configuration.

Fields:

- `id`
- `provider_id`
- `model_id`, nullable for provider-level operation pricing
- `operation_type`
- `currency`
- `input_per_1m_minor`
- `output_per_1m_minor`
- `unit_price_minor`
- `minimum_charge_minor`
- `effective_from`
- `effective_to`
- `is_active`
- `created_at`
- `updated_at`

Rules:

- New prices create a new row or close the previous effective window.
- Usage events store snapshots, so old usage remains explainable.

### `admin_actions`

Purpose: Audit log for sensitive admin operations.

Fields:

- `id`
- `admin_user_id`
- `admin_telegram_user_id`
- `action_type`
- `target_type`
- `target_id`
- `before_json`
- `after_json`
- `reason`
- `ip_address`
- `user_agent`
- `created_at`

### `assistant_feedback`

Purpose: User rating of assistant answers.

Fields:

- `id`
- `user_id`
- `telegram_user_id`
- `chat_id`
- `user_message_id`
- `assistant_message_id`
- `rating`: `1`, `-1`, optional `0` for skipped/neutral later
- `source`: `telegram_inline_button`, `telegram_reaction`, `web`
- `note`
- `reaction_raw_text`
- `sample_reason`
- `created_at`

Constraints:

- unique `(user_id, assistant_message_id, source)` where possible.

### `uploaded_files`

Purpose: File/photo audit and processing trace.

Fields:

- `id`
- `user_id`
- `chat_id`
- `project_id`
- `telegram_file_id`
- `telegram_file_unique_id`
- `filename`
- `mime_type`
- `file_type`
- `size_bytes`
- `storage_path`
- `caption`
- `status`: `received`, `stored`, `processed`, `indexed`, `failed`
- `usage_event_id`
- `metadata_json`
- `created_at`
- `processed_at`

### Current-model migration map

Current `UserPreference` can be migrated like this:

- `UserPreference.id` -> `users.id` migration source only
- `telegram_user_id` -> `telegram_identities.telegram_user_id`
- `phone_number` -> `users.primary_phone_e164` after normalization
- `preferred_name`, `first_name`, `username` -> `user_profiles`
- `account_status` -> `users.status`
- `credit_balance_usd` -> initial wallet balance and opening ledger row

## 5. Telegram Conversation Flow

### `/start`

Flow:

1. Load or create Telegram identity shell from `telegram_user_id`.
2. If Telegram identity is linked to an active user, continue to main menu.
3. If linked user is missing phone, ask for contact share.
4. If linked user has phone but missing name, ask preferred name.
5. If not linked to user, ask for Telegram native contact share.

User message:

```text
سلام 👋
برای ساخت یا بازیابی حساب، لطفاً شماره تماست رو با دکمه زیر بفرست.
```

Keyboard:

- `📱 ارسال شماره تماس` with `request_contact=True`

### Contact share

Validation:

1. `message.contact` exists.
2. If `contact.user_id` exists, it must equal `effective_user.id`.
3. Normalize phone.

Existing account:

1. Find user by normalized phone.
2. If found and not deleted, bind Telegram identity to that user.
3. If preferred name exists, mark active and show restored account message.
4. If name missing, ask preferred name.

New account:

1. Create user with status `pending_name`.
2. Create wallet.
3. Create phone history.
4. Bind Telegram identity.
5. Ask preferred name.

User message:

```text
شماره ثبت شد. دوست داری چی صدات کنم؟
```

### Preferred name

Flow:

1. Reject empty name.
2. Trim excessive whitespace.
3. Store as profile preferred name.
4. Mark account `active`.
5. Show main menu.

User message:

```text
حسابت آماده است، {name}. حالا چطوری کمکت کنم؟
```

### Existing user restore

If the phone belongs to an existing active user:

```text
حسابت بازیابی شد، {name}. می‌تونی ادامه بدی.
```

If suspended:

```text
حسابت فعلاً غیرفعاله. برای بررسی با پشتیبانی تماس بگیر.
```

### Refusing phone

Allow only non-paid help/account explanation:

```text
برای استفاده از قابلیت‌های پولی باید حساب با شماره تماس ساخته بشه. هر وقت آماده بودی از دکمه ارسال شماره استفاده کن.
```

### Insufficient credit

Before paid operation:

```text
اعتبار کافی نیست.
اعتبار فعلی: {balance}
هزینه تخمینی: {estimated_cost}
برای ادامه حسابت رو شارژ کن.
```

Do not call the model/provider after this message.

### Account panel

Display:

- Preferred name.
- Phone, masked except last 4 digits.
- Status.
- Available credit.
- Last 5 ledger entries.
- Buttons: refresh, change name, update phone, charge account placeholder.

### Future onboarding placeholder

Store:

- `onboarding_version = "basic_v1"`
- `onboarding_completed_at`

Do not ask learning preference questions in this phase.

## 6. Credit Deduction Logic

### Money representation

Use integer minor units.

Recommended:

- Internal unit: micro-USD.
- Display: dollars with 4 to 6 decimals depending on product preference.

Avoid:

- `Float` for wallet balances.
- Direct balance assignment except one-time migration.

### Operation states

Usage event statuses:

- `estimated`
- `authorized`
- `completed`
- `failed`
- `billing_failed`
- `refunded`

Ledger entry statuses:

- `pending`
- `posted`
- `voided`

### Cost calculation

Chat completion:

```text
cost = (input_tokens / 1_000_000 * input_price_per_1m) + (output_tokens / 1_000_000 * output_price_per_1m)
```

Embedding:

```text
cost = embedding_tokens / 1_000_000 * embedding_price_per_1m
```

Per-file processing:

```text
cost = unit_price * file_count or size tier
```

Minimum charge:

```text
cost = max(calculated_cost, pricing.minimum_charge)
```

### Pre-checks

Before expensive operation:

1. Ensure account status is `active`.
2. Resolve pricing.
3. Estimate cost.
4. Check available balance.
5. Create usage event.
6. Create authorization hold when the cost is material.

### Post-usage reconciliation

After provider response:

1. Extract provider-reported usage.
2. Calculate actual cost from original pricing snapshot.
3. Capture actual cost.
4. Release unused hold amount.
5. If actual cost exceeds hold, attempt additional capture if balance allows; otherwise mark `billing_failed` and alert admin.

### Refunds

Refunds are new ledger entries:

- `entry_type='refund'`
- `usage_event_id` links to original usage
- `metadata_json.original_ledger_entry_id`
- Reason required

Never edit the original charge.

### Pseudocode: wallet charge

```python
async def charge_wallet(
    db,
    *,
    user_id: int,
    amount_minor: int,
    entry_type: str,
    reason: str,
    idempotency_key: str,
    usage_event_id: int | None = None,
    admin_action_id: int | None = None,
    metadata: dict | None = None,
):
    existing = await ledger_repo.get_by_idempotency_key(db, idempotency_key)
    if existing:
        return existing

    wallet = await wallet_repo.get_for_update(db, user_id)
    if amount_minor < 0:
        raise ValueError("amount_minor must be positive")

    if not wallet.allow_negative and wallet.available_minor < amount_minor:
        raise InsufficientCredit(wallet.available_minor, amount_minor)

    wallet.balance_minor -= amount_minor
    wallet.available_minor -= amount_minor
    wallet.version += 1

    entry = CreditLedger(
        wallet_id=wallet.id,
        user_id=user_id,
        direction="debit",
        amount_minor=amount_minor,
        balance_after_minor=wallet.balance_minor,
        available_after_minor=wallet.available_minor,
        held_after_minor=wallet.held_minor,
        entry_type=entry_type,
        status="posted",
        usage_event_id=usage_event_id,
        admin_action_id=admin_action_id,
        idempotency_key=idempotency_key,
        reason=reason,
        metadata_json=metadata or {},
    )
    db.add(entry)
    await db.commit()
    return entry
```

### Pseudocode: billable chat completion

```python
async def run_billable_chat(db, *, user, chat, model, provider, messages, telegram_update_id):
    account_service.require_active(user)

    pricing = await pricing_service.snapshot(
        db,
        provider_id=provider.id,
        model_id=model.id,
        operation_type="chat_completion",
    )
    estimated_tokens = token_estimator.estimate_messages(messages)
    estimated_cost = pricing.estimate_chat(
        input_tokens=estimated_tokens,
        output_tokens=900,
    )

    usage = await usage_metering.create(
        db,
        user_id=user.id,
        chat_id=chat.id,
        operation_type="chat_completion",
        provider_id=provider.id,
        model_id=model.id,
        pricing_snapshot=pricing.to_json(),
        estimated_cost_minor=estimated_cost,
        request_id=f"tg:{telegram_update_id}:chat",
    )

    hold = await wallet_service.authorize(
        db,
        user_id=user.id,
        amount_minor=estimated_cost,
        usage_event_id=usage.id,
        idempotency_key=f"usage:{usage.id}:hold",
    )

    try:
        response = await request_chat_completion(provider, model.name, messages)
        input_tokens, output_tokens = usage_metering.extract_chat_tokens(response.get("usage"))
        actual_cost = pricing.calculate_chat(input_tokens, output_tokens)

        await usage_metering.complete(
            db,
            usage.id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            actual_cost_minor=actual_cost,
            usage_source="provider_reported",
        )
        await wallet_service.capture_hold(
            db,
            hold_id=hold.id,
            final_amount_minor=actual_cost,
            idempotency_key=f"usage:{usage.id}:capture",
        )
        return response
    except Exception:
        await usage_metering.fail(db, usage.id)
        await wallet_service.release_hold(
            db,
            hold_id=hold.id,
            reason="provider_failed",
            idempotency_key=f"usage:{usage.id}:release",
        )
        raise
```

## 7. Admin Panel and Admin Commands

### Permissions

MVP:

- Existing bearer admin password.
- Existing hardcoded Telegram admin remains supported.

Scalable version:

- `admin_users`
- roles: `viewer`, `support`, `finance`, `owner`
- permissions: `user.read`, `user.write`, `wallet.adjust`, `wallet.refund`, `usage.read`, `admin.audit.read`

### Admin capabilities

User management:

- Search users by phone, Telegram ID, username, preferred name, status.
- View user detail.
- Edit preferred name, username metadata, status, phone with conflict checks.
- Suspend/reactivate/deactivate user.
- Soft delete user.

Wallet management:

- Add credit.
- Decrease credit.
- Correct balance via ledger adjustment.
- Refund usage event.
- View wallet summary.
- Rebuild cached balance from ledger.

Usage and audit:

- View usage events.
- View usage detail and pricing snapshot.
- View ledger entries.
- View admin action logs.
- View feedback entries.

### Admin API proposal

```text
GET    /admin/users
GET    /admin/users/{user_id}
PATCH  /admin/users/{user_id}
POST   /admin/users/{user_id}/suspend
POST   /admin/users/{user_id}/reactivate
POST   /admin/users/{user_id}/deactivate
POST   /admin/users/{user_id}/credit-adjustments
POST   /admin/users/{user_id}/refunds
GET    /admin/users/{user_id}/wallet
GET    /admin/users/{user_id}/ledger
GET    /admin/users/{user_id}/usage-events
GET    /admin/ledger
GET    /admin/usage-events
GET    /admin/admin-actions
GET    /admin/feedback
```

### Admin credit adjustment request

```json
{
  "amount_minor": 10000000,
  "direction": "credit",
  "reason": "manual top-up after payment confirmation",
  "idempotency_key": "admin-567136570-user-42-2026-04-22-topup-1"
}
```

### Pseudocode: admin adjustment

```python
async def admin_adjust_credit(db, *, admin_user_id, target_user_id, amount_minor, direction, reason):
    target_before = await admin_service.user_wallet_snapshot(db, target_user_id)
    action = await admin_audit.create(
        db,
        admin_user_id=admin_user_id,
        action_type="credit_adjustment",
        target_type="user",
        target_id=target_user_id,
        before_json=target_before,
        reason=reason,
    )

    if direction == "credit":
        entry = await wallet_service.credit(
            db,
            user_id=target_user_id,
            amount_minor=amount_minor,
            entry_type="admin_adjustment",
            reason=reason,
            admin_action_id=action.id,
        )
    else:
        entry = await wallet_service.debit(
            db,
            user_id=target_user_id,
            amount_minor=amount_minor,
            entry_type="admin_adjustment",
            reason=reason,
            admin_action_id=action.id,
        )

    target_after = await admin_service.user_wallet_snapshot(db, target_user_id)
    await admin_audit.complete(db, action.id, after_json=target_after)
    return entry
```

## 8. Feedback and Rating Logic

### Trigger rules

Ask for rating only if all conditions pass:

1. Assistant answer length is at least 220 characters.
2. User message is not smalltalk/greeting/thanks.
3. Assistant answer is not a short greeting, error, insufficient-credit message, or admin/system confirmation.
4. No rating prompt was sent to this user in the last 24 hours.
5. The user has fewer than 2 rating prompts today.
6. The assistant message has not already been rated.
7. Random sample passes, recommended 15-30%.

### Telegram UI

Use inline buttons:

- `👍`
- `👎`

Prompt:

```text
این پاسخ مفید بود؟
```

After vote:

```text
مرسی از بازخوردت.
```

### Pseudocode: feedback trigger

```python
def should_request_rating(user_text, assistant_text, recent_feedback, assistant_message):
    if len((assistant_text or "").strip()) < 220:
        return False
    if is_smalltalk(user_text) or is_smalltalk(assistant_text):
        return False
    if assistant_message.metadata.get("is_error"):
        return False
    if assistant_message.metadata.get("billing_status") == "insufficient_credit":
        return False
    if recent_feedback.prompted_within(hours=24):
        return False
    if recent_feedback.prompts_today >= 2:
        return False
    if recent_feedback.has_feedback_for_message(assistant_message.id):
        return False
    return random.random() < 0.25
```

### Storage

Every feedback row should include:

- `user_id`
- `telegram_user_id`
- `chat_id`
- `user_message_id`
- `assistant_message_id`
- `rating`
- `source`
- `sample_reason`
- `created_at`

## 9. UX and Prompt Behavior Fixes

### Image or file with caption

Correct behavior:

1. Download/process media.
2. Treat caption as the user instruction.
3. Build LLM payload with media/file context plus caption.
4. Answer directly.

Avoid:

- "You asked..."
- "I extracted this caption..."
- Echoing caption as a separate bot message.

### Image or file without caption

Correct behavior:

1. Download/process media.
2. Check recent chat context for intent.
3. If intent is clear, proceed directly.
4. If unclear, ask once:

```text
فایل رو گرفتم. می‌خوای خلاصه کنم، ترجمه کنم، متن استخراج کنم، یا تحلیلش کنم؟
```

For images:

```text
عکس رو گرفتم. می‌خوای توصیفش کنم، متنش رو استخراج کنم، یا تحلیلش کنم؟
```

### Intent inference examples

If previous user message says:

- "این فایل رو خلاصه کن" then uploaded file without caption should be summarized.
- "این عکس رو بررسی کن" then uploaded image without caption should be analyzed.
- "ترجمه کن" then file/image text extraction plus translation is likely intended.

### Assistant behavior rules

Add to default system prompt:

```text
Media behavior:
- When the user sends an image or file with a caption, treat the caption as the user's actual instruction. Answer directly using the media and the caption. Do not say that you extracted the caption and do not repeat "you asked".
- When the user sends an image or file without a caption, infer the likely intent from recent conversation if possible. If the intent is clear, proceed. If not clear, ask one concise clarification with likely options.
- Avoid repetitive file-received meta messages. Use progress/error messages only when needed.

Feedback behavior:
- Do not ask users to rate greetings, trivial answers, errors, or short confirmations.
- Feedback prompts should be occasional and lightweight.

Billing behavior:
- If the system indicates insufficient credit, stop the paid task and explain briefly.
- Do not expose internal billing formulas unless the user asks for billing details.
```

## 10. Edge Cases

### User changes Telegram number

Handling:

- Require new native contact share.
- Add previous phone to `phone_history`.
- If new phone belongs to another user, block and require admin review.

### User refuses phone

Handling:

- Keep status `pending_phone`.
- Allow `/start`, `/account`, and help text.
- Block paid chat, embedding, file/image analysis.

### Duplicate accounts

Handling:

- Unique normalized phone.
- If Telegram ID is bound to a different user than the phone account, create an `account_conflict` admin action/event and block automatic merge unless policy is explicit.

### Partially failed billing

Handling:

- If provider succeeds but ledger capture fails, mark usage `billing_failed`.
- Retry capture idempotently.
- Alert admin.
- Do not lose provider usage payload.

### Pricing changes over time

Handling:

- Close old pricing row with `effective_to`.
- Create new active row.
- Store pricing snapshot in usage event.
- Never recalculate old charges from current pricing.

### Race conditions

Handling:

- Lock wallet row during debit/credit.
- Use wallet `version` for optimistic concurrency.
- Use idempotency keys for repeated Telegram updates.

### Retry behavior

Handling:

- Same Telegram update and same operation uses same request/idempotency key.
- Provider retry should not double charge.
- Failed operation releases hold.

### Admin mistakes

Handling:

- Admin creates a reversing adjustment with reason.
- Old ledger row remains unchanged.
- Admin actions show both mistake and correction.

### Refund scenarios

Handling:

- Refund failed model response.
- Refund file indexing if indexing fails after hold/capture.
- Partial refund if actual usage was lower than captured estimate.
- Link refund to original usage event and ledger entry.

### Feedback spam

Handling:

- Cooldown per user.
- Max prompts per day.
- One feedback per assistant message.
- Do not prompt after the user already gave feedback recently.

### Existing users missing phone

Handling:

- Status becomes `pending_phone` unless admin.
- Preserve current chats.
- Ask for contact next time they interact.

### Admin users

Handling:

- Admin may bypass credit checks but usage should still be recorded as `admin_exempt`.
- Admin account should still have profile/identity data for audit actor mapping.

## 11. Implementation Plan

### Phase 1: Foundation

1. Add SQLAlchemy models for `users`, `user_profiles`, `telegram_identities`, `wallets`, `credit_ledger`, `usage_events`, `model_pricing`, `admin_actions`, `assistant_feedback`, and `uploaded_files`.
2. Add SQLite compatibility migration or a one-time migration script.
3. Backfill from `UserPreference`.
4. Add indexes and uniqueness constraints.

Verification:

- Import/startup check.
- Migration on a copy of existing SQLite DB.
- Rebuild wallet balances from ledger and compare with old balances.

### Phase 2: Services

1. Implement `account_service.py`.
2. Implement `wallet_service.py`.
3. Implement `pricing_service.py`.
4. Implement `usage_metering.py`.
5. Implement `admin_audit.py`.
6. Implement `feedback_service.py`.
7. Implement `media_service.py`.

Verification:

- Unit tests for account restore.
- Unit tests for wallet credit/debit/refund/idempotency.
- Unit tests for pricing snapshots.

### Phase 3: Telegram bot integration

1. Replace `get_user` account creation with `AccountService`.
2. Replace current phone/name handling with phone-first restore flow.
3. Gate all paid handlers through `require_active_account`.
4. Wrap chat completion in usage + wallet billing flow.
5. Wrap RAG indexing in usage + wallet billing flow.
6. Wrap image/file analysis in usage + wallet billing flow.
7. Add feedback sampling service.
8. Fix caption/no-caption behavior.

Verification:

- `/start` new user.
- Existing phone restore.
- Missing phone blocked.
- Insufficient credit blocks provider call.
- Successful chat creates usage + ledger.
- Caption image answers directly.
- No-caption image asks concise prompt once.

### Phase 4: Admin backend

1. Add user detail endpoint.
2. Add explicit credit adjustment endpoint.
3. Add user status endpoints.
4. Add ledger and usage listing endpoints.
5. Add admin audit listing.
6. Replace destructive delete with soft delete/deactivate.

Verification:

- Admin adjustment writes ledger and admin action.
- Suspension blocks paid chat.
- Soft delete keeps ledger visible.

### Phase 5: Admin frontend

1. Add user detail drawer/page.
2. Add credit adjustment form with required reason.
3. Add ledger tab.
4. Add usage events tab.
5. Add admin actions tab.
6. Add feedback tab linked to message/user context.

Verification:

- `npm run lint`.
- `npm run build` if admin structure changes.

### Phase 6: Rollout

1. Enable observe-only billing logs.
2. Compare expected deductions with current behavior.
3. Enable enforcement for non-admin users.
4. Monitor `billing_failed`, negative balance attempts, and duplicate idempotency keys.
5. Move production billing DB to Postgres before significant paid usage.

## 12. Suggested Code Structure

```text
backend/app/
  services/
    __init__.py
    account_service.py
    wallet_service.py
    pricing_service.py
    usage_metering.py
    feedback_service.py
    media_service.py
    admin_audit.py
  billing_types.py
  account_routes.py
  wallet_routes.py
  admin_routes.py
  bot.py
  models.py
  schemas.py
```

Recommended separation:

- `bot.py` handles Telegram update routing and user-facing messages.
- Services own business logic and database writes.
- `llm.py` remains provider/client logic.
- `main_routes.py` and Telegram should share billing/metering services.

## 13. Pseudocode Deliverables

### Signup/login

```python
async def start_flow(update, context):
    identity = await account_service.get_identity_by_telegram_id(update.effective_user.id)
    if identity and identity.user.status == "active":
        return show_main_menu(identity.user)

    if identity and identity.user.status == "pending_name":
        context.user_data["asking_name"] = True
        return ask_preferred_name()

    return ask_for_contact_share()


async def contact_flow(update, context):
    contact = update.message.contact
    if contact.user_id and contact.user_id != update.effective_user.id:
        return reject_contact()

    phone = normalize_phone(contact.phone_number)
    user, restored = await account_service.create_or_restore_by_phone(
        phone=phone,
        telegram_user=update.effective_user,
        telegram_chat_id=update.effective_chat.id,
    )

    if user.status == "suspended":
        return show_suspended()

    if not user.profile.preferred_name:
        context.user_data["asking_name"] = True
        return ask_preferred_name()

    await account_service.activate_if_ready(user.id)
    return show_restored_or_main_menu(restored, user)
```

### Balance deduction

```python
async def deduct_for_usage(db, *, usage_event_id, user_id, actual_cost_minor):
    usage = await usage_metering.get(db, usage_event_id)
    if usage.status == "completed":
        return usage

    entry = await wallet_service.charge(
        db,
        user_id=user_id,
        amount_minor=actual_cost_minor,
        entry_type=usage.operation_type,
        reason=f"usage:{usage.operation_type}",
        usage_event_id=usage.id,
        idempotency_key=f"usage:{usage.id}:charge",
        metadata={
            "provider": usage.provider_name_snapshot,
            "model": usage.model_name_snapshot,
            "tokens": {
                "input": usage.input_tokens,
                "output": usage.output_tokens,
            },
        },
    )
    await usage_metering.mark_completed(db, usage.id, ledger_entry_id=entry.id)
    return usage
```

### Feedback trigger

```python
async def maybe_send_feedback_prompt(update, user, user_message, assistant_message):
    decision = await feedback_service.should_prompt(
        user_id=user.id,
        user_text=user_message.content,
        assistant_text=assistant_message.content,
        assistant_message_id=assistant_message.id,
    )
    if not decision.should_prompt:
        return

    await feedback_service.record_prompt(
        user_id=user.id,
        assistant_message_id=assistant_message.id,
        sample_reason=decision.reason,
    )
    await update.message.reply_text(
        "این پاسخ مفید بود؟",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👍", callback_data=f"rate_{assistant_message.id}_up"),
            InlineKeyboardButton("👎", callback_data=f"rate_{assistant_message.id}_down"),
        ]]),
    )
```

### Media with caption

```python
async def handle_media_with_caption(update, media, caption):
    account = await account_service.require_active_for_update(update)
    stored = await media_service.store(update, media, caption=caption)

    instruction = caption.strip()
    llm_payload = await media_service.build_llm_payload(
        stored_file=stored,
        instruction=instruction,
        chat_context=await chat_service.recent_context(account.user_id),
    )

    response = await billable_ai_service.run(
        user_id=account.user_id,
        operation_type=stored.billable_operation_type,
        payload=llm_payload,
    )
    return send_response(response)
```

### Media without caption

```python
async def handle_media_without_caption(update, media):
    account = await account_service.require_active_for_update(update)
    stored = await media_service.store(update, media)

    inferred = await media_service.infer_intent_from_recent_context(account.user_id, stored)
    if inferred:
        return await process_media_instruction(update, stored, inferred)

    context.user_data["pending_media"] = {
        "uploaded_file_id": stored.id,
        "asked_clarification": True,
    }
    return ask_one_media_clarification(stored)
```

## 14. Final Recommended Architecture

Recommended architecture:

- Account identity is rooted in `users.primary_phone_e164`.
- Telegram identity is a linked login method.
- Wallet is ledger-first with cached balances.
- Usage metering records every paid operation.
- Pricing is versioned and snapshotted into usage events.
- Admin actions are audited.
- Feedback is sampled and linked to messages.
- Media behavior is centralized in a service rather than repeated in handlers.

## 15. Minimal Viable Version

MVP should include:

1. Phone-first Telegram signup/restore.
2. Preferred name capture.
3. Wallet table and ledger table with integer money.
4. Admin credit adjustment endpoint with audit logs.
5. Usage events for chat completions and RAG embeddings.
6. Insufficient credit pre-check.
7. Feedback cooldown and message-linked ratings.
8. Caption/no-caption media UX fixes.
9. Soft user suspension/deactivation.

MVP can defer:

1. Payment gateway.
2. Full RBAC.
3. Multi-currency settlement.
4. Background reconciliation dashboard.
5. Telegram reactions support.

## 16. Safer Scalable Version

Scalable version should add:

1. Postgres with row-level wallet locks.
2. Alembic migrations.
3. Idempotency table for all external update handling.
4. Payment provider integration.
5. Admin RBAC and multi-admin audit identity.
6. Reconciliation jobs.
7. Billing exports.
8. Alerting for `billing_failed`, negative balance attempts, and duplicate account conflicts.
9. Provider-specific metering adapters.
10. Wallet statement exports for users.

## 17. Critical Engineering Risks

1. Using floats for billing.
2. Mutating balance directly from admin routes.
3. Charging without immutable usage and pricing snapshots.
4. Double-charging retries.
5. Race conditions in concurrent Telegram updates.
6. Deleting users or ledger rows.
7. Allowing phone account takeover through non-native contact input.
8. Pricing edits changing historical usage interpretation.
9. Billing failures after provider success.
10. Media processing costs bypassing wallet checks.

## 18. Open Questions That Can Be Postponed

1. Which payment provider will top up credit?
2. Is user-facing credit exactly USD, local currency, or product credits?
3. Should old users get starter credit?
4. Should web chat also require phone verification before paid usage?
5. Who can approve phone/account merge conflicts?
6. What is the refund policy for low-quality AI answers?
7. Should admin actions require two-step confirmation above a credit threshold?
8. Should user-visible invoices be generated?
9. What are exact image/file processing prices?
10. When should advanced onboarding/personalization begin?
