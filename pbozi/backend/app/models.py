from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    base_url = Column(String)
    api_key = Column(String)
    kind = Column(String, default="openai_compatible")
    config_json = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    models = relationship("Model", back_populates="provider")
    codex_accounts = relationship("CodexAccount", back_populates="provider")


class CapacityPool(Base):
    __tablename__ = "capacity_pools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    max_users = Column(Integer, default=50)
    active_users = Column(Integer, default=0)
    status = Column(String, default="active", index=True)
    fallback_behavior = Column(String, default="reject")
    fallback_model_id = Column(Integer, ForeignKey("models.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    fallback_model = relationship("Model", foreign_keys=[fallback_model_id])
    codex_accounts = relationship("CodexAccount", back_populates="pool")
    subscriptions = relationship("UserSubscription", back_populates="pool")


class CodexAccount(Base):
    __tablename__ = "codex_accounts"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True, index=True)
    pool_id = Column(Integer, ForeignKey("capacity_pools.id"), nullable=True, index=True)
    codex_home = Column(String, unique=True, nullable=False)
    auth_status = Column(String, default="pending", index=True)
    is_active = Column(Boolean, default=True)
    status = Column(String, default="active", index=True)
    max_users = Column(Integer, default=50)
    five_hour_limit = Column(Integer, default=0)
    five_hour_used = Column(Integer, default=0)
    weekly_limit = Column(Integer, default=0)
    weekly_used = Column(Integer, default=0)
    safety_buffer_percent = Column(Float, default=30.0)
    last_error = Column(Text, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    provider = relationship("Provider", back_populates="codex_accounts")
    pool = relationship("CapacityPool", back_populates="codex_accounts")


class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    display_name = Column(String, nullable=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True)
    pricing_input = Column(Float, default=0.0)
    pricing_output = Column(Float, default=0.0)
    context_window = Column(Integer, default=128000)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    capabilities = Column(JSON, nullable=True)

    provider = relationship("Provider", back_populates="models")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)
    owner_user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True, index=True)
    share_token = Column(String, unique=True, nullable=True, index=True)
    shared_from_project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    chats = relationship("Chat", back_populates="project")
    documents = relationship("Document", back_populates="project")
    owner = relationship("UserPreference", foreign_keys=[owner_user_id])
    shared_from_project = relationship("Project", remote_side=[id])


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="New Chat")
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=True)
    user_preference_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True, index=True)
    codex_thread_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="chats")
    user_preference = relationship("UserPreference", back_populates="chats")
    messages = relationship("Message", back_populates="chat", order_by="Message.created_at")
    tool_calls = relationship("ToolCall", back_populates="chat", order_by="ToolCall.created_at")

    @property
    def project_name(self):
        return self.project.name if self.project else None


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    role = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    chat = relationship("Chat", back_populates="messages")
    tool_calls = relationship("ToolCall", back_populates="message", order_by="ToolCall.created_at")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=True)
    filename = Column(String)
    file_type = Column(String)
    file_path = Column(String)
    chunk_count = Column(Integer, default=0)
    status = Column(String, default="pending", index=True)  # pending, processing, indexed, failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="documents")
    chat = relationship("Chat")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    telegram_user_id = Column(Integer, unique=True, index=True)
    first_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    preferred_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    account_status = Column(String, default="active")
    credit_balance_usd = Column(Float, default=0.0)
    current_chat_id = Column(Integer, nullable=True)
    current_project_id = Column(Integer, nullable=True)
    current_model_id = Column(Integer, nullable=True)
    is_admin = Column(Boolean, default=False)
    learning_preferences_status = Column(String, default="not_started")
    learning_preferences_summary = Column(Text, nullable=True)
    learning_preferences_prompt = Column(Text, nullable=True)
    learning_preferences_profile_json = Column(JSON, nullable=True)
    learning_preferences_onboarding_json = Column(JSON, nullable=True)
    learning_preferences_completed_at = Column(DateTime, nullable=True)
    custom_personalization = Column(Text, nullable=True)
    pending_action_payload = Column(JSON, nullable=True)
    is_pro = Column(Boolean, default=False)
    total_charged_usd = Column(Float, default=0.0)
    referral_campaign_id = Column(Integer, ForeignKey("referral_campaigns.id"), nullable=True, index=True)
    tip_pdf_math_dismissed = Column(Boolean, default=False)
    trial_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    referral_campaign = relationship("ReferralCampaign", back_populates="users", foreign_keys=[referral_campaign_id])
    chats = relationship("Chat", back_populates="user_preference")
    credit_ledger_entries = relationship(
        "CreditLedgerEntry",
        back_populates="user",
        order_by="CreditLedgerEntry.created_at",
        cascade="all, delete-orphan",
    )
    promo_code_redemptions = relationship(
        "PromoCodeRedemption",
        back_populates="user",
        order_by="PromoCodeRedemption.created_at",
        cascade="all, delete-orphan",
    )
    feedback_entries = relationship(
        "FeedbackEntry",
        back_populates="user",
        order_by="FeedbackEntry.created_at",
        cascade="all, delete-orphan",
    )
    wallet = relationship(
        "Wallet",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    billing_account = relationship(
        "UserBillingAccount",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    toman_ledger_entries = relationship(
        "TomanLedgerEntry",
        back_populates="user",
        order_by="TomanLedgerEntry.created_at",
        cascade="all, delete-orphan",
    )
    usage_events = relationship(
        "UsageEvent",
        back_populates="user",
        order_by="UsageEvent.created_at",
    )
    uploaded_files = relationship(
        "UploadedFile",
        back_populates="user",
        order_by="UploadedFile.created_at",
    )


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), unique=True, nullable=False, index=True)
    currency = Column(String, default="USD")
    balance_minor = Column(Integer, default=0)
    available_minor = Column(Integer, default=0)
    held_minor = Column(Integer, default=0)
    allow_negative = Column(Boolean, default=False)
    version = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference", back_populates="wallet")
    ledger_entries = relationship(
        "CreditLedgerEntry",
        back_populates="wallet",
        order_by="CreditLedgerEntry.created_at",
    )


class UserBillingAccount(Base):
    __tablename__ = "user_billing_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), unique=True, nullable=False, index=True)
    currency = Column(String, default="TOMAN")
    gift_balance_toman = Column(Integer, default=0)
    paid_balance_toman = Column(Integer, default=0)
    total_gift_granted_toman = Column(Integer, default=0)
    total_gift_spent_toman = Column(Integer, default=0)
    total_paid_topup_toman = Column(Integer, default=0)
    total_paid_spent_toman = Column(Integer, default=0)
    total_subscription_paid_toman = Column(Integer, default=0)
    first_topup_discount_used = Column(Boolean, default=False)
    version = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference", back_populates="billing_account")
    ledger_entries = relationship(
        "TomanLedgerEntry",
        back_populates="billing_account",
        order_by="TomanLedgerEntry.created_at",
    )


class TomanLedgerEntry(Base):
    __tablename__ = "toman_ledger_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    billing_account_id = Column(Integer, ForeignKey("user_billing_accounts.id"), nullable=True, index=True)
    amount_toman = Column(Integer, nullable=False)
    gift_delta_toman = Column(Integer, default=0)
    paid_delta_toman = Column(Integer, default=0)
    gift_balance_after_toman = Column(Integer, default=0)
    paid_balance_after_toman = Column(Integer, default=0)
    entry_type = Column(String, nullable=False, index=True)
    status = Column(String, default="posted")
    reason = Column(String, nullable=True)
    usage_event_id = Column(Integer, ForeignKey("usage_events.id"), nullable=True, index=True)
    admin_action_id = Column(Integer, ForeignKey("admin_actions.id"), nullable=True, index=True)
    idempotency_key = Column(String, unique=True, nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference", back_populates="toman_ledger_entries")
    billing_account = relationship("UserBillingAccount", back_populates="ledger_entries")
    usage_event = relationship("UsageEvent")
    admin_action = relationship("AdminAction", back_populates="toman_ledger_entries")


class CreditLedgerEntry(Base):
    __tablename__ = "credit_ledger_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True, index=True)
    amount_delta_usd = Column(Float, nullable=False)
    amount_minor = Column(Integer, nullable=True)
    balance_after_minor = Column(Integer, nullable=True)
    available_after_minor = Column(Integer, nullable=True)
    held_after_minor = Column(Integer, nullable=True)
    currency = Column(String, default="USD")
    direction = Column(String, nullable=True)
    entry_type = Column(String, nullable=False)
    status = Column(String, default="posted")
    reason = Column(String, nullable=True)
    usage_event_id = Column(Integer, ForeignKey("usage_events.id"), nullable=True, index=True)
    admin_action_id = Column(Integer, ForeignKey("admin_actions.id"), nullable=True, index=True)
    idempotency_key = Column(String, unique=True, nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference", back_populates="credit_ledger_entries")
    wallet = relationship("Wallet", back_populates="ledger_entries")
    usage_event = relationship("UsageEvent", back_populates="ledger_entries")
    admin_action = relationship("AdminAction", back_populates="ledger_entries")
    promo_code_redemptions = relationship(
        "PromoCodeRedemption",
        back_populates="credit_ledger_entry",
        order_by="PromoCodeRedemption.created_at",
    )


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    bonus_type = Column(String, default="fixed")
    currency = Column(String, default="USD")
    bonus_value_usd = Column(Float, default=0.0)
    bonus_value_toman = Column(Integer, default=0)
    minimum_charge_usd = Column(Float, default=0.0)
    minimum_charge_toman = Column(Integer, default=0)
    max_redemptions_total = Column(Integer, nullable=True)
    max_redemptions_per_user = Column(Integer, default=1)
    is_active = Column(Boolean, default=True, index=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    redemptions = relationship(
        "PromoCodeRedemption",
        back_populates="promo_code",
        order_by="PromoCodeRedemption.created_at",
        cascade="all, delete-orphan",
    )


class PromoCodeRedemption(Base):
    __tablename__ = "promo_code_redemptions"
    __table_args__ = (
        Index("ix_promo_code_redemptions_code_user", "promo_code_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    charge_amount_usd = Column(Float, default=0.0)
    charge_amount_toman = Column(Integer, default=0)
    bonus_amount_usd = Column(Float, default=0.0)
    bonus_amount_toman = Column(Integer, default=0)
    total_credit_usd = Column(Float, default=0.0)
    total_credit_toman = Column(Integer, default=0)
    credit_ledger_entry_id = Column(Integer, ForeignKey("credit_ledger_entries.id"), nullable=True, index=True)
    toman_ledger_entry_id = Column(Integer, ForeignKey("toman_ledger_entries.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    promo_code = relationship("PromoCode", back_populates="redemptions")
    user = relationship("UserPreference", back_populates="promo_code_redemptions")
    credit_ledger_entry = relationship("CreditLedgerEntry", back_populates="promo_code_redemptions")
    toman_ledger_entry = relationship("TomanLedgerEntry", foreign_keys=[toman_ledger_entry_id])


class FeedbackEntry(Base):
    __tablename__ = "feedback_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True, index=True)
    telegram_user_id = Column(Integer, nullable=True, index=True)
    chat_id = Column(Integer, nullable=True)
    message_id = Column(Integer, nullable=True)
    user_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    assistant_message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    rating_value = Column(Integer, nullable=False)
    source = Column(String, default="telegram_inline_button")
    note = Column(Text, nullable=True)
    reaction_raw_text = Column(Text, nullable=True)
    sample_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference", back_populates="feedback_entries")


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    uploaded_file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True, index=True)
    operation_type = Column(String, nullable=False, index=True)
    channel = Column(String, default="telegram")
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True)
    provider_name_snapshot = Column(String, nullable=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=True)
    model_name_snapshot = Column(String, nullable=True)
    pricing_snapshot_json = Column(JSON, nullable=True)
    request_id = Column(String, unique=True, nullable=True, index=True)
    request_payload_hash = Column(String, nullable=True)
    provider_request_id = Column(String, nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    units = Column(Integer, default=0)
    usage_source = Column(String, default="estimated")
    estimated_cost_minor = Column(Integer, default=0)
    actual_cost_minor = Column(Integer, default=0)
    status = Column(String, default="estimated", index=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    user = relationship("UserPreference", back_populates="usage_events")
    ledger_entries = relationship("CreditLedgerEntry", back_populates="usage_event")


class ModelPricing(Base):
    __tablename__ = "model_pricing"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True, index=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=True, index=True)
    operation_type = Column(String, nullable=False, index=True)
    currency = Column(String, default="USD")
    input_per_1m_minor = Column(Integer, default=0)
    output_per_1m_minor = Column(Integer, default=0)
    unit_price_minor = Column(Integer, default=0)
    minimum_charge_minor = Column(Integer, default=0)
    effective_from = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    effective_to = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class WebSearchConfig(Base):
    __tablename__ = "web_search_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    provider = Column(String, default="exa")
    base_url = Column(String, default="https://api.exa.ai/search")
    api_key = Column(String, nullable=True)
    search_type = Column(String, default="auto")
    max_results = Column(Integer, default=5)
    include_domains = Column(JSON, nullable=True)
    exclude_domains = Column(JSON, nullable=True)
    contents_options = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AdminAction(Base):
    __tablename__ = "admin_actions"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True, index=True)
    admin_telegram_user_id = Column(Integer, nullable=True, index=True)
    action_type = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=False)
    target_id = Column(Integer, nullable=True, index=True)
    before_json = Column(JSON, nullable=True)
    after_json = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ledger_entries = relationship("CreditLedgerEntry", back_populates="admin_action")
    toman_ledger_entries = relationship("TomanLedgerEntry", back_populates="admin_action")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    usage_event_id = Column(Integer, ForeignKey("usage_events.id"), nullable=True, index=True)
    telegram_file_id = Column(String, nullable=True)
    telegram_file_unique_id = Column(String, nullable=True, index=True)
    filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    size_bytes = Column(Integer, default=0)
    storage_path = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    status = Column(String, default="received", index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime, nullable=True)

    user = relationship("UserPreference", back_populates="uploaded_files")


class TelegramUpdateLog(Base):
    __tablename__ = "telegram_update_logs"

    id = Column(Integer, primary_key=True, index=True)
    update_id = Column(Integer, unique=True, nullable=False, index=True)
    update_key = Column(String, unique=True, nullable=True, index=True)
    telegram_user_id = Column(Integer, nullable=True, index=True)
    chat_id = Column(Integer, nullable=True, index=True)
    update_type = Column(String, nullable=True)
    status = Column(String, default="processing", index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class TelegramGroup(Base):
    __tablename__ = "telegram_groups"
    __table_args__ = (
        Index("ix_telegram_groups_status_type", "status", "chat_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    telegram_chat_id = Column(Integer, unique=True, nullable=False, index=True)
    title = Column(String, nullable=True)
    chat_type = Column(String, default="group", nullable=False)
    status = Column(String, default="active", index=True)
    trigger_phrases_json = Column(JSON, nullable=True)
    min_active_members = Column(Integer, default=2)
    app_chat_id = Column(Integer, ForeignKey("chats.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    members = relationship("TelegramGroupMember", back_populates="group", cascade="all, delete-orphan")
    usage_events = relationship(
        "GroupUsageEvent",
        back_populates="group",
        order_by="GroupUsageEvent.created_at",
        cascade="all, delete-orphan",
    )
    created_by_user = relationship("UserPreference")


class TelegramGroupMember(Base):
    __tablename__ = "telegram_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_telegram_group_members_group_user"),
        Index("ix_tgm_group_enabled_status", "group_id", "shared_billing_enabled", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("telegram_groups.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    telegram_user_id = Column(Integer, nullable=True, index=True)
    status = Column(String, default="active", index=True)
    shared_billing_enabled = Column(Boolean, default=False, index=True)
    last_opt_in_at = Column(DateTime, nullable=True)
    last_opt_out_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    group = relationship("TelegramGroup", back_populates="members")
    user = relationship("UserPreference")


class GroupUsageEvent(Base):
    __tablename__ = "group_usage_events"
    __table_args__ = (
        Index("ix_gue_group_status_created", "group_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("telegram_groups.id"), nullable=False, index=True)
    usage_event_id = Column(Integer, ForeignKey("usage_events.id"), nullable=True, index=True)
    triggered_by_user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True, index=True)
    request_id = Column(String, unique=True, nullable=True, index=True)
    telegram_chat_id = Column(Integer, nullable=True, index=True)
    telegram_message_id = Column(Integer, nullable=True, index=True)
    operation_type = Column(String, default="chat_completion", index=True)
    estimated_cost_minor = Column(Integer, default=0)
    actual_cost_minor = Column(Integer, default=0)
    split_member_count = Column(Integer, default=0)
    status = Column(String, default="pending", index=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    group = relationship("TelegramGroup", back_populates="usage_events")
    usage_event = relationship("UsageEvent")
    triggered_by_user = relationship("UserPreference")
    shares = relationship(
        "GroupUsageShare",
        back_populates="group_usage_event",
        order_by="GroupUsageShare.created_at",
        cascade="all, delete-orphan",
    )


class GroupUsageShare(Base):
    __tablename__ = "group_usage_shares"
    __table_args__ = (
        UniqueConstraint("group_usage_event_id", "user_id", name="uq_group_usage_shares_event_user"),
        Index("ix_gus_group_user_created", "group_id", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_usage_event_id = Column(Integer, ForeignKey("group_usage_events.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("telegram_groups.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    ledger_entry_id = Column(Integer, ForeignKey("credit_ledger_entries.id"), nullable=True, index=True)
    estimated_share_minor = Column(Integer, default=0)
    actual_share_minor = Column(Integer, default=0)
    status = Column(String, default="pending", index=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    group_usage_event = relationship("GroupUsageEvent", back_populates="shares")
    group = relationship("TelegramGroup")
    user = relationship("UserPreference")
    ledger_entry = relationship("CreditLedgerEntry")


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    content = Column(Text)
    is_active = Column(Boolean, default=True)
    auto_tool_guidance_enabled = Column(Boolean, default=True)
    tool_guidance_style = Column(String, default="compact")
    tool_guidance_template = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class EmbeddingConfig(Base):
    __tablename__ = "embedding_config"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    provider = Column(String, default="google")
    model = Column(String, default="text-embedding-004")
    api_key = Column(String, nullable=True)
    base_url = Column(String, default="https://generativelanguage.googleapis.com/v1beta")
    pricing_input = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TranscriptionConfig(Base):
    __tablename__ = "transcription_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    provider = Column(String, default="google")
    model = Column(String, default="gemini-3.1-flash-lite-preview")
    api_key = Column(String, nullable=True)
    base_url = Column(String, default="https://generativelanguage.googleapis.com/v1beta")
    pricing_input = Column(Float, default=0.5)
    pricing_output = Column(Float, default=1.5)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Tool(Base):
    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=True)
    description = Column(Text)
    kind = Column(String, default="builtin")
    implementation_key = Column(String, nullable=True)
    implementation_config = Column(JSON, nullable=True)
    input_schema = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    is_builtin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    bindings = relationship("ToolBinding", back_populates="tool", cascade="all, delete-orphan")
    calls = relationship("ToolCall", back_populates="tool")


class ToolBinding(Base):
    __tablename__ = "tool_bindings"

    id = Column(Integer, primary_key=True, index=True)
    tool_id = Column(Integer, ForeignKey("tools.id"), nullable=False, index=True)
    scope_type = Column(String, default="global")
    scope_id = Column(Integer, nullable=True)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tool = relationship("Tool", back_populates="bindings")
    calls = relationship("ToolCall", back_populates="binding")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(Integer, primary_key=True, index=True)
    tool_id = Column(Integer, ForeignKey("tools.id"), nullable=False, index=True)
    binding_id = Column(Integer, ForeignKey("tool_bindings.id"), nullable=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    provider_name = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    external_call_id = Column(String, nullable=True)
    arguments = Column(JSON, nullable=True)
    status = Column(String, default="pending")
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    tool = relationship("Tool", back_populates="calls")
    binding = relationship("ToolBinding", back_populates="calls")
    chat = relationship("Chat", back_populates="tool_calls")
    message = relationship("Message", back_populates="tool_calls")


class ProjectGroupShare(Base):
    __tablename__ = "project_group_shares"
    __table_args__ = (
        UniqueConstraint("project_id", "group_id", name="uq_project_group_shares_project_group"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("telegram_groups.id"), nullable=False, index=True)
    shared_by_user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    project = relationship("Project")
    group = relationship("TelegramGroup")
    shared_by = relationship("UserPreference")


class StarterCreditConfig(Base):
    __tablename__ = "starter_credit_configs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, default="default")
    amount_usd = Column(Float, default=0.0)
    amount_toman = Column(Integer, default=0)
    welcome_message = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, nullable=True)
    usage_rules = Column(Text, nullable=True)
    when_to_use = Column(Text, nullable=True)
    avoid_when = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)
    file_path = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ErrorLog(Base):
    __tablename__ = "error_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source = Column(String)
    error_message = Column(Text)
    stack_trace = Column(Text)
    user_id = Column(Integer, nullable=True)
    resolved = Column(Boolean, default=False)


class ReferralCampaign(Base):
    __tablename__ = "referral_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    created_by_admin_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    events = relationship("ReferralEvent", back_populates="campaign", cascade="all, delete-orphan")
    users = relationship("UserPreference", back_populates="referral_campaign", foreign_keys=[UserPreference.referral_campaign_id])


class ReferralConfig(Base):
    __tablename__ = "referral_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, default="default")
    reward_toman = Column(Integer, default=50000)
    reward_message = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ReferralEvent(Base):
    __tablename__ = "referral_events"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("referral_campaigns.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True) # 'start', 'signup', 'purchase'
    amount_usd = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    campaign = relationship("ReferralCampaign", back_populates="events")
    user = relationship("UserPreference")


class BotStartScenario(Base):
    __tablename__ = "bot_start_scenarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class AdminMessageButton(Base):
    __tablename__ = "admin_message_buttons"
    id: Mapped[int] = mapped_column(primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    plan_type = Column(String, default="monthly_credit")
    monthly_price_usd = Column(Float, default=0.0)
    monthly_price_toman = Column(Integer, default=0)
    gift_credit_toman = Column(Integer, default=0)
    cooldown_limit_toman = Column(Integer, default=0)
    cooldown_hours = Column(Integer, default=0)
    weekly_limit_toman = Column(Integer, default=0)
    allowed_tools_json = Column(JSON, nullable=True)
    allowed_skills_json = Column(JSON, nullable=True)
    is_agentic = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    rules = relationship("SubscriptionPlanRule", back_populates="plan", cascade="all, delete-orphan")
    subscriptions = relationship("UserSubscription", back_populates="plan", cascade="all, delete-orphan")


class SubscriptionPlanRule(Base):
    __tablename__ = "subscription_plan_rules"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False, index=True)
    free_chats_count = Column(Integer, default=0)
    free_tokens_per_chat = Column(Integer, default=0)
    discount_percent = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

    plan = relationship("SubscriptionPlan", back_populates="rules")
    model = relationship("Model")


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False, index=True)
    pool_id = Column(Integer, ForeignKey("capacity_pools.id"), nullable=True, index=True)
    status = Column(String, default="active", index=True)
    purchased_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False, index=True)
    cooldown_spent_toman = Column(Integer, default=0)
    cooldown_ends_at = Column(DateTime, nullable=True)
    weekly_spent_toman = Column(Integer, default=0)
    week_resets_at = Column(DateTime, nullable=True)

    user = relationship("UserPreference")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    pool = relationship("CapacityPool", back_populates="subscriptions")
    quotas = relationship("UserSubscriptionQuota", back_populates="user_subscription", cascade="all, delete-orphan")


class UserSubscriptionQuota(Base):
    __tablename__ = "user_subscription_quotas"
    id = Column(Integer, primary_key=True, index=True)
    user_subscription_id = Column(Integer, ForeignKey("user_subscriptions.id"), nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False, index=True)
    free_chats_remaining = Column(Integer, default=0)
    chat_token_quotas_json = Column(JSON, nullable=True) # {chat_id: tokens_remaining}
    discount_percent = Column(Float, default=0.0)

    user_subscription = relationship("UserSubscription", back_populates="quotas")
    model = relationship("Model")


class SubscriptionConfig(Base):
    __tablename__ = "subscription_configs"
    id = Column(Integer, primary_key=True, index=True)
    is_enabled = Column(Boolean, default=True)
    monthly_price_toman = Column(Integer, default=80000)
    gift_credit_toman = Column(Integer, default=100000)
    api_markup_percent = Column(Float, default=25.0)
    first_topup_discount_percent = Column(Float, default=50.0)
    first_topup_discount_cap_toman = Column(Integer, default=300000)
    usd_to_toman_rate = Column(Integer, default=50000)


class TrialConfig(Base):
    __tablename__ = "trial_configs"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    duration_hours = Column(Integer, default=48)
    is_enabled = Column(Boolean, default=False)
    apply_automatically = Column(Boolean, default=False)
    welcome_message = Column(Text, nullable=True)
    invitation_message = Column(Text, nullable=True)
    invitation_button_text = Column(String, default="فعال‌سازی اشتراک رایگان")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    plan = relationship("SubscriptionPlan")


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id = Column(Integer, primary_key=True, index=True)
    card_number = Column(String, unique=True, nullable=False, index=True)
    cardholder_name = Column(String, nullable=False)
    bank_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    amount_toman = Column(Integer, nullable=False)
    receipt_image_path = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    payment_type = Column(String, default="topup")  # topup, subscription
    plan_id = Column(Integer, nullable=True)  # for subscription payments
    status = Column(String, default="pending", index=True)  # pending, approved, rejected
    admin_note = Column(Text, nullable=True)
    approved_by = Column(Integer, ForeignKey("user_preferences.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference", foreign_keys=[user_id])
    approver = relationship("UserPreference", foreign_keys=[approved_by])


class LinkCode(Base):
    __tablename__ = "link_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    user_preference_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference")


class CodexProxyRequestLog(Base):
    __tablename__ = "codex_proxy_request_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, unique=True, index=True)
    model = Column(String, index=True)
    account_id = Column(Integer, ForeignKey("codex_accounts.id"), nullable=True, index=True)
    status = Column(String, default="success", index=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    has_image = Column(Boolean, default=False)
    image_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    account = relationship("CodexAccount")


class PromotionalLink(Base):
    __tablename__ = "promotional_links"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    offer_type = Column(String, nullable=False)  # credit_grant, free_subscription, topup_discount
    offer_value_toman = Column(Integer, default=0)
    offer_duration_hours = Column(Integer, default=0)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    discount_percent = Column(Float, default=0.0)
    max_redemptions = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("user_preferences.id"), nullable=True)

    plan = relationship("SubscriptionPlan")
    creator = relationship("UserPreference", foreign_keys=[created_by])
    clicks = relationship("PromotionalLinkClick", back_populates="link", cascade="all, delete-orphan")


class PromotionalLinkClick(Base):
    __tablename__ = "promotional_link_clicks"

    id = Column(Integer, primary_key=True, index=True)
    promotional_link_id = Column(Integer, ForeignKey("promotional_links.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    clicked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    redeemed_at = Column(DateTime, nullable=True)
    redemption_status = Column(String, default="pending")  # pending, redeemed, failed, already_used

    link = relationship("PromotionalLink", back_populates="clicks")
    user = relationship("UserPreference")

class Tip(Base):
    __tablename__ = "tips"
    id = Column(Integer, primary_key=True, index=True)
    trigger_key = Column(String, unique=True, index=True, nullable=False)
    tip_type = Column(String, default="event", index=True) # event, scheduled
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    delay_seconds = Column(Integer, default=0)
    auto_delete_seconds = Column(Integer, default=30)
    min_account_age_days = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class UserTipDismissal(Base):
    __tablename__ = "user_tip_dismissals"
    __table_args__ = (
        UniqueConstraint("user_id", "tip_id", name="uq_user_tip_dismissal"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_preferences.id"), nullable=False, index=True)
    tip_id = Column(Integer, ForeignKey("tips.id"), nullable=False, index=True)
    dismissed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("UserPreference")
    tip = relationship("Tip")

