from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import (
    Model,
    SubscriptionPlan,
    TomanLedgerEntry,
    UserBillingAccount,
    UserPreference,
    UserSubscription,
)
from app.schemas import (
    UserBillingAccountOut,
    UserSubscriptionPurchaseRequest,
    UserSubscriptionStatusOut,
    UserTopupApplyRequest,
    UserTrialClaimOut,
    UserUsagePermissionOut,
)
from app.services.account_service import get_user_by_telegram_id, create_or_restore_user
from app.services.toman_billing_service import (
    apply_toman_topup,
    check_chat_usage_permission_toman,
    get_or_create_billing_account,
    get_or_create_subscription_config,
    purchase_toman_subscription,
    quote_toman_topup_payment,
    utcnow,
)
from app.services.trial_service import TrialService

router = APIRouter(prefix="/api/user", tags=["User Subscription"])


async def _resolve_user(db: AsyncSession, telegram_user_id: int) -> UserPreference:
    user = await get_user_by_telegram_id(db, telegram_user_id)
    if not user:
        user = await create_or_restore_user(db, telegram_user_id=telegram_user_id, commit=True)
    return user


def _billing_account_out(account: UserBillingAccount) -> UserBillingAccountOut:
    return UserBillingAccountOut(
        user_id=account.user_id,
        gift_balance_toman=int(account.gift_balance_toman or 0),
        paid_balance_toman=int(account.paid_balance_toman or 0),
        total_balance_toman=int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0),
        total_gift_granted_toman=int(account.total_gift_granted_toman or 0),
        total_gift_spent_toman=int(account.total_gift_spent_toman or 0),
        total_paid_topup_toman=int(account.total_paid_topup_toman or 0),
        total_paid_spent_toman=int(account.total_paid_spent_toman or 0),
        total_subscription_paid_toman=int(account.total_subscription_paid_toman or 0),
        first_topup_discount_used=bool(account.first_topup_discount_used),
    )


def _subscription_status_out(sub: UserSubscription, now: datetime) -> UserSubscriptionStatusOut:
    plan = getattr(sub, "plan", None)
    expires = sub.expires_at
    if expires and expires.tzinfo is not None:
        expires = expires.astimezone(timezone.utc).replace(tzinfo=None)
    is_active = sub.status == "active" and expires and expires > now

    cooldown_ends = sub.cooldown_ends_at
    if cooldown_ends and cooldown_ends.tzinfo is not None:
        cooldown_ends = cooldown_ends.astimezone(timezone.utc).replace(tzinfo=None)
    in_cooldown = cooldown_ends is not None and now < cooldown_ends
    cooldown_remaining = None
    if in_cooldown:
        cooldown_remaining = int((cooldown_ends - now).total_seconds())

    week_resets = sub.week_resets_at
    if week_resets and week_resets.tzinfo is not None:
        week_resets = week_resets.astimezone(timezone.utc).replace(tzinfo=None)

    return UserSubscriptionStatusOut(
        id=sub.id,
        plan_id=sub.plan_id,
        plan_name=plan.name if plan else None,
        plan_type=plan.plan_type if plan else None,
        status=sub.status,
        purchased_at=sub.purchased_at,
        expires_at=sub.expires_at,
        is_active_now=is_active,
        cooldown_spent_toman=int(sub.cooldown_spent_toman or 0),
        cooldown_limit_toman=int(plan.cooldown_limit_toman or 0) if plan else 0,
        cooldown_hours=int(plan.cooldown_hours or 0) if plan else 0,
        cooldown_ends_at=sub.cooldown_ends_at,
        is_in_cooldown=in_cooldown,
        cooldown_remaining_seconds=cooldown_remaining,
        weekly_spent_toman=int(sub.weekly_spent_toman or 0),
        weekly_limit_toman=int(plan.weekly_limit_toman or 0) if plan else 0,
        week_resets_at=sub.week_resets_at,
    )


@router.get("/subscription/plans", response_model=list[dict])
async def list_active_plans(db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.is_active == True)
    )
    plans = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "plan_type": p.plan_type,
            "monthly_price_toman": p.monthly_price_toman,
            "gift_credit_toman": p.gift_credit_toman,
            "cooldown_limit_toman": p.cooldown_limit_toman,
            "cooldown_hours": p.cooldown_hours,
            "weekly_limit_toman": p.weekly_limit_toman,
            "is_agentic": p.is_agentic,
        }
        for p in plans
    ]


@router.get("/billing-account", response_model=UserBillingAccountOut)
async def get_billing_account(
    telegram_user_id: int,
    db: AsyncSession = Depends(get_session),
):
    user = await _resolve_user(db, telegram_user_id)
    account = await get_or_create_billing_account(db, user)
    await db.commit()
    await db.refresh(account)
    return _billing_account_out(account)


@router.get("/subscription", response_model=Optional[UserSubscriptionStatusOut])
async def get_user_subscription(
    telegram_user_id: int,
    db: AsyncSession = Depends(get_session),
):
    user = await _resolve_user(db, telegram_user_id)
    now = utcnow()
    sub = (
        await db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
            )
            .order_by(UserSubscription.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not sub:
        return None

    return _subscription_status_out(sub, now)


@router.post("/subscription/purchase", response_model=dict)
async def purchase_subscription(
    data: UserSubscriptionPurchaseRequest,
    telegram_user_id: int,
    db: AsyncSession = Depends(get_session),
):
    user = await _resolve_user(db, telegram_user_id)

    plan = await db.get(SubscriptionPlan, data.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(400, "Plan not found or inactive")

    result = await purchase_toman_subscription(
        db,
        user=user,
        plan=plan,
        idempotency_key=f"web-sub:{user.id}:{data.plan_id}:{datetime.now(timezone.utc).date().isoformat()}",
        payment_confirmed=True,
    )

    if not result.ok:
        reasons = {
            "active_subscription_exists": "شما قبلاً یک اشتراک فعال دارید",
            "insufficient_paid_toman_credit": "موجودی کیف پول کافی نیست",
            "pool_capacity_full": "ظرفیت این پلن تکمیل شده",
        }
        raise HTTPException(400, reasons.get(result.reason, result.reason or "purchase_failed"))

    return {
        "ok": True,
        "subscription_id": result.subscription.id,
        "plan_name": plan.name,
        "expires_at": result.subscription.expires_at,
        "gift_credit_toman": result.gift_credit_toman,
    }


@router.get("/topup/quote", response_model=dict)
async def get_topup_quote(
    telegram_user_id: int,
    amount_toman: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_session),
):
    user = await _resolve_user(db, telegram_user_id)
    quote = await quote_toman_topup_payment(db, user=user, credit_amount_toman=amount_toman)
    return {
        "credit_amount_toman": quote.credit_amount_toman,
        "normal_payment_toman": quote.normal_payment_toman,
        "payment_due_toman": quote.payment_due_toman,
        "discount_toman": quote.discount_toman,
        "discount_applied": quote.discount_applied,
        "markup_percent": quote.markup_percent,
        "discount_percent": quote.discount_percent,
    }


@router.post("/topup/apply", response_model=dict)
async def apply_topup(
    data: UserTopupApplyRequest,
    telegram_user_id: int,
    db: AsyncSession = Depends(get_session),
):
    user = await _resolve_user(db, telegram_user_id)

    if data.credit_amount_toman <= 0:
        raise HTTPException(400, "Invalid topup amount")

    result = await apply_toman_topup(
        db,
        user=user,
        credit_amount_toman=data.credit_amount_toman,
        metadata={"source": "web"},
    )

    if not result.ok:
        raise HTTPException(400, result.reason or "topup_failed")

    return {
        "ok": True,
        "credit_added_toman": result.quote.credit_amount_toman,
        "new_balance_toman": int(result.account.gift_balance_toman or 0) + int(result.account.paid_balance_toman or 0),
    }


@router.get("/ledger", response_model=list[dict])
async def get_ledger(
    telegram_user_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
):
    user = await _resolve_user(db, telegram_user_id)
    account = await get_or_create_billing_account(db, user)

    result = await db.execute(
        select(TomanLedgerEntry)
        .where(TomanLedgerEntry.billing_account_id == account.id)
        .order_by(TomanLedgerEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "amount_toman": e.amount_toman,
            "gift_delta_toman": e.gift_delta_toman,
            "paid_delta_toman": e.paid_delta_toman,
            "gift_balance_after_toman": e.gift_balance_after_toman,
            "paid_balance_after_toman": e.paid_balance_after_toman,
            "entry_type": e.entry_type,
            "reason": e.reason,
            "created_at": e.created_at,
        }
        for e in entries
    ]


@router.post("/usage-permission", response_model=UserUsagePermissionOut)
async def check_usage_permission(
    telegram_user_id: int,
    model_id: Optional[int] = None,
    input_tokens: int = 0,
    output_tokens: int = 1000,
    db: AsyncSession = Depends(get_session),
):
    user = await _resolve_user(db, telegram_user_id)
    account = await get_or_create_billing_account(db, user)
    now = utcnow()

    sub = None
    if model_id:
        model = await db.get(Model, model_id)
        if model:
            result = await check_chat_usage_permission_toman(
                db, user=user, model=model, input_tokens=input_tokens, output_tokens=output_tokens
            )

            sub_query = select(UserSubscription).options(selectinload(UserSubscription.plan)).where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
                UserSubscription.expires_at > now,
            )
            sub = (await db.execute(sub_query)).scalars().first()

            if result.ok:
                return UserUsagePermissionOut(
                    can_chat=True,
                    billing_account=_billing_account_out(account),
                    subscription=_subscription_status_out(sub, now) if sub else None,
                    billable_cost_toman=result.billable_cost_toman,
                )
            else:
                cooldown_remaining = None
                if sub and sub.cooldown_ends_at:
                    ce = sub.cooldown_ends_at
                    if ce.tzinfo is not None:
                        ce = ce.astimezone(timezone.utc).replace(tzinfo=None)
                    if now < ce:
                        cooldown_remaining = int((ce - now).total_seconds())

                return UserUsagePermissionOut(
                    can_chat=False,
                    reason=result.reason,
                    billing_account=_billing_account_out(account),
                    subscription=_subscription_status_out(sub, now) if sub else None,
                    billable_cost_toman=result.billable_cost_toman,
                    cooldown_remaining_seconds=cooldown_remaining,
                )

    available = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
    sub_query = select(UserSubscription).options(selectinload(UserSubscription.plan)).where(
        UserSubscription.user_id == user.id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now,
    )
    sub = (await db.execute(sub_query)).scalars().first()

    return UserUsagePermissionOut(
        can_chat=available > 0 or sub is not None,
        billing_account=_billing_account_out(account),
        subscription=_subscription_status_out(sub, now) if sub else None,
    )


@router.post("/trial/claim", response_model=UserTrialClaimOut)
async def claim_trial(
    telegram_user_id: int,
    db: AsyncSession = Depends(get_session),
):
    user = await _resolve_user(db, telegram_user_id)

    if user.trial_used:
        return UserTrialClaimOut(ok=False, reason="trial_already_used")

    service = TrialService()
    result = await service.grant_trial_subscription(db, user)

    if not result:
        return UserTrialClaimOut(ok=False, reason="trial_not_available")

    return UserTrialClaimOut(
        ok=True,
        subscription_id=result.id,
        expires_at=result.expires_at,
    )
