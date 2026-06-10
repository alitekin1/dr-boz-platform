from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Model,
    SubscriptionConfig,
    SubscriptionPlan,
    TomanLedgerEntry,
    UserBillingAccount,
    UserPreference,
    UserSubscription,
)
from app.services.codex_capacity_service import CodexCapacityError, assign_subscription_pool


DEFAULT_MONTHLY_PRICE_TOMAN = 80_000
DEFAULT_GIFT_CREDIT_TOMAN = 100_000
DEFAULT_API_MARKUP_PERCENT = 25.0
DEFAULT_FIRST_TOPUP_DISCOUNT_PERCENT = 50.0
DEFAULT_FIRST_TOPUP_DISCOUNT_CAP_TOMAN = 300_000
DEFAULT_USD_TO_TOMAN_RATE = 50_000


@dataclass
class PurchaseTomanSubscriptionResult:
    ok: bool
    account: UserBillingAccount
    subscription: UserSubscription | None = None
    payment_toman: int = 0
    gift_credit_toman: int = 0
    wallet_payment_toman: int = 0
    external_payment_toman: int = 0
    ledger_entries: list[TomanLedgerEntry] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class TopupQuote:
    credit_amount_toman: int
    normal_payment_toman: int
    payment_due_toman: int
    discount_toman: int
    discount_applied: bool
    discounted_credit_toman: int
    markup_percent: float
    discount_percent: float


@dataclass
class TopupResult:
    ok: bool
    account: UserBillingAccount
    quote: TopupQuote
    ledger_entry: TomanLedgerEntry | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ChatUsageQuote:
    global_api_cost_usd: float
    base_cost_toman: int
    billable_cost_toman: int
    usd_to_toman_rate: int
    markup_percent: float
    pricing_snapshot: dict[str, Any]


@dataclass
class ChatUsageChargeResult:
    ok: bool
    account: UserBillingAccount
    global_api_cost_usd: float = 0.0
    base_cost_toman: int = 0
    billable_cost_toman: int = 0
    gift_spent_toman: int = 0
    paid_spent_toman: int = 0
    ledger_entry: TomanLedgerEntry | None = None
    metadata: dict[str, Any] | None = None
    reason: str | None = None
    user_sub: UserSubscription | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _round_toman(value: Decimal | float | int | str) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _positive_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value or default))
    except (TypeError, ValueError):
        return default


def _positive_float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value if value is not None else default))
    except (TypeError, ValueError):
        return default


async def get_or_create_subscription_config(db: AsyncSession) -> SubscriptionConfig:
    config = (await db.execute(select(SubscriptionConfig))).scalars().first()
    if config is None:
        config = SubscriptionConfig(
            is_enabled=True,
            monthly_price_toman=DEFAULT_MONTHLY_PRICE_TOMAN,
            gift_credit_toman=DEFAULT_GIFT_CREDIT_TOMAN,
            api_markup_percent=DEFAULT_API_MARKUP_PERCENT,
            first_topup_discount_percent=DEFAULT_FIRST_TOPUP_DISCOUNT_PERCENT,
            first_topup_discount_cap_toman=DEFAULT_FIRST_TOPUP_DISCOUNT_CAP_TOMAN,
            usd_to_toman_rate=DEFAULT_USD_TO_TOMAN_RATE,
        )
        db.add(config)
        await db.flush()
    return config


async def get_or_create_billing_account(db: AsyncSession, user: UserPreference) -> UserBillingAccount:
    account = (
        await db.execute(select(UserBillingAccount).where(UserBillingAccount.user_id == user.id))
    ).scalars().first()
    if account is None:
        account = UserBillingAccount(user_id=user.id)
        db.add(account)
        await db.flush()
    return account


async def _existing_ledger(db: AsyncSession, idempotency_key: str | None) -> TomanLedgerEntry | None:
    if not idempotency_key:
        return None
    return (
        await db.execute(select(TomanLedgerEntry).where(TomanLedgerEntry.idempotency_key == idempotency_key))
    ).scalar_one_or_none()


def _new_ledger_entry(
    *,
    user: UserPreference,
    account: UserBillingAccount,
    amount_toman: int,
    gift_delta_toman: int,
    paid_delta_toman: int,
    entry_type: str,
    reason: str | None,
    usage_event_id: int | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TomanLedgerEntry:
    return TomanLedgerEntry(
        user_id=user.id,
        billing_account_id=account.id,
        amount_toman=int(amount_toman),
        gift_delta_toman=int(gift_delta_toman),
        paid_delta_toman=int(paid_delta_toman),
        gift_balance_after_toman=int(account.gift_balance_toman or 0),
        paid_balance_after_toman=int(account.paid_balance_toman or 0),
        entry_type=entry_type,
        status="posted",
        reason=reason,
        usage_event_id=usage_event_id,
        idempotency_key=idempotency_key,
        metadata_json=metadata or {},
    )


def _plan_price_toman(plan: SubscriptionPlan, config: SubscriptionConfig) -> int:
    plan_price = getattr(plan, "monthly_price_toman", None)
    if plan_price is not None:
        return max(0, int(plan_price))
    return _positive_int(config.monthly_price_toman, DEFAULT_MONTHLY_PRICE_TOMAN)


def _plan_gift_toman(plan: SubscriptionPlan, config: SubscriptionConfig) -> int:
    plan_gift = getattr(plan, "gift_credit_toman", None)
    if plan_gift is not None:
        return max(0, int(plan_gift))
    return _positive_int(config.gift_credit_toman, DEFAULT_GIFT_CREDIT_TOMAN)


async def purchase_toman_subscription(
    db: AsyncSession,
    *,
    user: UserPreference,
    plan: SubscriptionPlan,
    idempotency_key: str | None = None,
    payment_confirmed: bool = False,
    wallet_payment_toman: int | None = None,
    grant_gift_toman_balance: bool = True,
    commit: bool = True,
) -> PurchaseTomanSubscriptionResult:
    account = await get_or_create_billing_account(db, user)
    existing = await _existing_ledger(db, idempotency_key)
    if existing is not None:
        return PurchaseTomanSubscriptionResult(ok=True, account=account, ledger_entries=[existing], reason="idempotent")
    active_subscription = (
        await db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
                UserSubscription.expires_at > utcnow(),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if active_subscription is not None:
        return PurchaseTomanSubscriptionResult(
            ok=False,
            account=account,
            subscription=active_subscription,
            reason="active_subscription_exists",
        )

    config = await get_or_create_subscription_config(db)
    payment_toman = _plan_price_toman(plan, config)
    gift_toman = _plan_gift_toman(plan, config)
    available_paid = int(account.paid_balance_toman or 0)
    requested_wallet_payment = payment_toman if wallet_payment_toman is None and not payment_confirmed else _positive_int(wallet_payment_toman)
    wallet_payment = min(payment_toman, requested_wallet_payment)
    external_payment = payment_toman - wallet_payment
    if wallet_payment > available_paid:
        return PurchaseTomanSubscriptionResult(
            ok=False,
            account=account,
            payment_toman=payment_toman,
            gift_credit_toman=gift_toman,
            wallet_payment_toman=wallet_payment,
            external_payment_toman=external_payment,
            reason="insufficient_paid_toman_credit",
        )
    if not payment_confirmed and external_payment > 0:
        return PurchaseTomanSubscriptionResult(
            ok=False,
            account=account,
            payment_toman=payment_toman,
            gift_credit_toman=gift_toman,
            wallet_payment_toman=wallet_payment,
            external_payment_toman=external_payment,
            reason="insufficient_paid_toman_credit",
        )

    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status="active",
        expires_at=utcnow() + timedelta(days=30),
    )
    db.add(subscription)
    await db.flush()
    try:
        await assign_subscription_pool(db, subscription)
    except CodexCapacityError as exc:
        await db.delete(subscription)
        await db.flush()
        return PurchaseTomanSubscriptionResult(
            ok=False,
            account=account,
            subscription=subscription,
            payment_toman=payment_toman,
            gift_credit_toman=gift_toman,
            wallet_payment_toman=wallet_payment,
            external_payment_toman=external_payment,
            reason=exc.code,
        )

    paid_delta = 0
    if wallet_payment > 0:
        account.paid_balance_toman = int(account.paid_balance_toman or 0) - wallet_payment
        account.total_paid_spent_toman = int(account.total_paid_spent_toman or 0) + wallet_payment
        paid_delta = -wallet_payment
    gift_delta = gift_toman if grant_gift_toman_balance else 0
    account.gift_balance_toman = int(account.gift_balance_toman or 0) + gift_delta
    account.total_gift_granted_toman = int(account.total_gift_granted_toman or 0) + gift_toman
    account.total_subscription_paid_toman = int(account.total_subscription_paid_toman or 0) + payment_toman
    account.version = int(account.version or 0) + 1
    payment_entry = _new_ledger_entry(
        user=user,
        account=account,
        amount_toman=payment_toman,
        gift_delta_toman=0,
        paid_delta_toman=paid_delta,
        entry_type="subscription_payment",
        reason=f"Purchased {plan.name}",
        idempotency_key=f"{idempotency_key}:payment" if idempotency_key else None,
        metadata={
            "plan_id": plan.id,
            "subscription_id": subscription.id,
            "payment_confirmed": payment_confirmed,
            "wallet_payment_toman": wallet_payment,
            "external_payment_toman": external_payment,
        },
    )
    gift_entry = _new_ledger_entry(
        user=user,
        account=account,
        amount_toman=gift_toman,
        gift_delta_toman=gift_delta,
        paid_delta_toman=0,
        entry_type="subscription_gift_credit",
        reason=f"Gift credit for {plan.name}",
        idempotency_key=idempotency_key,
        metadata={
            "plan_id": plan.id,
            "subscription_id": subscription.id,
            "payment_toman": payment_toman,
            "grant_gift_toman_balance": grant_gift_toman_balance,
        },
    )
    db.add_all([payment_entry, gift_entry])
    if commit:
        await db.commit()
        await db.refresh(account)
        await db.refresh(subscription)
        await db.refresh(gift_entry)
    else:
        await db.flush()
    return PurchaseTomanSubscriptionResult(
        ok=True,
        account=account,
        subscription=subscription,
        payment_toman=payment_toman,
        gift_credit_toman=gift_toman,
        wallet_payment_toman=wallet_payment,
        external_payment_toman=external_payment,
        ledger_entries=[payment_entry, gift_entry],
    )


async def quote_toman_topup_payment(
    db: AsyncSession,
    *,
    user: UserPreference,
    credit_amount_toman: int,
) -> TopupQuote:
    account = await get_or_create_billing_account(db, user)
    config = await get_or_create_subscription_config(db)
    credit_amount = _positive_int(credit_amount_toman)
    markup_percent = _positive_float(config.api_markup_percent, DEFAULT_API_MARKUP_PERCENT)
    normal_payment = _round_toman(Decimal(credit_amount) * (Decimal("1") + Decimal(str(markup_percent)) / Decimal("100")))
    active_subscription_id = (
        await db.execute(
            select(UserSubscription.id).where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
                UserSubscription.expires_at > utcnow(),
            ).limit(1)
        )
    ).scalar_one_or_none()
    has_subscription_payment = int(account.total_subscription_paid_toman or 0) > 0 or active_subscription_id is not None
    discount_percent = _positive_float(config.first_topup_discount_percent, DEFAULT_FIRST_TOPUP_DISCOUNT_PERCENT)
    cap = _positive_int(config.first_topup_discount_cap_toman, DEFAULT_FIRST_TOPUP_DISCOUNT_CAP_TOMAN)
    discounted_credit = min(credit_amount, cap) if has_subscription_payment and not account.first_topup_discount_used else 0
    discount = _round_toman(
        Decimal(discounted_credit)
        * (Decimal("1") + Decimal(str(markup_percent)) / Decimal("100"))
        * Decimal(str(discount_percent))
        / Decimal("100")
    )
    return TopupQuote(
        credit_amount_toman=credit_amount,
        normal_payment_toman=normal_payment,
        payment_due_toman=max(0, normal_payment - discount),
        discount_toman=discount,
        discount_applied=discount > 0,
        discounted_credit_toman=discounted_credit,
        markup_percent=markup_percent,
        discount_percent=discount_percent,
    )


async def apply_toman_topup(
    db: AsyncSession,
    *,
    user: UserPreference,
    credit_amount_toman: int,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
) -> TopupResult:
    account = await get_or_create_billing_account(db, user)
    existing = await _existing_ledger(db, idempotency_key)
    quote = await quote_toman_topup_payment(db, user=user, credit_amount_toman=credit_amount_toman)
    if existing is not None:
        return TopupResult(ok=True, account=account, quote=quote, ledger_entry=existing, reason="idempotent")
    if quote.credit_amount_toman <= 0:
        return TopupResult(ok=False, account=account, quote=quote, reason="invalid_topup_amount")

    account.paid_balance_toman = int(account.paid_balance_toman or 0) + quote.credit_amount_toman
    account.total_paid_topup_toman = int(account.total_paid_topup_toman or 0) + quote.credit_amount_toman
    if quote.discount_applied:
        account.first_topup_discount_used = True
    account.version = int(account.version or 0) + 1
    entry_metadata = {
        "payment_due_toman": quote.payment_due_toman,
        "normal_payment_toman": quote.normal_payment_toman,
        "discount_toman": quote.discount_toman,
        "discounted_credit_toman": quote.discounted_credit_toman,
        **(metadata or {}),
    }
    entry = _new_ledger_entry(
        user=user,
        account=account,
        amount_toman=quote.credit_amount_toman,
        gift_delta_toman=0,
        paid_delta_toman=quote.credit_amount_toman,
        entry_type="paid_topup_credit",
        reason="wallet topup",
        idempotency_key=idempotency_key,
        metadata=entry_metadata,
    )
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(account)
        await db.refresh(entry)
    else:
        await db.flush()
    return TopupResult(ok=True, account=account, quote=quote, ledger_entry=entry)


async def mark_first_topup_discount_used(
    db: AsyncSession,
    *,
    user: UserPreference,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
) -> TomanLedgerEntry | None:
    account = await get_or_create_billing_account(db, user)
    if account.first_topup_discount_used:
        return None
    existing = await _existing_ledger(db, idempotency_key)
    if existing is not None:
        account.first_topup_discount_used = True
        if commit:
            await db.commit()
            await db.refresh(account)
        else:
            await db.flush()
        return existing
    account.first_topup_discount_used = True
    account.version = int(account.version or 0) + 1
    entry = _new_ledger_entry(
        user=user,
        account=account,
        amount_toman=0,
        gift_delta_toman=0,
        paid_delta_toman=0,
        entry_type="first_topup_discount_used",
        reason="first topup discount used on USD wallet topup",
        idempotency_key=idempotency_key,
        metadata=metadata,
    )
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(account)
        await db.refresh(entry)
    else:
        await db.flush()
    return entry


async def quote_chat_usage_toman(
    db: AsyncSession,
    *,
    model: Model,
    input_tokens: int,
    output_tokens: int,
) -> ChatUsageQuote:
    config = await get_or_create_subscription_config(db)
    input_count = _positive_int(input_tokens)
    output_count = _positive_int(output_tokens)
    price_in = _positive_float(getattr(model, "pricing_input", 0.0))
    price_out = _positive_float(getattr(model, "pricing_output", 0.0))
    global_cost = (Decimal(input_count) / Decimal(1_000_000) * Decimal(str(price_in))) + (
        Decimal(output_count) / Decimal(1_000_000) * Decimal(str(price_out))
    )
    rate = _positive_int(config.usd_to_toman_rate, DEFAULT_USD_TO_TOMAN_RATE)
    markup_percent = _positive_float(config.api_markup_percent, DEFAULT_API_MARKUP_PERCENT)
    base_toman = _round_toman(global_cost * Decimal(rate))
    billable = _round_toman(Decimal(base_toman) * (Decimal("1") + Decimal(str(markup_percent)) / Decimal("100")))
    return ChatUsageQuote(
        global_api_cost_usd=float(global_cost),
        base_cost_toman=base_toman,
        billable_cost_toman=billable,
        usd_to_toman_rate=rate,
        markup_percent=markup_percent,
        pricing_snapshot={
            "model_id": getattr(model, "id", None),
            "model_name": getattr(model, "name", None),
            "pricing_input_usd_per_1m": price_in,
            "pricing_output_usd_per_1m": price_out,
        },
    )


async def check_chat_usage_permission_toman(
    db: AsyncSession,
    *,
    user: UserPreference,
    model: Model,
    input_tokens: int,
    output_tokens: int,
) -> ChatUsageChargeResult:
    """Checks if the user has enough credit (sub or balance) to perform the operation."""
    account = await get_or_create_billing_account(db, user)
    quote = await quote_chat_usage_toman(db, model=model, input_tokens=input_tokens, output_tokens=output_tokens)
    
    if quote.billable_cost_toman <= 0:
        return ChatUsageChargeResult(ok=True, account=account)

    from sqlalchemy.orm import selectinload
    now = utcnow()
    sub_query = select(UserSubscription).options(selectinload(UserSubscription.plan)).where(
        UserSubscription.user_id == user.id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now
    )
    user_sub = (await db.execute(sub_query)).scalars().first()

    if user_sub and user_sub.plan.plan_type == "tiered_cooldown":
        plan = user_sub.plan
        
        # Weekly reset
        if not user_sub.week_resets_at or now >= user_sub.week_resets_at:
            user_sub.weekly_spent_toman = 0
            user_sub.week_resets_at = now + timedelta(days=7)
            
        # Cooldown reset
        if user_sub.cooldown_ends_at and now >= user_sub.cooldown_ends_at:
            user_sub.cooldown_spent_toman = 0
            user_sub.cooldown_ends_at = None

        in_cooldown = (
            user_sub.cooldown_ends_at and 
            now < user_sub.cooldown_ends_at and 
            (user_sub.cooldown_spent_toman or 0) >= plan.cooldown_limit_toman
        )
        weekly_limit_hit = plan.weekly_limit_toman > 0 and (user_sub.weekly_spent_toman or 0) >= plan.weekly_limit_toman
        
        if in_cooldown:
            available = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
            if available >= quote.billable_cost_toman:
                return ChatUsageChargeResult(
                    ok=True,
                    account=account,
                    billable_cost_toman=quote.billable_cost_toman,
                    reason="cooldown_payg_available",
                    user_sub=user_sub
                )
            return ChatUsageChargeResult(
                ok=False,
                account=account,
                billable_cost_toman=quote.billable_cost_toman,
                reason="cooldown_limit_reached",
                user_sub=user_sub
            )
        
        if weekly_limit_hit:
            available = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
            if available >= quote.billable_cost_toman:
                return ChatUsageChargeResult(
                    ok=True,
                    account=account,
                    billable_cost_toman=quote.billable_cost_toman,
                    reason="weekly_limit_payg_available",
                    user_sub=user_sub
                )
            return ChatUsageChargeResult(
                ok=False,
                account=account,
                billable_cost_toman=quote.billable_cost_toman,
                reason="weekly_limit_reached",
                user_sub=user_sub
            )
        
        return ChatUsageChargeResult(ok=True, account=account, user_sub=user_sub, reason="tiered_subscription")

    available = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
    if available >= quote.billable_cost_toman:
        return ChatUsageChargeResult(ok=True, account=account)

    return ChatUsageChargeResult(
        ok=False,
        account=account,
        billable_cost_toman=quote.billable_cost_toman,
        reason="insufficient_toman_credit",
        user_sub=user_sub
    )


async def charge_chat_usage_toman(
    db: AsyncSession,
    *,
    user: UserPreference,
    model: Model,
    input_tokens: int,
    output_tokens: int,
    usage_event_id: int | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
) -> ChatUsageChargeResult:
    account = await get_or_create_billing_account(db, user)
    existing = await _existing_ledger(db, idempotency_key)
    quote = await quote_chat_usage_toman(db, model=model, input_tokens=input_tokens, output_tokens=output_tokens)
    if existing is not None:
        return ChatUsageChargeResult(ok=True, account=account, ledger_entry=existing, reason="idempotent")
    if quote.billable_cost_toman <= 0:
        return ChatUsageChargeResult(ok=True, account=account, metadata={**quote.pricing_snapshot})

    from sqlalchemy.orm import selectinload
    now = utcnow()
    sub_query = select(UserSubscription).options(selectinload(UserSubscription.plan)).where(
        UserSubscription.user_id == user.id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now
    )
    user_sub = (await db.execute(sub_query)).scalars().first()

    if user_sub and user_sub.plan.plan_type == "tiered_cooldown":
        plan = user_sub.plan
        
        # Weekly reset
        if not user_sub.week_resets_at or now >= user_sub.week_resets_at:
            user_sub.weekly_spent_toman = 0
            user_sub.week_resets_at = now + timedelta(days=7)
            
        # Weekly limit check
        can_use_tiered = True
        if plan.weekly_limit_toman > 0 and (user_sub.weekly_spent_toman or 0) >= plan.weekly_limit_toman:
            can_use_tiered = False
            
        in_cooldown = (
            user_sub.cooldown_ends_at and 
            now < user_sub.cooldown_ends_at and 
            (user_sub.cooldown_spent_toman or 0) >= plan.cooldown_limit_toman
        )
        if can_use_tiered and not in_cooldown:
            if user_sub.cooldown_ends_at and now >= user_sub.cooldown_ends_at:
                user_sub.cooldown_spent_toman = 0
                user_sub.cooldown_ends_at = None
                
            # If window not started and we have cooldown hours, start it now
            if user_sub.cooldown_ends_at is None and plan.cooldown_hours > 0:
                user_sub.cooldown_ends_at = now + timedelta(hours=plan.cooldown_hours)
                user_sub.cooldown_spent_toman = 0

            cost = quote.billable_cost_toman
            user_sub.cooldown_spent_toman = (user_sub.cooldown_spent_toman or 0) + cost
            user_sub.weekly_spent_toman = (user_sub.weekly_spent_toman or 0) + cost
            
            if commit:
                await db.commit()
                await db.refresh(user_sub)
                
            return ChatUsageChargeResult(
                ok=True, 
                account=account, 
                metadata={"tiered_covered": True, "cost": cost, "reason": "tiered_subscription", **quote.pricing_snapshot},
                user_sub=user_sub
            )

    available = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
    if available < quote.billable_cost_toman:
        reason = "insufficient_toman_credit"
        if user_sub and user_sub.plan.plan_type == "tiered_cooldown":
            if user_sub.cooldown_ends_at and now < user_sub.cooldown_ends_at:
                reason = "cooldown_limit_reached"
            elif plan.weekly_limit_toman > 0 and (user_sub.weekly_spent_toman or 0) >= plan.weekly_limit_toman:
                reason = "weekly_limit_reached"
                
        return ChatUsageChargeResult(
            ok=False,
            account=account,
            global_api_cost_usd=quote.global_api_cost_usd,
            base_cost_toman=quote.base_cost_toman,
            billable_cost_toman=quote.billable_cost_toman,
            reason=reason,
            user_sub=user_sub
        )

    gift_spent = min(int(account.gift_balance_toman or 0), quote.billable_cost_toman)
    paid_spent = quote.billable_cost_toman - gift_spent
    account.gift_balance_toman = int(account.gift_balance_toman or 0) - gift_spent
    account.paid_balance_toman = int(account.paid_balance_toman or 0) - paid_spent
    account.total_gift_spent_toman = int(account.total_gift_spent_toman or 0) + gift_spent
    account.total_paid_spent_toman = int(account.total_paid_spent_toman or 0) + paid_spent
    account.version = int(account.version or 0) + 1
    entry_metadata = {
        "global_api_cost_usd": quote.global_api_cost_usd,
        "base_cost_toman": quote.base_cost_toman,
        "billable_cost_toman": quote.billable_cost_toman,
        "gift_spent_toman": gift_spent,
        "paid_spent_toman": paid_spent,
        "usd_to_toman_rate": quote.usd_to_toman_rate,
        "api_markup_percent": quote.markup_percent,
        "pricing_snapshot": quote.pricing_snapshot,
        **(metadata or {}),
    }
    entry = _new_ledger_entry(
        user=user,
        account=account,
        amount_toman=-quote.billable_cost_toman,
        gift_delta_toman=-gift_spent,
        paid_delta_toman=-paid_spent,
        entry_type="chat_completion_usage",
        reason="chat completion usage",
        usage_event_id=usage_event_id,
        idempotency_key=idempotency_key,
        metadata=entry_metadata,
    )
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(account)
        await db.refresh(entry)
    else:
        await db.flush()
    return ChatUsageChargeResult(
        ok=True,
        account=account,
        global_api_cost_usd=quote.global_api_cost_usd,
        base_cost_toman=quote.base_cost_toman,
        billable_cost_toman=quote.billable_cost_toman,
        gift_spent_toman=gift_spent,
        paid_spent_toman=paid_spent,
        ledger_entry=entry,
        metadata=entry_metadata,
        user_sub=user_sub
    )



async def usd_to_toman(db: AsyncSession, amount_usd: float) -> int:
    config = await get_or_create_subscription_config(db)
    rate = _positive_int(config.usd_to_toman_rate, DEFAULT_USD_TO_TOMAN_RATE)
    return _round_toman(Decimal(str(amount_usd or 0)) * Decimal(rate))


@dataclass
class GenericUsageChargeResult:
    ok: bool
    account: UserBillingAccount
    cost_toman: int = 0
    gift_spent_toman: int = 0
    paid_spent_toman: int = 0
    ledger_entry: TomanLedgerEntry | None = None
    reason: str | None = None


async def charge_generic_usage_toman(
    db: AsyncSession,
    *,
    user: UserPreference,
    cost_usd: float,
    entry_type: str,
    reason: str,
    usage_event_id: int | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
) -> GenericUsageChargeResult:
    account = await get_or_create_billing_account(db, user)
    existing = await _existing_ledger(db, idempotency_key)
    if existing is not None:
        return GenericUsageChargeResult(ok=True, account=account, ledger_entry=existing, reason="idempotent")

    cost_toman = await usd_to_toman(db, cost_usd)
    if cost_toman <= 0:
        return GenericUsageChargeResult(ok=True, account=account, cost_toman=0, reason="zero_cost")

    available = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
    if available < cost_toman:
        return GenericUsageChargeResult(
            ok=False,
            account=account,
            cost_toman=cost_toman,
            reason="insufficient_toman_credit",
        )

    gift_spent = min(int(account.gift_balance_toman or 0), cost_toman)
    paid_spent = cost_toman - gift_spent
    account.gift_balance_toman = int(account.gift_balance_toman or 0) - gift_spent
    account.paid_balance_toman = int(account.paid_balance_toman or 0) - paid_spent
    account.total_gift_spent_toman = int(account.total_gift_spent_toman or 0) + gift_spent
    account.total_paid_spent_toman = int(account.total_paid_spent_toman or 0) + paid_spent
    account.version = int(account.version or 0) + 1

    entry_metadata = {
        "cost_usd": float(cost_usd or 0.0),
        "cost_toman": cost_toman,
        "gift_spent_toman": gift_spent,
        "paid_spent_toman": paid_spent,
        **(metadata or {}),
    }
    entry = _new_ledger_entry(
        user=user,
        account=account,
        amount_toman=-cost_toman,
        gift_delta_toman=-gift_spent,
        paid_delta_toman=-paid_spent,
        entry_type=entry_type,
        reason=reason,
        usage_event_id=usage_event_id,
        idempotency_key=idempotency_key,
        metadata=entry_metadata,
    )
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(account)
        await db.refresh(entry)
    else:
        await db.flush()
    return GenericUsageChargeResult(
        ok=True,
        account=account,
        cost_toman=cost_toman,
        gift_spent_toman=gift_spent,
        paid_spent_toman=paid_spent,
        ledger_entry=entry,
    )
