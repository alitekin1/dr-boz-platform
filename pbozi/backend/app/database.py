from sqlalchemy import text, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import DATABASE_URL
from app.models import Base

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"timeout": 30} if DATABASE_URL.startswith("sqlite") else {}
)

if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _sqlite_table_columns(conn, table_name: str) -> set[str]:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


async def _apply_sqlite_compat_migrations(conn):
    existing_tables = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    table_names = {row[0] for row in existing_tables.fetchall()}
    if "documents" in table_names:
        columns = await _sqlite_table_columns(conn, "documents")
        additions = {
            "status": "ALTER TABLE documents ADD COLUMN status VARCHAR DEFAULT 'pending'",
            "error": "ALTER TABLE documents ADD COLUMN error TEXT",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "user_preferences" in table_names:
        columns = await _sqlite_table_columns(conn, "user_preferences")
        additions = {
            "phone_number": "ALTER TABLE user_preferences ADD COLUMN phone_number VARCHAR",
            "account_status": "ALTER TABLE user_preferences ADD COLUMN account_status VARCHAR DEFAULT 'active'",
            "credit_balance_usd": "ALTER TABLE user_preferences ADD COLUMN credit_balance_usd FLOAT DEFAULT 0.0",
            "learning_preferences_status": "ALTER TABLE user_preferences ADD COLUMN learning_preferences_status VARCHAR DEFAULT 'not_started'",
            "learning_preferences_summary": "ALTER TABLE user_preferences ADD COLUMN learning_preferences_summary TEXT",
            "learning_preferences_prompt": "ALTER TABLE user_preferences ADD COLUMN learning_preferences_prompt TEXT",
            "learning_preferences_profile_json": "ALTER TABLE user_preferences ADD COLUMN learning_preferences_profile_json JSON",
            "learning_preferences_onboarding_json": "ALTER TABLE user_preferences ADD COLUMN learning_preferences_onboarding_json JSON",
            "learning_preferences_completed_at": "ALTER TABLE user_preferences ADD COLUMN learning_preferences_completed_at DATETIME",
            "custom_personalization": "ALTER TABLE user_preferences ADD COLUMN custom_personalization TEXT",
            "pending_action_payload": "ALTER TABLE user_preferences ADD COLUMN pending_action_payload JSON",
            "is_pro": "ALTER TABLE user_preferences ADD COLUMN is_pro BOOLEAN DEFAULT 0",
            "total_charged_usd": "ALTER TABLE user_preferences ADD COLUMN total_charged_usd FLOAT DEFAULT 0.0",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "chats" in table_names:
        columns = await _sqlite_table_columns(conn, "chats")
        additions = {
            "user_preference_id": "ALTER TABLE chats ADD COLUMN user_preference_id INTEGER",
            "codex_thread_id": "ALTER TABLE chats ADD COLUMN codex_thread_id VARCHAR",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
        if "codex_thread_id" in additions and "codex_thread_id" in columns:
             # Just ensure index exists if it doesn't
             await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chats_codex_thread_id ON chats (codex_thread_id)"))
    if "projects" in table_names:
        columns = await _sqlite_table_columns(conn, "projects")
        additions = {
            "instructions": "ALTER TABLE projects ADD COLUMN instructions TEXT",
            "owner_user_id": "ALTER TABLE projects ADD COLUMN owner_user_id INTEGER",
            "share_token": "ALTER TABLE projects ADD COLUMN share_token VARCHAR",
            "shared_from_project_id": "ALTER TABLE projects ADD COLUMN shared_from_project_id INTEGER",
            "project_group_shares": """
                CREATE TABLE IF NOT EXISTS project_group_shares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    shared_by_user_id INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(project_id) REFERENCES projects(id),
                    FOREIGN KEY(group_id) REFERENCES telegram_groups(id),
                    FOREIGN KEY(shared_by_user_id) REFERENCES user_preferences(id),
                    UNIQUE(project_id, group_id)
                )
            """,
            "project_group_shares_ix_project": "CREATE INDEX IF NOT EXISTS ix_project_group_shares_project_id ON project_group_shares (project_id)",
            "project_group_shares_ix_group": "CREATE INDEX IF NOT EXISTS ix_project_group_shares_group_id ON project_group_shares (group_id)",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_projects_share_token ON projects (share_token)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_owner_user_id ON projects (owner_user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_projects_shared_from_project_id ON projects (shared_from_project_id)"))
    if "tools" in table_names:
        columns = await _sqlite_table_columns(conn, "tools")
        additions = {
            "kind": "ALTER TABLE tools ADD COLUMN kind VARCHAR DEFAULT 'builtin'",
            "implementation_key": "ALTER TABLE tools ADD COLUMN implementation_key VARCHAR",
            "implementation_config": "ALTER TABLE tools ADD COLUMN implementation_config JSON",
            "input_schema": "ALTER TABLE tools ADD COLUMN input_schema JSON",
            "is_builtin": "ALTER TABLE tools ADD COLUMN is_builtin BOOLEAN DEFAULT 0",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "trial_configs" in table_names:
        columns = await _sqlite_table_columns(conn, "trial_configs")
        additions = {
            "invitation_message": "ALTER TABLE trial_configs ADD COLUMN invitation_message TEXT",
            "invitation_button_text": "ALTER TABLE trial_configs ADD COLUMN invitation_button_text VARCHAR DEFAULT 'فعال‌سازی اشتراک رایگان'",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "models" in table_names:
        columns = await _sqlite_table_columns(conn, "models")
        additions = {
            "is_default": "ALTER TABLE models ADD COLUMN is_default BOOLEAN DEFAULT 0",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "providers" in table_names:
        columns = await _sqlite_table_columns(conn, "providers")
        additions = {
            "kind": "ALTER TABLE providers ADD COLUMN kind VARCHAR DEFAULT 'openai_compatible'",
            "config_json": "ALTER TABLE providers ADD COLUMN config_json JSON",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "capacity_pools" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS capacity_pools (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR,
                    max_users INTEGER DEFAULT 50,
                    active_users INTEGER DEFAULT 0,
                    status VARCHAR DEFAULT 'active',
                    fallback_behavior VARCHAR DEFAULT 'reject',
                    fallback_model_id INTEGER,
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY(fallback_model_id) REFERENCES models (id)
                )
                """
            )
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_capacity_pools_name ON capacity_pools (name)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_capacity_pools_status ON capacity_pools (status)"))
    if "codex_accounts" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS codex_accounts (
                    id INTEGER NOT NULL PRIMARY KEY,
                    label VARCHAR,
                    provider_id INTEGER,
                    pool_id INTEGER,
                    codex_home VARCHAR NOT NULL UNIQUE,
                    auth_status VARCHAR DEFAULT 'pending',
                    is_active BOOLEAN DEFAULT 1,
                    status VARCHAR DEFAULT 'active',
                    max_users INTEGER DEFAULT 50,
                    five_hour_limit INTEGER DEFAULT 0,
                    five_hour_used INTEGER DEFAULT 0,
                    weekly_limit INTEGER DEFAULT 0,
                    weekly_used INTEGER DEFAULT 0,
                    safety_buffer_percent FLOAT DEFAULT 30.0,
                    last_error TEXT,
                    cooldown_until DATETIME,
                    last_used_at DATETIME,
                    metadata_json JSON,
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY(provider_id) REFERENCES providers (id),
                    FOREIGN KEY(pool_id) REFERENCES capacity_pools (id)
                )
                """
            )
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_label ON codex_accounts (label)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_provider_id ON codex_accounts (provider_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_pool_id ON codex_accounts (pool_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_auth_status ON codex_accounts (auth_status)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_status ON codex_accounts (status)"))
    else:
        columns = await _sqlite_table_columns(conn, "codex_accounts")
        additions = {
            "provider_id": "ALTER TABLE codex_accounts ADD COLUMN provider_id INTEGER",
            "pool_id": "ALTER TABLE codex_accounts ADD COLUMN pool_id INTEGER",
            "auth_status": "ALTER TABLE codex_accounts ADD COLUMN auth_status VARCHAR DEFAULT 'pending'",
            "is_active": "ALTER TABLE codex_accounts ADD COLUMN is_active BOOLEAN DEFAULT 1",
            "status": "ALTER TABLE codex_accounts ADD COLUMN status VARCHAR DEFAULT 'active'",
            "max_users": "ALTER TABLE codex_accounts ADD COLUMN max_users INTEGER DEFAULT 50",
            "five_hour_limit": "ALTER TABLE codex_accounts ADD COLUMN five_hour_limit INTEGER DEFAULT 0",
            "five_hour_used": "ALTER TABLE codex_accounts ADD COLUMN five_hour_used INTEGER DEFAULT 0",
            "weekly_limit": "ALTER TABLE codex_accounts ADD COLUMN weekly_limit INTEGER DEFAULT 0",
            "weekly_used": "ALTER TABLE codex_accounts ADD COLUMN weekly_used INTEGER DEFAULT 0",
            "safety_buffer_percent": "ALTER TABLE codex_accounts ADD COLUMN safety_buffer_percent FLOAT DEFAULT 30.0",
            "last_error": "ALTER TABLE codex_accounts ADD COLUMN last_error TEXT",
            "cooldown_until": "ALTER TABLE codex_accounts ADD COLUMN cooldown_until DATETIME",
            "last_used_at": "ALTER TABLE codex_accounts ADD COLUMN last_used_at DATETIME",
            "metadata_json": "ALTER TABLE codex_accounts ADD COLUMN metadata_json JSON",
            "updated_at": "ALTER TABLE codex_accounts ADD COLUMN updated_at DATETIME",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_label ON codex_accounts (label)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_provider_id ON codex_accounts (provider_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_pool_id ON codex_accounts (pool_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_auth_status ON codex_accounts (auth_status)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_codex_accounts_status ON codex_accounts (status)"))
    if "credit_ledger_entries" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS credit_ledger_entries (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    amount_delta_usd FLOAT NOT NULL,
                    entry_type VARCHAR NOT NULL,
                    reason VARCHAR,
                    metadata_json JSON,
                    created_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES user_preferences (id)
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "credit_ledger_entries")
        additions = {
            "wallet_id": "ALTER TABLE credit_ledger_entries ADD COLUMN wallet_id INTEGER",
            "amount_minor": "ALTER TABLE credit_ledger_entries ADD COLUMN amount_minor INTEGER",
            "balance_after_minor": "ALTER TABLE credit_ledger_entries ADD COLUMN balance_after_minor INTEGER",
            "available_after_minor": "ALTER TABLE credit_ledger_entries ADD COLUMN available_after_minor INTEGER",
            "held_after_minor": "ALTER TABLE credit_ledger_entries ADD COLUMN held_after_minor INTEGER",
            "currency": "ALTER TABLE credit_ledger_entries ADD COLUMN currency VARCHAR DEFAULT 'USD'",
            "direction": "ALTER TABLE credit_ledger_entries ADD COLUMN direction VARCHAR",
            "status": "ALTER TABLE credit_ledger_entries ADD COLUMN status VARCHAR DEFAULT 'posted'",
            "usage_event_id": "ALTER TABLE credit_ledger_entries ADD COLUMN usage_event_id INTEGER",
            "admin_action_id": "ALTER TABLE credit_ledger_entries ADD COLUMN admin_action_id INTEGER",
            "idempotency_key": "ALTER TABLE credit_ledger_entries ADD COLUMN idempotency_key VARCHAR",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "feedback_entries" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS feedback_entries (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER,
                    telegram_user_id INTEGER,
                    chat_id INTEGER,
                    message_id INTEGER,
                    rating_value INTEGER NOT NULL,
                    note TEXT,
                    reaction_raw_text TEXT,
                    created_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES user_preferences (id)
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "feedback_entries")
        additions = {
            "user_message_id": "ALTER TABLE feedback_entries ADD COLUMN user_message_id INTEGER",
            "assistant_message_id": "ALTER TABLE feedback_entries ADD COLUMN assistant_message_id INTEGER",
            "source": "ALTER TABLE feedback_entries ADD COLUMN source VARCHAR DEFAULT 'telegram_inline_button'",
            "sample_reason": "ALTER TABLE feedback_entries ADD COLUMN sample_reason VARCHAR",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "system_prompts" in table_names:
        columns = await _sqlite_table_columns(conn, "system_prompts")
        additions = {
            "auto_tool_guidance_enabled": "ALTER TABLE system_prompts ADD COLUMN auto_tool_guidance_enabled BOOLEAN DEFAULT 1",
            "tool_guidance_style": "ALTER TABLE system_prompts ADD COLUMN tool_guidance_style VARCHAR DEFAULT 'compact'",
            "tool_guidance_template": "ALTER TABLE system_prompts ADD COLUMN tool_guidance_template TEXT",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "embedding_config" in table_names:
        columns = await _sqlite_table_columns(conn, "embedding_config")
        additions = {
            "pricing_input": "ALTER TABLE embedding_config ADD COLUMN pricing_input FLOAT DEFAULT 0.0",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "transcription_configs" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS transcription_configs (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR UNIQUE,
                    provider VARCHAR DEFAULT 'google',
                    model VARCHAR DEFAULT 'gemini-3.1-flash-lite-preview',
                    api_key VARCHAR,
                    base_url VARCHAR DEFAULT 'https://generativelanguage.googleapis.com/v1beta',
                    pricing_input FLOAT DEFAULT 0.5,
                    pricing_output FLOAT DEFAULT 1.5,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "transcription_configs")
        additions = {
            "base_url": "ALTER TABLE transcription_configs ADD COLUMN base_url VARCHAR DEFAULT 'https://generativelanguage.googleapis.com/v1beta'",
            "pricing_input": "ALTER TABLE transcription_configs ADD COLUMN pricing_input FLOAT DEFAULT 0.5",
            "pricing_output": "ALTER TABLE transcription_configs ADD COLUMN pricing_output FLOAT DEFAULT 1.5",
            "is_active": "ALTER TABLE transcription_configs ADD COLUMN is_active BOOLEAN DEFAULT 1",
            "updated_at": "ALTER TABLE transcription_configs ADD COLUMN updated_at DATETIME",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    if "telegram_groups" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS telegram_groups (
                    id INTEGER NOT NULL PRIMARY KEY,
                    telegram_chat_id INTEGER NOT NULL UNIQUE,
                    title VARCHAR,
                    chat_type VARCHAR NOT NULL DEFAULT 'group',
                    status VARCHAR DEFAULT 'active',
                    trigger_phrases_json JSON,
                    min_active_members INTEGER DEFAULT 2,
                    app_chat_id INTEGER,
                    created_by_user_id INTEGER,
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY(created_by_user_id) REFERENCES user_preferences (id)
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "telegram_groups")
        additions = {
            "title": "ALTER TABLE telegram_groups ADD COLUMN title VARCHAR",
            "chat_type": "ALTER TABLE telegram_groups ADD COLUMN chat_type VARCHAR NOT NULL DEFAULT 'group'",
            "status": "ALTER TABLE telegram_groups ADD COLUMN status VARCHAR DEFAULT 'active'",
            "trigger_phrases_json": "ALTER TABLE telegram_groups ADD COLUMN trigger_phrases_json JSON",
            "min_active_members": "ALTER TABLE telegram_groups ADD COLUMN min_active_members INTEGER DEFAULT 2",
            "app_chat_id": "ALTER TABLE telegram_groups ADD COLUMN app_chat_id INTEGER",
            "created_by_user_id": "ALTER TABLE telegram_groups ADD COLUMN created_by_user_id INTEGER",
            "updated_at": "ALTER TABLE telegram_groups ADD COLUMN updated_at DATETIME",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_groups_chat_id ON telegram_groups (telegram_chat_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_telegram_groups_status ON telegram_groups (status)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_telegram_groups_status_type ON telegram_groups (status, chat_type)"))

    if "telegram_group_members" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS telegram_group_members (
                    id INTEGER NOT NULL PRIMARY KEY,
                    group_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    telegram_user_id INTEGER,
                    status VARCHAR DEFAULT 'active',
                    shared_billing_enabled BOOLEAN DEFAULT 0,
                    last_opt_in_at DATETIME,
                    last_opt_out_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY(group_id) REFERENCES telegram_groups (id),
                    FOREIGN KEY(user_id) REFERENCES user_preferences (id)
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "telegram_group_members")
        additions = {
            "telegram_user_id": "ALTER TABLE telegram_group_members ADD COLUMN telegram_user_id INTEGER",
            "status": "ALTER TABLE telegram_group_members ADD COLUMN status VARCHAR DEFAULT 'active'",
            "shared_billing_enabled": "ALTER TABLE telegram_group_members ADD COLUMN shared_billing_enabled BOOLEAN DEFAULT 0",
            "last_opt_in_at": "ALTER TABLE telegram_group_members ADD COLUMN last_opt_in_at DATETIME",
            "last_opt_out_at": "ALTER TABLE telegram_group_members ADD COLUMN last_opt_out_at DATETIME",
            "updated_at": "ALTER TABLE telegram_group_members ADD COLUMN updated_at DATETIME",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_group_members_group_user ON telegram_group_members (group_id, user_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tgm_group_enabled_status ON telegram_group_members (group_id, shared_billing_enabled, status)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_telegram_group_members_status ON telegram_group_members (status)"))

    if "group_usage_events" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS group_usage_events (
                    id INTEGER NOT NULL PRIMARY KEY,
                    group_id INTEGER NOT NULL,
                    usage_event_id INTEGER,
                    triggered_by_user_id INTEGER,
                    request_id VARCHAR UNIQUE,
                    telegram_chat_id INTEGER,
                    telegram_message_id INTEGER,
                    operation_type VARCHAR DEFAULT 'chat_completion',
                    estimated_cost_minor INTEGER DEFAULT 0,
                    actual_cost_minor INTEGER DEFAULT 0,
                    split_member_count INTEGER DEFAULT 0,
                    status VARCHAR DEFAULT 'pending',
                    error TEXT,
                    metadata_json JSON,
                    created_at DATETIME,
                    completed_at DATETIME,
                    FOREIGN KEY(group_id) REFERENCES telegram_groups (id),
                    FOREIGN KEY(usage_event_id) REFERENCES usage_events (id),
                    FOREIGN KEY(triggered_by_user_id) REFERENCES user_preferences (id)
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "group_usage_events")
        additions = {
            "usage_event_id": "ALTER TABLE group_usage_events ADD COLUMN usage_event_id INTEGER",
            "triggered_by_user_id": "ALTER TABLE group_usage_events ADD COLUMN triggered_by_user_id INTEGER",
            "request_id": "ALTER TABLE group_usage_events ADD COLUMN request_id VARCHAR",
            "telegram_chat_id": "ALTER TABLE group_usage_events ADD COLUMN telegram_chat_id INTEGER",
            "telegram_message_id": "ALTER TABLE group_usage_events ADD COLUMN telegram_message_id INTEGER",
            "operation_type": "ALTER TABLE group_usage_events ADD COLUMN operation_type VARCHAR DEFAULT 'chat_completion'",
            "estimated_cost_minor": "ALTER TABLE group_usage_events ADD COLUMN estimated_cost_minor INTEGER DEFAULT 0",
            "actual_cost_minor": "ALTER TABLE group_usage_events ADD COLUMN actual_cost_minor INTEGER DEFAULT 0",
            "split_member_count": "ALTER TABLE group_usage_events ADD COLUMN split_member_count INTEGER DEFAULT 0",
            "status": "ALTER TABLE group_usage_events ADD COLUMN status VARCHAR DEFAULT 'pending'",
            "error": "ALTER TABLE group_usage_events ADD COLUMN error TEXT",
            "metadata_json": "ALTER TABLE group_usage_events ADD COLUMN metadata_json JSON",
            "completed_at": "ALTER TABLE group_usage_events ADD COLUMN completed_at DATETIME",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_group_usage_events_request_id ON group_usage_events (request_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_gue_group_status_created ON group_usage_events (group_id, status, created_at)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_group_usage_events_chat_message ON group_usage_events (telegram_chat_id, telegram_message_id)"))

    if "group_usage_shares" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS group_usage_shares (
                    id INTEGER NOT NULL PRIMARY KEY,
                    group_usage_event_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    ledger_entry_id INTEGER,
                    estimated_share_minor INTEGER DEFAULT 0,
                    actual_share_minor INTEGER DEFAULT 0,
                    status VARCHAR DEFAULT 'pending',
                    error TEXT,
                    metadata_json JSON,
                    created_at DATETIME,
                    completed_at DATETIME,
                    FOREIGN KEY(group_usage_event_id) REFERENCES group_usage_events (id),
                    FOREIGN KEY(group_id) REFERENCES telegram_groups (id),
                    FOREIGN KEY(user_id) REFERENCES user_preferences (id),
                    FOREIGN KEY(ledger_entry_id) REFERENCES credit_ledger_entries (id)
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "group_usage_shares")
        additions = {
            "group_id": "ALTER TABLE group_usage_shares ADD COLUMN group_id INTEGER",
            "ledger_entry_id": "ALTER TABLE group_usage_shares ADD COLUMN ledger_entry_id INTEGER",
            "estimated_share_minor": "ALTER TABLE group_usage_shares ADD COLUMN estimated_share_minor INTEGER DEFAULT 0",
            "actual_share_minor": "ALTER TABLE group_usage_shares ADD COLUMN actual_share_minor INTEGER DEFAULT 0",
            "status": "ALTER TABLE group_usage_shares ADD COLUMN status VARCHAR DEFAULT 'pending'",
            "error": "ALTER TABLE group_usage_shares ADD COLUMN error TEXT",
            "metadata_json": "ALTER TABLE group_usage_shares ADD COLUMN metadata_json JSON",
            "completed_at": "ALTER TABLE group_usage_shares ADD COLUMN completed_at DATETIME",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_group_usage_shares_event_user ON group_usage_shares (group_usage_event_id, user_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_gus_group_user_created ON group_usage_shares (group_id, user_id, created_at)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_group_usage_shares_status ON group_usage_shares (status)"))

    if "telegram_update_logs" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS telegram_update_logs (
                    id INTEGER NOT NULL PRIMARY KEY,
                    update_id INTEGER NOT NULL UNIQUE,
                    update_key VARCHAR UNIQUE,
                    telegram_user_id INTEGER,
                    chat_id INTEGER,
                    update_type VARCHAR,
                    status VARCHAR DEFAULT 'processing',
                    metadata_json JSON,
                    created_at DATETIME,
                    completed_at DATETIME
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "telegram_update_logs")
        additions = {
            "update_key": "ALTER TABLE telegram_update_logs ADD COLUMN update_key VARCHAR",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))

    if "starter_credit_configs" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS starter_credit_configs (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR UNIQUE,
                    amount_usd FLOAT DEFAULT 0.0,
                    welcome_message TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
    else:
        columns = await _sqlite_table_columns(conn, "starter_credit_configs")
        additions = {
            "amount_usd": "ALTER TABLE starter_credit_configs ADD COLUMN amount_usd FLOAT DEFAULT 0.0",
            "amount_toman": "ALTER TABLE starter_credit_configs ADD COLUMN amount_toman INTEGER DEFAULT 0",
            "welcome_message": "ALTER TABLE starter_credit_configs ADD COLUMN welcome_message TEXT",
            "is_active": "ALTER TABLE starter_credit_configs ADD COLUMN is_active BOOLEAN DEFAULT 1",
            "updated_at": "ALTER TABLE starter_credit_configs ADD COLUMN updated_at DATETIME",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))

    if "subscription_plans" in table_names:
        columns = await _sqlite_table_columns(conn, "subscription_plans")
        additions = {
            "monthly_price_toman": "ALTER TABLE subscription_plans ADD COLUMN monthly_price_toman INTEGER DEFAULT 0",
            "gift_credit_toman": "ALTER TABLE subscription_plans ADD COLUMN gift_credit_toman INTEGER DEFAULT 0",
            "allowed_tools_json": "ALTER TABLE subscription_plans ADD COLUMN allowed_tools_json JSON",
            "allowed_skills_json": "ALTER TABLE subscription_plans ADD COLUMN allowed_skills_json JSON",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))

    if "user_subscriptions" in table_names:
        columns = await _sqlite_table_columns(conn, "user_subscriptions")
        additions = {
            "pool_id": "ALTER TABLE user_subscriptions ADD COLUMN pool_id INTEGER",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_subscriptions_pool_id ON user_subscriptions (pool_id)"))

    if "subscription_configs" in table_names:
        columns = await _sqlite_table_columns(conn, "subscription_configs")
        additions = {
            "monthly_price_toman": "ALTER TABLE subscription_configs ADD COLUMN monthly_price_toman INTEGER DEFAULT 80000",
            "gift_credit_toman": "ALTER TABLE subscription_configs ADD COLUMN gift_credit_toman INTEGER DEFAULT 100000",
            "api_markup_percent": "ALTER TABLE subscription_configs ADD COLUMN api_markup_percent FLOAT DEFAULT 25.0",
            "first_topup_discount_percent": "ALTER TABLE subscription_configs ADD COLUMN first_topup_discount_percent FLOAT DEFAULT 50.0",
            "first_topup_discount_cap_toman": "ALTER TABLE subscription_configs ADD COLUMN first_topup_discount_cap_toman INTEGER DEFAULT 300000",
            "usd_to_toman_rate": "ALTER TABLE subscription_configs ADD COLUMN usd_to_toman_rate INTEGER DEFAULT 50000",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))

    if "promo_codes" in table_names:
        columns = await _sqlite_table_columns(conn, "promo_codes")
        additions = {
            "currency": "ALTER TABLE promo_codes ADD COLUMN currency VARCHAR DEFAULT 'USD'",
            "bonus_value_toman": "ALTER TABLE promo_codes ADD COLUMN bonus_value_toman INTEGER DEFAULT 0",
            "minimum_charge_toman": "ALTER TABLE promo_codes ADD COLUMN minimum_charge_toman INTEGER DEFAULT 0",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))

    if "promo_code_redemptions" in table_names:
        columns = await _sqlite_table_columns(conn, "promo_code_redemptions")
        additions = {
            "charge_amount_toman": "ALTER TABLE promo_code_redemptions ADD COLUMN charge_amount_toman INTEGER DEFAULT 0",
            "bonus_amount_toman": "ALTER TABLE promo_code_redemptions ADD COLUMN bonus_amount_toman INTEGER DEFAULT 0",
            "total_credit_toman": "ALTER TABLE promo_code_redemptions ADD COLUMN total_credit_toman INTEGER DEFAULT 0",
            "toman_ledger_entry_id": "ALTER TABLE promo_code_redemptions ADD COLUMN toman_ledger_entry_id INTEGER",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))

    if "referral_campaigns" in table_names:
        columns = await _sqlite_table_columns(conn, "referral_campaigns")
        additions = {
            "created_by_user_id": "ALTER TABLE referral_campaigns ADD COLUMN created_by_user_id INTEGER",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))

    if "referral_configs" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS referral_configs (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR UNIQUE DEFAULT 'default',
                    reward_toman INTEGER DEFAULT 50000,
                    reward_message TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        await conn.execute(
            text("INSERT OR IGNORE INTO referral_configs (name, reward_toman, is_active, created_at) VALUES ('default', 50000, 1, datetime('now'))")
        )

    if "user_billing_accounts" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_billing_accounts (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    currency VARCHAR DEFAULT 'TOMAN',
                    gift_balance_toman INTEGER DEFAULT 0,
                    paid_balance_toman INTEGER DEFAULT 0,
                    total_gift_granted_toman INTEGER DEFAULT 0,
                    total_gift_spent_toman INTEGER DEFAULT 0,
                    total_paid_topup_toman INTEGER DEFAULT 0,
                    total_paid_spent_toman INTEGER DEFAULT 0,
                    total_subscription_paid_toman INTEGER DEFAULT 0,
                    first_topup_discount_used BOOLEAN DEFAULT 0,
                    version INTEGER DEFAULT 0,
                    created_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES user_preferences (id)
                )
                """
            )
        )
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_billing_accounts_user_id ON user_billing_accounts (user_id)"))

    if "toman_ledger_entries" not in table_names:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS toman_ledger_entries (
                    id INTEGER NOT NULL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    billing_account_id INTEGER,
                    amount_toman INTEGER NOT NULL,
                    gift_delta_toman INTEGER DEFAULT 0,
                    paid_delta_toman INTEGER DEFAULT 0,
                    gift_balance_after_toman INTEGER DEFAULT 0,
                    paid_balance_after_toman INTEGER DEFAULT 0,
                    entry_type VARCHAR NOT NULL,
                    status VARCHAR DEFAULT 'posted',
                    reason VARCHAR,
                    usage_event_id INTEGER,
                    idempotency_key VARCHAR UNIQUE,
                    metadata_json JSON,
                    created_at DATETIME,
                    FOREIGN KEY(user_id) REFERENCES user_preferences (id),
                    FOREIGN KEY(billing_account_id) REFERENCES user_billing_accounts (id),
                    FOREIGN KEY(usage_event_id) REFERENCES usage_events (id)
                )
                """
            )
        )
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_toman_ledger_entries_user_id ON toman_ledger_entries (user_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_toman_ledger_entries_billing_account_id ON toman_ledger_entries (billing_account_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_toman_ledger_entries_usage_event_id ON toman_ledger_entries (usage_event_id)"))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_toman_ledger_entries_idempotency_key ON toman_ledger_entries (idempotency_key)"))

    if "payment_requests" in table_names:
        columns = await _sqlite_table_columns(conn, "payment_requests")
        additions = {
            "payment_type": "ALTER TABLE payment_requests ADD COLUMN payment_type VARCHAR DEFAULT 'topup'",
            "plan_id": "ALTER TABLE payment_requests ADD COLUMN plan_id INTEGER",
        }
        for column_name, statement in additions.items():
            if column_name not in columns:
                await conn.execute(text(statement))


async def _seed_codex_prompt(session: AsyncSession) -> None:
    from app.models import SystemPrompt
    from app.llm import DEFAULT_CODEX_SYSTEM_PROMPT_TEXT

    existing = (await session.execute(select(SystemPrompt).where(SystemPrompt.name == "codex"))).scalar_one_or_none()
    if existing is None:
        session.add(
            SystemPrompt(
                name="codex",
                content=DEFAULT_CODEX_SYSTEM_PROMPT_TEXT,
                is_active=True,
                auto_tool_guidance_enabled=True,
                tool_guidance_style="compact",
            )
        )
        await session.commit()


async def _migrate_usd_balances_to_toman(session: AsyncSession) -> None:
    from app.models import SubscriptionConfig, UserBillingAccount, UserPreference, Wallet
    from app.services.toman_billing_service import DEFAULT_USD_TO_TOMAN_RATE, get_or_create_billing_account
    from decimal import Decimal, ROUND_HALF_UP

    config = (await session.execute(select(SubscriptionConfig))).scalars().first()
    rate = int(config.usd_to_toman_rate) if config else DEFAULT_USD_TO_TOMAN_RATE

    users_with_balance = (
        await session.execute(select(UserPreference).where(UserPreference.credit_balance_usd > 0))
    ).scalars().all()

    for user in users_with_balance:
        usd_amount = float(user.credit_balance_usd or 0.0)
        if usd_amount <= 0:
            continue
        toman_amount = int(Decimal(str(usd_amount * rate)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if toman_amount <= 0:
            continue
        account = await get_or_create_billing_account(session, user)
        account.paid_balance_toman = int(account.paid_balance_toman or 0) + toman_amount
        account.total_paid_topup_toman = int(account.total_paid_topup_toman or 0) + toman_amount
        account.version = int(account.version or 0) + 1
        user.credit_balance_usd = 0.0
        # Zero out wallet if it exists
        wallet = (await session.execute(select(Wallet).where(Wallet.user_id == user.id))).scalar_one_or_none()
        if wallet:
            wallet.balance_minor = 0
            wallet.available_minor = 0
            wallet.held_minor = 0
    if users_with_balance:
        await session.commit()


async def _repair_document_statuses(session: AsyncSession) -> None:
    from app.models import Document

    result = await session.execute(
        select(Document).where(
            Document.chunk_count > 0,
            Document.status.in_(["pending", "processing"]),
        )
    )
    docs = result.scalars().all()
    if docs:
        for doc in docs:
            doc.status = "indexed"
        await session.commit()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if DATABASE_URL.startswith("sqlite"):
            await _apply_sqlite_compat_migrations(conn)

    from app.llm import ensure_builtin_tool_bindings

    async with async_session() as session:
        await ensure_builtin_tool_bindings(session)
        await _seed_codex_prompt(session)
        await _migrate_usd_balances_to_toman(session)
        await _repair_document_statuses(session)


async def get_session():
    async with async_session() as session:
        yield session
