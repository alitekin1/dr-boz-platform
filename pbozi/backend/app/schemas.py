from datetime import datetime
from typing import Literal, Optional, List

from pydantic import BaseModel, ConfigDict


class ProviderCreate(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    kind: str = "openai_compatible"
    config_json: Optional[dict] = None
    is_active: bool = True
    sync_models: bool = False
    model_names: Optional[list[str]] = None
    imported_models: Optional[list["ProviderImportedModelConfig"]] = None
    activate_imported_models: bool = False


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    kind: Optional[str] = None
    config_json: Optional[dict] = None
    is_active: Optional[bool] = None
    sync_models: Optional[bool] = None
    model_names: Optional[list[str]] = None
    imported_models: Optional[list["ProviderImportedModelConfig"]] = None
    activate_imported_models: Optional[bool] = None


class ProviderImportedModelConfig(BaseModel):
    name: str
    display_name: Optional[str] = None
    pricing_input: float = 0.0
    pricing_output: float = 0.0
    context_window: int = 128000
    is_active: bool = False


class ProviderOut(BaseModel):
    id: int
    name: str
    base_url: str | None = None
    api_key: str | None = None
    kind: str | None = None
    config_json: Optional[dict] = None
    is_active: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ProviderModelDiscoverRequest(BaseModel):
    base_url: str
    api_key: Optional[str] = None


class ProviderModelDiscoverOut(BaseModel):
    models: list[str]


class CapacityPoolCreate(BaseModel):
    name: str
    max_users: int = 50
    active_users: int = 0
    status: str = "active"
    fallback_behavior: str = "reject"
    fallback_model_id: Optional[int] = None


class CapacityPoolUpdate(BaseModel):
    name: Optional[str] = None
    max_users: Optional[int] = None
    active_users: Optional[int] = None
    status: Optional[str] = None
    fallback_behavior: Optional[str] = None
    fallback_model_id: Optional[int] = None


class CapacityPoolOut(BaseModel):
    id: int
    name: str
    max_users: int
    active_users: int
    status: str
    fallback_behavior: str
    fallback_model_id: Optional[int]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CodexAccountCreate(BaseModel):
    label: str
    provider_id: Optional[int] = None
    pool_id: Optional[int] = None
    is_active: bool = True
    status: str = "active"
    max_users: int = 50
    five_hour_limit: int = 0
    five_hour_used: int = 0
    weekly_limit: int = 0
    weekly_used: int = 0
    safety_buffer_percent: float = 30.0


class CodexAccountUpdate(BaseModel):
    label: Optional[str] = None
    provider_id: Optional[int] = None
    pool_id: Optional[int] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None
    max_users: Optional[int] = None
    five_hour_limit: Optional[int] = None
    five_hour_used: Optional[int] = None
    weekly_limit: Optional[int] = None
    weekly_used: Optional[int] = None
    safety_buffer_percent: Optional[float] = None
    auth_status: Optional[str] = None
    last_error: Optional[str] = None


class CodexAccountOut(BaseModel):
    id: int
    label: str
    provider_id: Optional[int]
    pool_id: Optional[int]
    codex_home: str
    auth_status: str
    is_active: bool
    status: str
    max_users: int
    five_hour_limit: int
    five_hour_used: int
    weekly_limit: int
    weekly_used: int
    safety_buffer_percent: float
    last_error: Optional[str]
    cooldown_until: Optional[datetime]
    last_used_at: Optional[datetime]
    metadata_json: Optional[dict]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class CodexAccountAuthStartOut(BaseModel):
    account_id: int
    codex_home: str
    argv: list[str]
    env: dict[str, str]
    shell: str


class CodexAccountStatusOut(BaseModel):
    account_id: int
    auth_status: str
    is_authenticated: bool
    stdout: str = ""
    stderr: str = ""


class CodexAccountLimitStatusOut(BaseModel):
    account_id: int
    checked_at: str
    status_text: str
    usage: Optional[dict] = None
    stderr: str = ""


class ModelCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    provider_id: Optional[int] = None
    pricing_input: float = 0.0
    pricing_output: float = 0.0
    context_window: int = 128000
    is_active: bool = True
    is_default: bool = False
    capabilities: Optional[dict] = None


class ModelUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    provider_id: Optional[int] = None
    pricing_input: Optional[float] = None
    pricing_output: Optional[float] = None
    context_window: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    capabilities: Optional[dict] = None


class ModelOut(BaseModel):
    id: int
    name: str
    display_name: Optional[str]
    provider_id: Optional[int]
    pricing_input: float
    pricing_output: float
    pricing_input_toman: int = 0
    pricing_output_toman: int = 0
    context_window: int
    is_active: bool
    is_default: bool
    capabilities: Optional[dict]

    class Config:
        from_attributes = True


class ModelBulkAction(BaseModel):
    ids: list[int]
    action: Literal["delete", "enable", "disable"]


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    instructions: Optional[str]
    owner_user_id: Optional[int]
    shared_from_project_id: Optional[int]
    import_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectShareOut(BaseModel):
    project_id: int
    share_token: str
    telegram_url: Optional[str] = None


class ChatCreate(BaseModel):
    project_id: Optional[int] = None
    model_id: Optional[int] = None
    user_preference_id: Optional[int] = None


class ChatOut(BaseModel):
    id: int
    title: str
    project_id: Optional[int]
    project_name: Optional[str] = None
    model_id: Optional[int]
    user_preference_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    chat_id: int
    role: str
    content: str


class MessageOut(BaseModel):
    id: int
    chat_id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    content: str
    model_id: Optional[int] = None
    user_id: Optional[int] = None
    telegram_user_id: Optional[int] = None


class ToolExecutionOut(BaseModel):
    id: int
    tool_name: str
    status: str
    arguments: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True


class SystemPromptCreate(BaseModel):
    name: str
    content: str
    is_active: bool = True
    auto_tool_guidance_enabled: bool = True
    tool_guidance_style: Literal["compact", "detailed"] = "compact"
    tool_guidance_template: Optional[str] = None


class SystemPromptUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    auto_tool_guidance_enabled: Optional[bool] = None
    tool_guidance_style: Optional[Literal["compact", "detailed"]] = None
    tool_guidance_template: Optional[str] = None


class SystemPromptOut(BaseModel):
    id: int
    name: str
    content: str
    is_active: bool = True
    auto_tool_guidance_enabled: Optional[bool] = True
    tool_guidance_style: Optional[str]
    tool_guidance_template: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class EmbeddingConfigCreate(BaseModel):
    name: str
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    pricing_input: float = 0.0
    is_active: bool = True


class EmbeddingConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    pricing_input: Optional[float] = None
    is_active: Optional[bool] = None


class EmbeddingConfigOut(BaseModel):
    id: int
    name: str
    provider: str
    model: str
    api_key: Optional[str]
    base_url: Optional[str]
    pricing_input: float
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserPreferenceOut(BaseModel):
    id: int
    telegram_user_id: Optional[int]
    first_name: Optional[str]
    username: Optional[str]
    preferred_name: Optional[str]
    phone_number: Optional[str]
    account_status: Optional[str]
    credit_balance_usd: float
    is_admin: bool
    is_pro: bool = False
    total_charged_usd: float = 0.0
    learning_preferences_status: Optional[str] = None
    learning_preferences_summary: Optional[str] = None
    learning_preferences_prompt: Optional[str] = None
    learning_preferences_profile_json: Optional[dict] = None
    learning_preferences_completed_at: Optional[datetime] = None
    created_at: datetime
    gift_balance_toman: int = 0
    paid_balance_toman: int = 0
    total_balance_toman: int = 0

    class Config:
        from_attributes = True


class UserPreferenceUpdate(BaseModel):
    preferred_name: Optional[str] = None
    phone: Optional[str] = None
    phone_number: Optional[str] = None
    account_status: Optional[str] = None
    is_admin: Optional[bool] = None
    is_pro: Optional[bool] = None
    total_charged_usd: Optional[float] = None
    credit: Optional[float] = None
    credit_balance: Optional[float] = None
    credit_balance_usd: Optional[float] = None
    learning_preferences_status: Optional[str] = None
    learning_preferences_summary: Optional[str] = None
    learning_preferences_prompt: Optional[str] = None
    learning_preferences_profile_json: Optional[dict] = None
    learning_preferences_onboarding_json: Optional[dict] = None


class LearningPreferencesTurnRequest(BaseModel):
    message: str


class LearningPreferencesSkipRequest(BaseModel):
    reason: Optional[str] = None


class CreditLedgerEntryOut(BaseModel):
    id: int
    user_id: int
    wallet_id: Optional[int] = None
    amount_delta_usd: float
    amount_minor: Optional[int] = None
    balance_after_minor: Optional[int] = None
    available_after_minor: Optional[int] = None
    held_after_minor: Optional[int] = None
    currency: Optional[str] = None
    direction: Optional[str] = None
    entry_type: str
    status: Optional[str] = None
    reason: Optional[str]
    usage_event_id: Optional[int] = None
    admin_action_id: Optional[int] = None
    idempotency_key: Optional[str] = None
    metadata_json: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class CreditAdjustmentCreate(BaseModel):
    amount: float
    direction: Literal["credit", "debit"] = "credit"
    reason: str
    idempotency_key: Optional[str] = None


class PromoCodeCreate(BaseModel):
    code: str
    description: Optional[str] = None
    bonus_type: Literal["fixed", "percent"] = "fixed"
    currency: Literal["USD", "TOMAN"] = "USD"
    bonus_value: float
    minimum_charge: float = 0.0
    max_redemptions_total: Optional[int] = None
    max_redemptions_per_user: int = 1
    is_active: bool = True
    expires_at: Optional[datetime] = None


class PromoCodeUpdate(BaseModel):
    code: Optional[str] = None
    description: Optional[str] = None
    bonus_type: Optional[Literal["fixed", "percent"]] = None
    currency: Optional[Literal["USD", "TOMAN"]] = None
    bonus_value: Optional[float] = None
    minimum_charge: Optional[float] = None
    max_redemptions_total: Optional[int] = None
    max_redemptions_per_user: Optional[int] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


class PromoCodeOut(BaseModel):
    id: int
    code: str
    description: Optional[str]
    bonus_type: str
    currency: str
    bonus_value_usd: float
    bonus_value_toman: int
    minimum_charge_usd: float
    minimum_charge_toman: int
    max_redemptions_total: Optional[int]
    max_redemptions_per_user: int
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PromoCodeRedemptionCreate(BaseModel):
    code: str
    charge_amount: float = 0.0
    charge_amount_toman: int = 0
    currency: Literal["USD", "TOMAN"] = "USD"


class PromoCodeRedemptionOut(BaseModel):
    id: int
    promo_code_id: int
    user_id: int
    charge_amount_usd: float
    charge_amount_toman: int
    bonus_amount_usd: float
    bonus_amount_toman: int
    total_credit_usd: float
    total_credit_toman: int
    credit_ledger_entry_id: Optional[int] = None
    toman_ledger_entry_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WalletOut(BaseModel):
    id: int
    user_id: int
    currency: str
    balance_minor: int
    available_minor: int
    held_minor: int
    allow_negative: bool
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UsageEventOut(BaseModel):
    id: int
    user_id: int
    chat_id: Optional[int]
    message_id: Optional[int]
    uploaded_file_id: Optional[int]
    operation_type: str
    channel: Optional[str]
    provider_id: Optional[int]
    provider_name_snapshot: Optional[str]
    model_id: Optional[int]
    model_name_snapshot: Optional[str]
    pricing_snapshot_json: Optional[dict]
    request_id: Optional[str]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    units: int
    usage_source: Optional[str]
    estimated_cost_minor: int
    actual_cost_minor: int
    status: str
    error: Optional[str]
    metadata_json: Optional[dict]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class TelegramGroupBase(BaseModel):
    title: Optional[str] = None
    chat_type: str = "group"
    status: str = "active"
    trigger_phrases_json: Optional[list[str]] = None
    min_active_members: int = 2
    app_chat_id: Optional[int] = None


class TelegramGroupCreate(TelegramGroupBase):
    telegram_chat_id: int
    created_by_user_id: Optional[int] = None


class TelegramGroupUpdate(BaseModel):
    title: Optional[str] = None
    chat_type: Optional[str] = None
    status: Optional[str] = None
    trigger_phrases_json: Optional[list[str]] = None
    min_active_members: Optional[int] = None
    created_by_user_id: Optional[int] = None


class TelegramGroupOut(TelegramGroupBase):
    id: int
    telegram_chat_id: int
    created_by_user_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TelegramGroupMemberCreate(BaseModel):
    group_id: int
    user_id: int
    telegram_user_id: Optional[int] = None
    status: str = "active"
    shared_billing_enabled: bool = False


class TelegramGroupMemberUpdate(BaseModel):
    status: Optional[str] = None
    shared_billing_enabled: Optional[bool] = None
    telegram_user_id: Optional[int] = None


class TelegramGroupMemberOut(BaseModel):
    id: int
    group_id: int
    user_id: int
    telegram_user_id: Optional[int]
    status: str
    shared_billing_enabled: bool
    last_opt_in_at: Optional[datetime]
    last_opt_out_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GroupUsageShareOut(BaseModel):
    id: int
    group_usage_event_id: int
    group_id: int
    user_id: int
    ledger_entry_id: Optional[int]
    estimated_share_minor: int
    actual_share_minor: int
    status: str
    error: Optional[str]
    metadata_json: Optional[dict]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class GroupUsageEventOut(BaseModel):
    id: int
    group_id: int
    usage_event_id: Optional[int]
    triggered_by_user_id: Optional[int]
    request_id: Optional[str]
    telegram_chat_id: Optional[int]
    telegram_message_id: Optional[int]
    operation_type: str
    estimated_cost_minor: int
    actual_cost_minor: int
    split_member_count: int
    status: str
    error: Optional[str]
    metadata_json: Optional[dict]
    created_at: datetime
    completed_at: Optional[datetime]
    shares: Optional[list[GroupUsageShareOut]] = None

    class Config:
        from_attributes = True


class AdminActionOut(BaseModel):
    id: int
    admin_user_id: Optional[int]
    admin_telegram_user_id: Optional[int]
    action_type: str
    target_type: str
    target_id: Optional[int]
    before_json: Optional[dict]
    after_json: Optional[dict]
    reason: Optional[str]
    metadata_json: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackEntryOut(BaseModel):
    id: int
    user_id: Optional[int]
    telegram_user_id: Optional[int]
    chat_id: Optional[int]
    message_id: Optional[int]
    user_message_id: Optional[int]
    assistant_message_id: Optional[int]
    rating_value: int
    source: Optional[str]
    note: Optional[str]
    reaction_raw_text: Optional[str]
    sample_reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ToolBase(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: str
    kind: str = "builtin"
    implementation_key: Optional[str] = None
    implementation_config: Optional[dict] = None
    input_schema: Optional[dict] = None
    is_active: bool = True


class ToolCreate(ToolBase):
    is_builtin: bool = False


class ToolUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[str] = None
    implementation_key: Optional[str] = None
    implementation_config: Optional[dict] = None
    input_schema: Optional[dict] = None
    is_active: Optional[bool] = None


class ToolOut(ToolBase):
    id: int
    is_builtin: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ToolBindingCreate(BaseModel):
    tool_id: int
    scope_type: str = "global"
    scope_id: Optional[int] = None
    is_enabled: bool = True


class ToolBindingUpdate(BaseModel):
    scope_type: Optional[str] = None
    scope_id: Optional[int] = None
    is_enabled: Optional[bool] = None


class ToolBindingOut(BaseModel):
    id: int
    tool_id: int
    scope_type: str
    scope_id: Optional[int]
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
    tool: ToolOut

    class Config:
        from_attributes = True


class ToolCallOut(BaseModel):
    id: int
    tool_id: int
    binding_id: Optional[int]
    chat_id: Optional[int]
    message_id: Optional[int]
    provider_name: Optional[str]
    model_name: Optional[str]
    external_call_id: Optional[str]
    arguments: Optional[dict]
    status: str
    result: Optional[dict]
    error: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    tool: ToolOut

    class Config:
        from_attributes = True


class WebSearchConfigBase(BaseModel):
    name: str = "default"
    provider: Literal["exa"] = "exa"
    base_url: str = "https://api.exa.ai/search"
    search_type: Literal["auto", "neural", "keyword"] = "auto"
    max_results: int = 5
    include_domains: Optional[list[str]] = None
    exclude_domains: Optional[list[str]] = None
    contents_options: Optional[dict] = None
    is_active: bool = True


class WebSearchConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[Literal["exa"]] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    search_type: Optional[Literal["auto", "neural", "keyword"]] = None
    max_results: Optional[int] = None
    include_domains: Optional[list[str]] = None
    exclude_domains: Optional[list[str]] = None
    contents_options: Optional[dict] = None
    is_active: Optional[bool] = None


class WebSearchConfigOut(WebSearchConfigBase):
    id: int
    api_key_set: bool
    created_at: datetime
    updated_at: datetime


class TranscriptionConfigBase(BaseModel):
    name: str = "default"
    provider: Literal["google", "openrouter"] = "google"
    model: str = "gemini-1.5-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    pricing_input: float = 0.5
    pricing_output: float = 1.5
    is_active: bool = True


class TranscriptionConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[Literal["google", "openrouter"]] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    pricing_input: Optional[float] = None
    pricing_output: Optional[float] = None
    is_active: Optional[bool] = None


class TranscriptionConfigOut(TranscriptionConfigBase):
    id: int
    api_key_set: bool
    created_at: datetime
    updated_at: datetime


class StarterCreditConfigBase(BaseModel):
    name: str = "default"
    amount_usd: float = 0.0
    amount_toman: int = 0
    welcome_message: Optional[str] = None
    is_active: bool = True


class StarterCreditConfigUpdate(BaseModel):
    name: Optional[str] = None
    amount_usd: Optional[float] = None
    amount_toman: Optional[int] = None
    welcome_message: Optional[str] = None
    is_active: Optional[bool] = None


class StarterCreditConfigOut(StarterCreditConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime


class TelegramBotStatusOut(BaseModel):
    running: bool
    pid: Optional[int] = None
    managed: bool = False
    started_at: Optional[str] = None
    detail: Optional[str] = None


class BroadcastRequest(BaseModel):
    message: str
    target_user_ids: Optional[list[int]] = None  # If None, send to all
    target_groups: Optional[list[str]] = None   # e.g., ["active", "suspended"]


class BroadcastOut(BaseModel):
    success_count: int
    failure_count: int
    total_targeted: int
    errors: Optional[list[dict]] = None


class BulkGrantTrialRequest(BaseModel):
    user_ids: Optional[list[int]] = None
    skip_if_used: bool = True


class BulkGrantTrialOut(BaseModel):
    success_count: int
    skipped_count: int
    error_count: int
    total_targeted: int
    details: Optional[list[dict]] = None


class SkillBase(BaseModel):
    name: str
    description: Optional[str] = None
    usage_rules: Optional[str] = None
    when_to_use: Optional[str] = None
    avoid_when: Optional[str] = None
    is_active: bool = True


class SkillCreate(SkillBase):
    pass


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    usage_rules: Optional[str] = None
    when_to_use: Optional[str] = None
    avoid_when: Optional[str] = None
    is_active: Optional[bool] = None


class SkillOut(SkillBase):
    id: int
    instructions: Optional[str] = None
    file_path: Optional[str] = None
    files: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ErrorLogBase(BaseModel):
    source: str
    error_message: str
    stack_trace: str
    user_id: Optional[int] = None
    resolved: bool = False


class ErrorLogResponse(ErrorLogBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True


class ReferralCampaignCreate(BaseModel):
    description: Optional[str] = None


class ReferralCampaignOut(BaseModel):
    id: int
    code: str
    description: Optional[str]
    created_by_admin_id: Optional[int]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ReferralStatsOut(BaseModel):
    campaign: ReferralCampaignOut
    starts: int
    signups: int
    purchases: int
    revenue_usd: float


class BotStartScenarioSchema(BaseModel):
    id: int
    label: str
    prompt: str
    order: int
    is_active: bool

    class Config:
        from_attributes = True


class BotStartScenarioCreate(BaseModel):
    label: str
    prompt: str
    order: int = 0
    is_active: bool = True


class BotStartScenarioUpdate(BaseModel):
    label: Optional[str] = None
    prompt: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None

class SubscriptionPlanCreate(BaseModel):
    name: str
    plan_type: str = "monthly_credit"
    monthly_price_toman: int = 0
    gift_credit_toman: int = 0
    cooldown_limit_toman: int = 0
    cooldown_hours: int = 0
    weekly_limit_toman: int = 0
    allowed_tools_json: Optional[list[str]] = None
    allowed_skills_json: Optional[list[str]] = None
    is_agentic: bool = True
    is_active: bool = True


class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    plan_type: Optional[str] = None
    monthly_price_toman: Optional[int] = None
    gift_credit_toman: Optional[int] = None
    cooldown_limit_toman: Optional[int] = None
    cooldown_hours: Optional[int] = None
    weekly_limit_toman: Optional[int] = None
    allowed_tools_json: Optional[list[str]] = None
    allowed_skills_json: Optional[list[str]] = None
    is_agentic: Optional[bool] = None
    is_active: Optional[bool] = None

class SubscriptionPlanOut(SubscriptionPlanCreate):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

class SubscriptionPlanRuleCreate(BaseModel):
    model_id: int
    free_chats_count: int
    free_tokens_per_chat: int
    discount_percent: float
    is_active: bool = True

class SubscriptionPlanRuleOut(SubscriptionPlanRuleCreate):
    id: int
    plan_id: int
    
    model_config = ConfigDict(from_attributes=True)


class SubscriptionConfigOut(BaseModel):
    id: int
    is_enabled: bool = True
    monthly_price_toman: Optional[int] = 80000
    gift_credit_toman: Optional[int] = 100000
    api_markup_percent: Optional[float] = 25.0
    first_topup_discount_percent: Optional[float] = 50.0
    first_topup_discount_cap_toman: Optional[int] = 300000
    usd_to_toman_rate: Optional[int] = 50000
    model_config = ConfigDict(from_attributes=True)


class SubscriptionConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    monthly_price_toman: Optional[int] = None
    gift_credit_toman: Optional[int] = None
    api_markup_percent: Optional[float] = None
    first_topup_discount_percent: Optional[float] = None
    first_topup_discount_cap_toman: Optional[int] = None
    usd_to_toman_rate: Optional[int] = None


class AdminUserSubscriptionOut(BaseModel):
    id: int
    user_id: int
    telegram_user_id: Optional[int] = None
    first_name: Optional[str] = None
    username: Optional[str] = None
    phone_number: Optional[str] = None
    gift_balance_toman: int = 0
    paid_balance_toman: int = 0
    total_balance_toman: int = 0
    plan_id: int
    plan_name: Optional[str] = None
    pool_id: Optional[int] = None
    pool_name: Optional[str] = None
    status: str
    purchased_at: datetime
    expires_at: datetime
    is_active_now: bool = False


class TomanLedgerEntryOut(BaseModel):
    id: int
    user_id: int
    billing_account_id: Optional[int] = None
    amount_toman: int
    gift_delta_toman: int = 0
    paid_delta_toman: int = 0
    gift_balance_after_toman: int = 0
    paid_balance_after_toman: int = 0
    entry_type: str
    status: Optional[str] = None
    reason: Optional[str] = None
    usage_event_id: Optional[int] = None
    admin_action_id: Optional[int] = None
    idempotency_key: Optional[str] = None
    metadata_json: Optional[dict] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserTomanBillingSummaryOut(BaseModel):
    user_id: int
    gift_balance_toman: int = 0
    paid_balance_toman: int = 0
    total_balance_toman: int = 0
    total_gift_granted_toman: int = 0
    total_gift_spent_toman: int = 0
    total_paid_topup_toman: int = 0
    total_paid_spent_toman: int = 0
    total_subscription_paid_toman: int = 0
    first_topup_discount_used: bool = False
    ledger_entries: list[TomanLedgerEntryOut] = []


class BackupStatusOut(BaseModel):
    enabled: bool
    interval_minutes: int
    max_count: int
    running: bool
    next_run: Optional[str] = None


class BackupRunOut(BaseModel):
    status: str
    archive_name: Optional[str] = None
    drive_file_id: Optional[str] = None
    timestamp: str
    error: Optional[str] = None


class TrialConfigOut(BaseModel):
    id: int
    plan_id: Optional[int]
    duration_hours: int
    is_enabled: bool
    apply_automatically: bool
    welcome_message: Optional[str]
    invitation_message: Optional[str]
    invitation_button_text: Optional[str]
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrialConfigUpdate(BaseModel):
    plan_id: Optional[int] = None
    duration_hours: Optional[int] = None
    is_enabled: Optional[bool] = None
    apply_automatically: Optional[bool] = None
    welcome_message: Optional[str] = None
    invitation_message: Optional[str] = None
    invitation_button_text: Optional[str] = None


class UserBillingAccountOut(BaseModel):
    user_id: int
    gift_balance_toman: int = 0
    paid_balance_toman: int = 0
    total_balance_toman: int = 0
    total_gift_granted_toman: int = 0
    total_gift_spent_toman: int = 0
    total_paid_topup_toman: int = 0
    total_paid_spent_toman: int = 0
    total_subscription_paid_toman: int = 0
    first_topup_discount_used: bool = False


class UserSubscriptionStatusOut(BaseModel):
    id: int
    plan_id: int
    plan_name: Optional[str] = None
    plan_type: Optional[str] = None
    status: str
    purchased_at: datetime
    expires_at: datetime
    is_active_now: bool = False
    cooldown_spent_toman: int = 0
    cooldown_limit_toman: int = 0
    cooldown_hours: int = 0
    cooldown_ends_at: Optional[datetime] = None
    is_in_cooldown: bool = False
    cooldown_remaining_seconds: Optional[int] = None
    weekly_spent_toman: int = 0
    weekly_limit_toman: int = 0
    week_resets_at: Optional[datetime] = None


class UserSubscriptionPurchaseRequest(BaseModel):
    plan_id: int


class UserTopupApplyRequest(BaseModel):
    credit_amount_toman: int


class UserUsagePermissionOut(BaseModel):
    can_chat: bool
    reason: Optional[str] = None
    billing_account: Optional[UserBillingAccountOut] = None
    subscription: Optional[UserSubscriptionStatusOut] = None
    billable_cost_toman: int = 0
    cooldown_remaining_seconds: Optional[int] = None


class UserTrialClaimRequest(BaseModel):
    pass


class UserTrialClaimOut(BaseModel):
    ok: bool
    subscription_id: Optional[int] = None
    expires_at: Optional[datetime] = None
    reason: Optional[str] = None


class PaymentMethodCreate(BaseModel):
    card_number: str
    cardholder_name: str
    bank_name: str
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class PaymentMethodUpdate(BaseModel):
    card_number: Optional[str] = None
    cardholder_name: Optional[str] = None
    bank_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class PaymentMethodOut(BaseModel):
    id: int
    card_number: str
    cardholder_name: str
    bank_name: str
    description: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PaymentRequestCreate(BaseModel):
    amount_toman: int
    description: Optional[str] = None


class PaymentRequestOut(BaseModel):
    id: int
    user_id: int
    first_name: Optional[str] = None
    username: Optional[str] = None
    amount_toman: int
    receipt_image_path: str
    description: Optional[str] = None
    payment_type: str
    plan_id: Optional[int] = None
    status: str
    admin_note: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PaymentRequestApprove(BaseModel):
    admin_note: Optional[str] = None


class PaymentRequestReject(BaseModel):
    admin_note: str


class LinkCodeOut(BaseModel):
    code: str
    expires_at: datetime
    user_name: str

    model_config = ConfigDict(from_attributes=True)


class LinkCodeValidateResponse(BaseModel):
    telegram_user_id: int
    first_name: Optional[str]
    username: Optional[str]
    is_admin: bool
    is_pro: bool
    preferred_name: Optional[str]


class PromotionalLinkCreate(BaseModel):
    title: str
    description: Optional[str] = None
    offer_type: Literal["credit_grant", "free_subscription", "topup_discount"]
    offer_value_toman: int = 0
    offer_duration_hours: int = 0
    plan_id: Optional[int] = None
    discount_percent: float = 0.0
    max_redemptions: Optional[int] = None
    expires_at: Optional[datetime] = None


class PromotionalLinkUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    offer_type: Optional[Literal["credit_grant", "free_subscription", "topup_discount"]] = None
    offer_value_toman: Optional[int] = None
    offer_duration_hours: Optional[int] = None
    plan_id: Optional[int] = None
    discount_percent: Optional[float] = None
    max_redemptions: Optional[int] = None
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class PromotionalLinkOut(BaseModel):
    id: int
    code: str
    title: str
    description: Optional[str] = None
    offer_type: str
    offer_value_toman: int
    offer_duration_hours: int
    plan_id: Optional[int] = None
    discount_percent: float
    max_redemptions: Optional[int] = None
    expires_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    created_by: Optional[int] = None
    total_clicks: int = 0
    total_redemptions: int = 0

    model_config = ConfigDict(from_attributes=True)


class PromotionalLinkClickOut(BaseModel):
    id: int
    promotional_link_id: int
    user_id: int
    clicked_at: datetime
    redeemed_at: Optional[datetime] = None
    redemption_status: str

    model_config = ConfigDict(from_attributes=True)


class PromotionalLinkStats(BaseModel):
    total_clicks: int
    total_redemptions: int
    total_failed: int
    total_already_used: int
    conversion_rate: float
    clicks: List[PromotionalLinkClickOut] = []

class TipBase(BaseModel):
    trigger_key: str
    tip_type: str = "event"
    content: str
    is_active: bool = True
    delay_seconds: int = 0
    auto_delete_seconds: int = 30
    min_account_age_days: int = 0

class TipCreate(TipBase):
    pass

class TipUpdate(BaseModel):
    trigger_key: Optional[str] = None
    tip_type: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    delay_seconds: Optional[int] = None
    auto_delete_seconds: Optional[int] = None
    min_account_age_days: Optional[int] = None

class TipOut(TipBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

