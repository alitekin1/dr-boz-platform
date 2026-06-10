"""
SQLAlchemy models for the ERA (Dr. Boz) account database.
These models map to the existing era-app SQLite database tables.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship

log = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass


class UserPreference(Base):
    """Main user table in the ERA database."""
    __tablename__ = 'user_preferences'

    id = Column(Integer, primary_key=True)
    telegram_user_id = Column(Integer, nullable=True)
    first_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    preferred_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    account_status = Column(String, nullable=True, default='active')
    credit_balance_usd = Column(Float, nullable=True, default=0.0)
    is_admin = Column(Boolean, nullable=True, default=False)
    is_pro = Column(Boolean, nullable=True, default=False)
    total_charged_usd = Column(Float, nullable=True, default=0.0)
    referral_campaign_id = Column(Integer, nullable=True)
    trial_used = Column(Boolean, nullable=True, default=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class SubscriptionPlan(Base):
    """Subscription plan definitions."""
    __tablename__ = 'subscription_plans'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    plan_type = Column(String, nullable=True)
    monthly_price_usd = Column(Float, nullable=True)
    monthly_price_toman = Column(Integer, nullable=True)
    gift_credit_toman = Column(Integer, nullable=True)
    cooldown_limit_toman = Column(Integer, nullable=True)
    cooldown_hours = Column(Integer, nullable=True)
    weekly_limit_toman = Column(Integer, nullable=True)
    allowed_tools_json = Column(JSON, nullable=True)
    is_agentic = Column(Boolean, nullable=True)
    is_active = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class UserSubscription(Base):
    """User's active/past subscriptions."""
    __tablename__ = 'user_subscriptions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user_preferences.id'), nullable=False)
    plan_id = Column(Integer, ForeignKey('subscription_plans.id'), nullable=False)
    pool_id = Column(Integer, nullable=True)
    status = Column(String, nullable=True, default='active')
    purchased_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    cooldown_spent_toman = Column(Integer, nullable=True, default=0)
    cooldown_ends_at = Column(DateTime, nullable=True)
    weekly_spent_toman = Column(Integer, nullable=True, default=0)
    week_resets_at = Column(DateTime, nullable=True)

    plan = relationship('SubscriptionPlan', lazy='selectin')


class UserBillingAccount(Base):
    """User's billing/wallet account in toman."""
    __tablename__ = 'user_billing_accounts'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user_preferences.id'), nullable=False)
    currency = Column(String, nullable=True)
    gift_balance_toman = Column(Integer, nullable=True, default=0)
    paid_balance_toman = Column(Integer, nullable=True, default=0)
    total_gift_granted_toman = Column(Integer, nullable=True, default=0)
    total_gift_spent_toman = Column(Integer, nullable=True, default=0)
    total_paid_topup_toman = Column(Integer, nullable=True, default=0)
    total_paid_spent_toman = Column(Integer, nullable=True, default=0)
    total_subscription_paid_toman = Column(Integer, nullable=True, default=0)
    first_topup_discount_used = Column(Boolean, nullable=True, default=False)
    version = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class TomanLedgerEntry(Base):
    """Transaction history in toman."""
    __tablename__ = 'toman_ledger_entries'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('user_preferences.id'), nullable=False)
    billing_account_id = Column(Integer, nullable=True)
    amount_toman = Column(Integer, nullable=False)
    gift_delta_toman = Column(Integer, nullable=True, default=0)
    paid_delta_toman = Column(Integer, nullable=True, default=0)
    gift_balance_after_toman = Column(Integer, nullable=True)
    paid_balance_after_toman = Column(Integer, nullable=True)
    entry_type = Column(String, nullable=False)
    status = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    usage_event_id = Column(Integer, nullable=True)
    admin_action_id = Column(Integer, nullable=True)
    idempotency_key = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)


class ReferralCampaign(Base):
    """Referral campaign definitions."""
    __tablename__ = 'referral_campaigns'

    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime, nullable=True)


class ReferralEvent(Base):
    """Referral events (signups, rewards)."""
    __tablename__ = 'referral_events'

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey('referral_campaigns.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('user_preferences.id'), nullable=False)
    event_type = Column(String, nullable=False)
    amount_usd = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=True)


class ReferralConfig(Base):
    """Referral configuration."""
    __tablename__ = 'referral_configs'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    reward_toman = Column(Integer, nullable=True, default=50000)
    is_active = Column(Boolean, nullable=True, default=True)
