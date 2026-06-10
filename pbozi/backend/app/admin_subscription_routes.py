from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .database import get_session
from .models import SubscriptionPlan, SubscriptionPlanRule, SubscriptionConfig, UserSubscription
from .schemas import (
    AdminUserSubscriptionOut,
    SubscriptionPlanCreate, 
    SubscriptionPlanOut, 
    SubscriptionPlanUpdate,
    SubscriptionPlanRuleCreate, 
    SubscriptionPlanRuleOut,
    SubscriptionConfigOut,
    SubscriptionConfigUpdate
)
from app.services.toman_billing_service import get_or_create_subscription_config
from app.services.codex_capacity_service import recalculate_pool_active_users
from app.services.notification_service import send_telegram_notification

router = APIRouter(prefix="/api/admin/subscriptions", tags=["Admin Subscriptions"])

async def _get_or_create_config(db: AsyncSession) -> SubscriptionConfig:
    config = await get_or_create_subscription_config(db)
    await db.commit()
    await db.refresh(config)
    return config

@router.get("/config", response_model=SubscriptionConfigOut)
async def get_config(db: AsyncSession = Depends(get_session)):
    return await _get_or_create_config(db)

@router.patch("/config", response_model=SubscriptionConfigOut)
async def update_config(data: SubscriptionConfigUpdate, db: AsyncSession = Depends(get_session)):
    config = await _get_or_create_config(db)
    payload = data.model_dump(exclude_unset=True)
    if "is_enabled" in payload and payload["is_enabled"] is not None:
        config.is_enabled = bool(payload["is_enabled"])
    int_fields = {
        "monthly_price_toman",
        "gift_credit_toman",
        "first_topup_discount_cap_toman",
        "usd_to_toman_rate",
    }
    percent_fields = {"api_markup_percent", "first_topup_discount_percent"}
    for field in int_fields:
        if field in payload:
            value = int(payload[field] or 0)
            if value < 0:
                raise HTTPException(400, f"{field} must be zero or greater")
            setattr(config, field, value)
    for field in percent_fields:
        if field in payload:
            value = float(payload[field] or 0.0)
            if value < 0:
                raise HTTPException(400, f"{field} must be zero or greater")
            setattr(config, field, value)
    await db.commit()
    await db.refresh(config)
    return config

@router.get("/plans", response_model=list[SubscriptionPlanOut])

async def list_plans(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(SubscriptionPlan))
    return list(result.scalars().all())


async def _subscription_out(subscription: UserSubscription, db: AsyncSession) -> AdminUserSubscriptionOut:
    user = subscription.user
    plan = subscription.plan
    
    # Force naive UTC
    def _to_naive(dt: datetime) -> datetime:
        if dt is None: return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at_naive = _to_naive(subscription.expires_at)
    
    gift_toman = 0
    paid_toman = 0
    if user:
        from app.models import UserBillingAccount
        account = (
            await db.execute(select(UserBillingAccount).where(UserBillingAccount.user_id == user.id))
        ).scalar_one_or_none()
        if account:
            gift_toman = int(account.gift_balance_toman or 0)
            paid_toman = int(account.paid_balance_toman or 0)
            
    is_active_now = False
    if subscription.status == "active" and expires_at_naive is not None:
        is_active_now = expires_at_naive > now_naive
        
    return AdminUserSubscriptionOut(
        id=subscription.id,
        user_id=subscription.user_id,
        telegram_user_id=user.telegram_user_id if user else None,
        first_name=user.first_name if user else None,
        username=user.username if user else None,
        phone_number=user.phone_number if user else None,
        gift_balance_toman=gift_toman,
        paid_balance_toman=paid_toman,
        total_balance_toman=gift_toman + paid_toman,
        plan_id=subscription.plan_id,
        plan_name=plan.name if plan else None,
        pool_id=subscription.pool_id,
        pool_name=subscription.pool.name if getattr(subscription, "pool", None) else None,
        status=subscription.status,
        purchased_at=subscription.purchased_at,
        expires_at=subscription.expires_at,
        is_active_now=is_active_now,
    )


@router.get("/user-subscriptions", response_model=list[AdminUserSubscriptionOut])
async def list_user_subscriptions(
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    query = (
        select(UserSubscription)
        .options(selectinload(UserSubscription.user), selectinload(UserSubscription.plan), selectinload(UserSubscription.pool))
        .order_by(UserSubscription.purchased_at.desc(), UserSubscription.id.desc())
    )
    if status and status != "all":
        query = query.where(UserSubscription.status == status)
    result = await db.execute(query)
    return [await _subscription_out(subscription, db) for subscription in result.scalars().all()]


@router.post("/user-subscriptions/{subscription_id}/cancel", response_model=AdminUserSubscriptionOut)
async def cancel_user_subscription(subscription_id: int, db: AsyncSession = Depends(get_session)):
    subscription = (
        await db.execute(
        select(UserSubscription)
            .options(selectinload(UserSubscription.user), selectinload(UserSubscription.plan), selectinload(UserSubscription.pool))
            .where(UserSubscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    if not subscription:
        raise HTTPException(404, "Subscription not found")
    subscription.status = "cancelled"
    pool_id = subscription.pool_id
    if pool_id is not None:
        await recalculate_pool_active_users(db, pool_id)
    await db.commit()
    await db.refresh(subscription)

    # Notify user
    if subscription.user and subscription.user.telegram_user_id:
        plan_name = subscription.plan.name if subscription.plan else "اشتراک"
        msg = f"✅ اشتراک {plan_name} شما توسط مدیریت فعال شد." if subscription.status == "active" else f"❌ اشتراک {plan_name} شما توسط مدیریت لغو شد."
        await send_telegram_notification(subscription.user.telegram_user_id, msg)

    subscription = (
        await db.execute(
        select(UserSubscription)
            .options(selectinload(UserSubscription.user), selectinload(UserSubscription.plan), selectinload(UserSubscription.pool))
            .where(UserSubscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    return await _subscription_out(subscription, db)


@router.post("/user-subscriptions/{subscription_id}/reactivate", response_model=AdminUserSubscriptionOut)
async def reactivate_user_subscription(subscription_id: int, db: AsyncSession = Depends(get_session)):
    subscription = (
        await db.execute(
        select(UserSubscription)
            .options(selectinload(UserSubscription.user), selectinload(UserSubscription.plan), selectinload(UserSubscription.pool))
            .where(UserSubscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    if not subscription:
        raise HTTPException(404, "Subscription not found")
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at_naive = subscription.expires_at
    if expires_at_naive.tzinfo is not None:
        expires_at_naive = expires_at_naive.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        expires_at_naive = expires_at_naive.replace(tzinfo=None)
    subscription.status = "active"
    if expires_at_naive <= now_naive:
        subscription.expires_at = now_naive + timedelta(days=30)
    pool_id = subscription.pool_id
    if pool_id is not None:
        await recalculate_pool_active_users(db, pool_id)
    await db.commit()
    await db.refresh(subscription)

    # Notify user
    if subscription.user and subscription.user.telegram_user_id:
        plan_name = subscription.plan.name if subscription.plan else "اشتراک"
        msg = f"✅ اشتراک {plan_name} شما توسط مدیریت فعال شد." if subscription.status == "active" else f"❌ اشتراک {plan_name} شما توسط مدیریت لغو شد."
        await send_telegram_notification(subscription.user.telegram_user_id, msg)

    subscription = (
        await db.execute(
        select(UserSubscription)
            .options(selectinload(UserSubscription.user), selectinload(UserSubscription.plan), selectinload(UserSubscription.pool))
            .where(UserSubscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    return await _subscription_out(subscription, db)

@router.post("/plans", response_model=SubscriptionPlanOut)
async def create_plan(plan: SubscriptionPlanCreate, db: AsyncSession = Depends(get_session)):
    db_plan = SubscriptionPlan(**plan.model_dump())
    db.add(db_plan)
    await db.commit()
    await db.refresh(db_plan)
    return db_plan

@router.patch("/plans/{plan_id}", response_model=SubscriptionPlanOut)
async def update_plan(plan_id: int, data: SubscriptionPlanUpdate, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    db_plan = result.scalar_one_or_none()
    if not db_plan:
        raise HTTPException(404, "Plan not found")
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(db_plan, key, value)
    await db.commit()
    await db.refresh(db_plan)
    return db_plan

@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    db_plan = result.scalar_one_or_none()
    if not db_plan:
        raise HTTPException(404, "Plan not found")
    await db.delete(db_plan)
    await db.commit()
    return {"ok": True}

@router.get("/plans/{plan_id}/rules", response_model=list[SubscriptionPlanRuleOut])
async def list_rules(plan_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(SubscriptionPlanRule).where(SubscriptionPlanRule.plan_id == plan_id))
    return list(result.scalars().all())

@router.post("/plans/{plan_id}/rules", response_model=SubscriptionPlanRuleOut)
async def create_rule(plan_id: int, rule: SubscriptionPlanRuleCreate, db: AsyncSession = Depends(get_session)):
    db_rule = SubscriptionPlanRule(**rule.model_dump(), plan_id=plan_id)
    db.add(db_rule)
    await db.commit()
    await db.refresh(db_rule)
    return db_rule

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(SubscriptionPlanRule).where(SubscriptionPlanRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if rule:
        await db.delete(rule)
        await db.commit()
    return {"ok": True}
