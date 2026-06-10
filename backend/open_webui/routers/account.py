"""
Account router for Dr. Boz (ERA) account integration.

Provides endpoints to fetch account information from the ERA database
and display it in the Open WebUI frontend.

User mapping:
  - Open WebUI user.oauth.telegram.sub (or .bale.sub) -> telegram_user_id
  - This is used to look up the corresponding user_preferences record
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from open_webui.utils.auth import get_verified_user
from open_webui.models.users import UserModel
from open_webui.models.era_db import (
    UserPreference,
    UserSubscription,
    SubscriptionPlan,
    UserBillingAccount,
    TomanLedgerEntry,
    ReferralCampaign,
    ReferralEvent,
)
from open_webui.utils.era_db import get_era_session, is_era_db_available

router = APIRouter()
log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_era_tracking_id(user: UserModel) -> int:
    """
    Map any Open WebUI user to a stable ERA tracking ID.

    Telegram/Bale users keep their real telegram_user_id.
    Email/password users get a synthetic integer derived from the webui user ID
    so the ERA database can track their spending.  Range: 9_000_000_000+.
    """
    oauth = getattr(user, 'oauth', None) or {}
    for provider in ('telegram', 'bale'):
        provider_data = oauth.get(provider)
        if provider_data and 'sub' in provider_data:
            try:
                return int(provider_data['sub'])
            except (ValueError, TypeError):
                continue
    import hashlib
    h = hashlib.md5(user.id.encode()).hexdigest()[:10]
    return 9_000_000_000 + (int(h, 16) % 1_000_000_000)


async def _find_era_user(db: AsyncSession, tracking_id: int) -> Optional[UserPreference]:
    """Find the ERA user by telegram_user_id."""
    result = await db.execute(
        select(UserPreference).where(UserPreference.telegram_user_id == tracking_id)
    )
    return result.scalars().first()


async def _get_active_subscription(db: AsyncSession, era_user_id: int):
    """Get the active subscription for a user."""
    now = _utcnow()
    result = await db.execute(
        select(UserSubscription)
        .options(selectinload(UserSubscription.plan))
        .where(
            UserSubscription.user_id == era_user_id,
            UserSubscription.status == 'active',
            UserSubscription.expires_at > now,
        )
        .order_by(UserSubscription.expires_at.desc())
    )
    return result.scalars().first()


async def _get_billing_account(db: AsyncSession, era_user_id: int) -> Optional[UserBillingAccount]:
    """Get or create the billing account for a user."""
    result = await db.execute(
        select(UserBillingAccount).where(UserBillingAccount.user_id == era_user_id)
    )
    return result.scalars().first()


def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime to ISO string."""
    if dt is None:
        return None
    try:
        return dt.isoformat() + 'Z'
    except Exception:
        return None


def _calc_limit_info(spent: int, limit: int, ends_at: Optional[datetime]) -> dict:
    """Calculate limit usage info."""
    if limit <= 0:
        return {
            'used': spent or 0,
            'total': 0,
            'remaining': 0,
            'reset_at': _format_datetime(ends_at),
            'reached': False,
        }
    remaining = max(0, limit - (spent or 0))
    reached = (spent or 0) >= limit
    return {
        'used': spent or 0,
        'total': limit,
        'remaining': remaining,
        'reset_at': _format_datetime(ends_at),
        'reached': reached,
    }


def _format_toman(amount: int) -> str:
    """Format amount in toman with Persian-style formatting."""
    return f"{int(amount or 0):,}"


# ─── Endpoints ──────────────────────────────────────────────────


@router.get('/me', response_model=dict)
async def get_account_me(
    user=Depends(get_verified_user),
):
    """
    Get current user's account information from the ERA database.
    
    Returns plan, subscription, wallet, and limit info.
    """
    if not await is_era_db_available():
        return {
            'available': False,
            'user': None,
            'plan': None,
            'subscription': None,
            'wallet': None,
            'limits': None,
        }

    era_tracking_id = _get_era_tracking_id(user)

    try:
        async with get_era_session() as db:
            era_user = await _find_era_user(db, era_tracking_id)
            if not era_user:
                # Try phone-based lookup for OTP phone-auth users
                phone = getattr(user, 'phone', None)
                if phone:
                    phone_result = await db.execute(
                        select(UserPreference).where(UserPreference.phone_number == phone)
                    )
                    era_user = phone_result.scalars().first()
            if not era_user:
                return {
                    'available': True,
                    'error': 'user_not_found',
                    'message': 'حساب شما در سیستم دکتر بز یافت نشد.',
                    'user': None,
                    'plan': None,
                    'subscription': None,
                    'wallet': None,
                    'limits': None,
                }

            # Get active subscription
            sub = await _get_active_subscription(db, era_user.id)
            plan_name = 'free'
            plan_status = 'inactive'
            plan_expires_at = None
            cooldown_limit = 0
            cooldown_hours = 5
            weekly_limit = 0
            cooldown_spent = 0
            cooldown_ends_at = None
            weekly_spent = 0
            week_resets_at = None

            if sub:
                plan_obj = sub.plan
                plan_name = (plan_obj.name or 'unknown').lower() if plan_obj else 'unknown'
                plan_status = sub.status
                plan_expires_at = _format_datetime(sub.expires_at)
                cooldown_limit = getattr(plan_obj, 'cooldown_limit_toman', 0) or 0
                cooldown_hours = getattr(plan_obj, 'cooldown_hours', 5) or 5
                weekly_limit = getattr(plan_obj, 'weekly_limit_toman', 0) or 0
                cooldown_spent = sub.cooldown_spent_toman or 0
                cooldown_ends_at = sub.cooldown_ends_at
                weekly_spent = sub.weekly_spent_toman or 0
                week_resets_at = sub.week_resets_at

                # Reset cooldown if expired
                now = _utcnow()
                if cooldown_ends_at and now >= cooldown_ends_at:
                    cooldown_spent = 0
                    cooldown_ends_at = None

            # Get billing account
            billing = await _get_billing_account(db, era_user.id)
            gift_balance = 0
            paid_balance = 0
            total_balance = 0
            if billing:
                gift_balance = billing.gift_balance_toman or 0
                paid_balance = billing.paid_balance_toman or 0
                total_balance = gift_balance + paid_balance

            # Calculate limits
            five_hour_limit = _calc_limit_info(cooldown_spent, cooldown_limit, cooldown_ends_at)
            seven_day_limit = _calc_limit_info(weekly_spent, weekly_limit, week_resets_at)

            return {
                'available': True,
                'user': {
                    'id': str(era_user.id),
                    'name': era_user.preferred_name or era_user.first_name or 'کاربر',
                    'phone': era_user.phone_number or '',
                    'status': era_user.account_status or 'active',
                },
                'plan': {
                    'name': plan_name,
                    'display_name': era_user.preferred_name or 'کاربر',
                    'status': plan_status,
                    'expires_at': plan_expires_at,
                },
                'subscription': {
                    'status': plan_status,
                    'expires_at': plan_expires_at,
                },
                'wallet': {
                    'gift_balance': gift_balance,
                    'paid_balance': paid_balance,
                    'total_balance': total_balance,
                    'currency': 'IRR',
                    'formatted_balance': _format_toman(total_balance) + ' تومان',
                },
                'limits': {
                    'five_hour': five_hour_limit,
                    'seven_day': seven_day_limit,
                    'cooldown_hours': cooldown_hours,
                },
            }

    except Exception as e:
        log.error(f'Error fetching account info for tracking_id={era_tracking_id}: {e}')
        return {
            'available': True,
            'error': 'fetch_error',
            'message': 'خطا در دریافت اطلاعات حساب.',
            'user': None,
            'plan': None,
            'subscription': None,
            'wallet': None,
            'limits': None,
        }


async def _get_account_usage_internal(user: UserModel) -> dict:
    """
    Internal version of get_account_usage without Depends.
    Can be called from main.py chat_completion with an already-resolved user.
    """
    if not await is_era_db_available():
        return {
            'plan': 'free',
            'quota': {'used': 0, 'limit': 0, 'remaining': 0},
            'subscription': {'status': 'active', 'expires_at': None},
            'limits': {
                'five_hour': {'used': 0, 'total': 0, 'remaining': 0, 'reached': False, 'reset_at': None},
                'seven_day': {'used': 0, 'total': 0, 'remaining': 0, 'reached': False, 'reset_at': None},
            },
        }

    tracking_id = _get_era_tracking_id(user)

    try:
        async with get_era_session() as db:
            era_user = await _find_era_user(db, tracking_id)
            if not era_user:
                # Try phone-based lookup for OTP phone-auth users
                phone = getattr(user, 'phone', None)
                if phone:
                    phone_result = await db.execute(
                        select(UserPreference).where(UserPreference.phone_number == phone)
                    )
                    era_user = phone_result.scalars().first()
            if not era_user:
                # Auto-create ERA user with free plan subscription
                from datetime import datetime, timedelta
                now = _utcnow()

                # Get free plan
                free_plan_result = await db.execute(
                    select(SubscriptionPlan).where(SubscriptionPlan.plan_type == 'free').limit(1)
                )
                free_plan = free_plan_result.scalars().first()

                # Create user_preferences
                oauth = getattr(user, 'oauth', None) or {}
                tg_data = oauth.get('telegram', {}) or oauth.get('bale', {}) or {}
                name = user.name or tg_data.get('username', '') or 'کاربر'
                phone = getattr(user, 'phone', None)

                era_user = UserPreference(
                    telegram_user_id=tracking_id,
                    first_name=name,
                    preferred_name=name,
                    phone_number=phone,
                    account_status='active',
                    created_at=now,
                    updated_at=now,
                )
                db.add(era_user)
                await db.flush()

                # Create billing account
                billing = UserBillingAccount(
                    user_id=era_user.id,
                    currency='IRR',
                    gift_balance_toman=0,
                    paid_balance_toman=0,
                    created_at=now,
                    updated_at=now,
                )
                db.add(billing)

                # Create subscription (free plan if available)
                if free_plan:
                    sub = UserSubscription(
                        user_id=era_user.id,
                        plan_id=free_plan.id,
                        status='active',
                        purchased_at=now,
                        expires_at=now + timedelta(days=36500),
                        cooldown_spent_toman=0,
                        cooldown_ends_at=now + timedelta(hours=(free_plan.cooldown_hours or 5)),
                        weekly_spent_toman=0,
                        week_resets_at=now + timedelta(days=7),
                    )
                    db.add(sub)

                await db.commit()

                # Return plan info with free plan limits
                plan_name = 'free'
                cooldown_limit = free_plan.cooldown_limit_toman if free_plan else 0
                weekly_limit = free_plan.weekly_limit_toman if free_plan else 0

                log.info(f'Auto-created ERA user for tracking_id={tracking_id}, owui_user={user.id}')

                return {
                    'plan': plan_name,
                    'quota': {'used': 0, 'limit': 0, 'remaining': 0},
                    'subscription': {'status': 'active', 'expires_at': None},
                    'limits': {
                        'five_hour': {
                            'used': 0,
                            'total': cooldown_limit,
                            'remaining': cooldown_limit,
                            'reset_at': _format_datetime(now + timedelta(hours=(free_plan.cooldown_hours or 5))),
                            'reached': False,
                        },
                        'seven_day': {
                            'used': 0,
                            'total': weekly_limit,
                            'remaining': weekly_limit,
                            'reset_at': _format_datetime(now + timedelta(days=7)),
                            'reached': False,
                        },
                    },
                }

            sub = await _get_active_subscription(db, era_user.id)
            plan_name = 'free'
            cooldown_limit = 0
            weekly_limit = 0
            cooldown_spent = 0
            cooldown_ends_at = None
            weekly_spent = 0
            week_resets_at = None
            sub_expires_at = None
            sub_status = 'active'

            if sub:
                plan_obj = sub.plan
                plan_name = (plan_obj.name or 'unknown').lower()
                sub_status = sub.status
                sub_expires_at = _format_datetime(sub.expires_at)
                cooldown_limit = getattr(plan_obj, 'cooldown_limit_toman', 0) or 0
                weekly_limit = getattr(plan_obj, 'weekly_limit_toman', 0) or 0
                cooldown_spent = sub.cooldown_spent_toman or 0
                cooldown_ends_at = sub.cooldown_ends_at
                weekly_spent = sub.weekly_spent_toman or 0
                week_resets_at = sub.week_resets_at

                now = _utcnow()
                if cooldown_ends_at and now >= cooldown_ends_at:
                    cooldown_spent = 0
                    cooldown_ends_at = None

            five_hour_used = cooldown_spent
            five_hour_total = cooldown_limit
            five_hour_remaining = max(0, five_hour_total - five_hour_used)
            five_hour_reached = five_hour_total > 0 and five_hour_used >= five_hour_total

            seven_day_used = weekly_spent
            seven_day_total = weekly_limit
            seven_day_remaining = max(0, seven_day_total - seven_day_used)
            seven_day_reached = seven_day_total > 0 and seven_day_used >= seven_day_total

            return {
                'plan': plan_name,
                'quota': {'used': 0, 'limit': 0, 'remaining': 0},
                'subscription': {
                    'status': sub_status,
                    'expires_at': sub_expires_at,
                },
                'limits': {
                    'five_hour': {
                        'used': five_hour_used,
                        'total': five_hour_total,
                        'remaining': five_hour_remaining,
                        'reset_at': _format_datetime(cooldown_ends_at),
                        'reached': five_hour_reached,
                    },
                    'seven_day': {
                        'used': seven_day_used,
                        'total': seven_day_total,
                        'remaining': seven_day_remaining,
                        'reset_at': _format_datetime(week_resets_at),
                        'reached': seven_day_reached,
                    },
                },
            }

    except Exception as e:
        log.error(f'Error fetching usage for tracking_id={tracking_id}: {e}')
        return {
            'plan': 'free',
            'quota': {'used': 0, 'limit': 0, 'remaining': 0},
            'subscription': {'status': 'active', 'expires_at': None},
            'limits': {
                'five_hour': {'used': 0, 'total': 0, 'remaining': 0, 'reached': False, 'reset_at': None},
                'seven_day': {'used': 0, 'total': 0, 'remaining': 0, 'reached': False, 'reset_at': None},
            },
        }


@router.get('/usage', response_model=dict)
async def get_account_usage(
    user=Depends(get_verified_user),
):
    """
    Get current user's usage and limits from the ERA database.
    Simplified endpoint for sidebar display.
    """
    return await _get_account_usage_internal(user)


@router.get('/transactions', response_model=dict)
async def get_account_transactions(
    user=Depends(get_verified_user),
):
    """
    Get current user's transaction history from the ERA database.
    """
    if not await is_era_db_available():
        return {'transactions': []}

    tracking_id = _get_era_tracking_id(user)

    try:
        async with get_era_session() as db:
            era_user = await _find_era_user(db, tracking_id)
            if not era_user:
                # Try phone-based lookup for OTP phone-auth users
                phone = getattr(user, 'phone', None)
                if phone:
                    phone_result = await db.execute(
                        select(UserPreference).where(UserPreference.phone_number == phone)
                    )
                    era_user = phone_result.scalars().first()
            if not era_user:
                return {'transactions': []}

            result = await db.execute(
                select(TomanLedgerEntry)
                .where(
                    TomanLedgerEntry.user_id == era_user.id,
                    TomanLedgerEntry.entry_type.notin_(['chat_completion_usage', 'chat_completion']),
                )
                .order_by(TomanLedgerEntry.created_at.desc())
                .limit(20)
            )
            entries = result.scalars().all()

            entry_type_labels = {
                'chat_completion': 'پاسخ چت',
                'voice_transcription': 'تبدیل صوت',
                'rag_embedding': 'ایندکس فایل',
                'admin_adjustment': 'تنظیم ادمین',
                'opening_balance': 'موجودی اولیه',
                'wallet_topup': 'شارژ کیف پول',
                'promo_code_credit': 'بونس کوپن',
                'subscription_gift_credit': 'اعتبار هدیه اشتراک',
                'subscription_wallet_payment': 'پرداخت اشتراک از کیف پول',
                'first_topup_discount_used': 'تخفیف اولین شارژ',
                'chat_completion_usage': 'پاسخ چت',
                'paid_topup_credit': 'شارژ اعتبار',
                'subscription_payment': 'خرید اشتراک',
                'referral_reward': 'پاداش دعوت',
            }

            transactions = []
            for entry in entries:
                delta = entry.amount_toman or 0
                sign = '+' if delta >= 0 else ''
                reason = (entry.reason or '').strip()
                if not reason:
                    reason = entry_type_labels.get((entry.entry_type or '').strip().lower(), entry.entry_type or 'تراکنش')
                created = entry.created_at
                created_str = _format_datetime(created) if created else '-'

                transactions.append({
                    'id': entry.id,
                    'amount': delta,
                    'formatted_amount': f'{sign}{delta:,} تومان',
                    'type': entry.entry_type,
                    'reason': reason,
                    'status': entry.status,
                    'created_at': created_str,
                })

            return {'transactions': transactions}

    except Exception as e:
        log.error(f'Error fetching transactions for tracking_id={tracking_id}: {e}')
        return {'transactions': [], 'error': 'fetch_error'}


@router.get('/referral', response_model=dict)
async def get_account_referral(
    user=Depends(get_verified_user),
):
    """
    Get current user's referral information from the ERA database.
    """
    if not await is_era_db_available():
        return {'available': False}

    tracking_id = _get_era_tracking_id(user)

    try:
        async with get_era_session() as db:
            era_user = await _find_era_user(db, tracking_id)
            if not era_user:
                # Try phone-based lookup for OTP phone-auth users
                phone = getattr(user, 'phone', None)
                if phone:
                    phone_result = await db.execute(
                        select(UserPreference).where(UserPreference.phone_number == phone)
                    )
                    era_user = phone_result.scalars().first()
            if not era_user:
                return {'available': False}

            campaign = None
            if era_user.referral_campaign_id:
                result = await db.execute(
                    select(ReferralCampaign).where(
                        ReferralCampaign.id == era_user.referral_campaign_id
                    )
                )
                campaign = result.scalars().first()

            if not campaign:
                code = f'ref_u{era_user.id}_{era_user.telegram_user_id}'
                campaign = ReferralCampaign(
                    code=code,
                    description=f'Referral link for user {era_user.id}',
                    is_active=True,
                )
                db.add(campaign)
                await db.flush()
                era_user.referral_campaign_id = campaign.id
                await db.commit()

            config_result = await db.execute(
                select(ReferralEvent).where(ReferralEvent.campaign_id == campaign.id)
            )
            events = config_result.scalars().all()
            total_invites = len(events)
            rewarded_count = sum(1 for e in events if e.event_type == 'signup')

            return {
                'available': True,
                'campaign_code': campaign.code,
                'total_invites': total_invites,
                'rewarded_count': rewarded_count,
            }

    except Exception as e:
        log.error(f'Error fetching referral for tracking_id={tracking_id}: {e}')
        return {'available': False, 'error': 'fetch_error'}


# ═══════════════════════════════════════════════════════════════
# Admin Endpoints
# ═══════════════════════════════════════════════════════════════

from open_webui.utils.auth import get_admin_user


@router.get('/admin/plans', response_model=dict)
async def admin_get_plans(
    user=Depends(get_admin_user),
):
    """Admin: List all subscription plans."""
    if not await is_era_db_available():
        raise HTTPException(status_code=503, detail='ERA database not available')

    async with get_era_session() as db:
        result = await db.execute(
            select(SubscriptionPlan).order_by(SubscriptionPlan.id)
        )
        plans = result.scalars().all()
        return {
            'plans': [{
                'id': p.id,
                'name': p.name,
                'plan_type': p.plan_type,
                'monthly_price_toman': p.monthly_price_toman or 0,
                'gift_credit_toman': p.gift_credit_toman or 0,
                'cooldown_limit_toman': p.cooldown_limit_toman or 0,
                'cooldown_hours': p.cooldown_hours or 5,
                'weekly_limit_toman': p.weekly_limit_toman or 0,
                'is_active': p.is_active,
            } for p in plans]
        }


@router.put('/admin/plans/{plan_id}', response_model=dict)
async def admin_update_plan(
    plan_id: int,
    request: Request,
    user=Depends(get_admin_user),
):
    """Admin: Update a subscription plan."""
    if not await is_era_db_available():
        raise HTTPException(status_code=503, detail='ERA database not available')

    body = await request.json()

    async with get_era_session() as db:
        plan = await db.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail='Plan not found')

        allowed_fields = {
            'name', 'plan_type', 'monthly_price_toman',
            'gift_credit_toman', 'cooldown_limit_toman',
            'cooldown_hours', 'weekly_limit_toman', 'is_active',
        }
        for key in allowed_fields:
            if key in body:
                setattr(plan, key, body[key])

        await db.commit()
        await db.refresh(plan)

        return {
            'plan': {
                'id': plan.id,
                'name': plan.name,
                'plan_type': plan.plan_type,
                'monthly_price_toman': plan.monthly_price_toman or 0,
                'gift_credit_toman': plan.gift_credit_toman or 0,
                'cooldown_limit_toman': plan.cooldown_limit_toman or 0,
                'cooldown_hours': plan.cooldown_hours or 5,
                'weekly_limit_toman': plan.weekly_limit_toman or 0,
                'is_active': plan.is_active,
            }
        }


@router.get('/admin/pricing', response_model=dict)
async def admin_get_pricing(
    user=Depends(get_admin_user),
):
    """Admin: Get current model pricing config."""
    from open_webui.config import MODEL_PRICING_CONFIG
    try:
        import json
        pricing = json.loads(MODEL_PRICING_CONFIG.value)
    except (json.JSONDecodeError, TypeError):
        pricing = {}
    return {'pricing': pricing}


@router.put('/admin/pricing', response_model=dict)
async def admin_update_pricing(
    request: Request,
    user=Depends(get_admin_user),
):
    """Admin: Update model pricing config."""
    body = await request.json()
    pricing = body.get('pricing', {})

    import json
    request.app.state.config.MODEL_PRICING_CONFIG = json.dumps(pricing, ensure_ascii=False)

    return {'pricing': json.loads(request.app.state.config.MODEL_PRICING_CONFIG)}


@router.get('/admin/subscriptions', response_model=dict)
async def admin_get_subscriptions(
    user=Depends(get_admin_user),
):
    """Admin: List all user subscriptions."""
    if not await is_era_db_available():
        raise HTTPException(status_code=503, detail='ERA database not available')

    async with get_era_session() as db:
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .order_by(UserSubscription.expires_at.desc())
            .limit(100)
        )
        subs = result.scalars().all()
        return {
            'subscriptions': [{
                'id': s.id,
                'user_id': s.user_id,
                'plan_name': s.plan.name if s.plan else 'unknown',
                'status': s.status,
                'purchased_at': _format_datetime(s.purchased_at),
                'expires_at': _format_datetime(s.expires_at),
                'cooldown_spent_toman': s.cooldown_spent_toman or 0,
                'weekly_spent_toman': s.weekly_spent_toman or 0,
            } for s in subs]
        }


@router.post('/admin/plans', response_model=dict)
async def admin_create_plan(
    request: Request,
    user=Depends(get_admin_user),
):
    """Admin: Create a new subscription plan."""
    if not await is_era_db_available():
        raise HTTPException(status_code=503, detail='ERA database not available')

    body = await request.json()
    now = _utcnow()

    async with get_era_session() as db:
        plan = SubscriptionPlan(
            name=body.get('name', 'New Plan'),
            plan_type=body.get('plan_type', 'free'),
            monthly_price_toman=body.get('monthly_price_toman', 0),
            gift_credit_toman=body.get('gift_credit_toman', 0),
            cooldown_limit_toman=body.get('cooldown_limit_toman', 0),
            cooldown_hours=body.get('cooldown_hours', 5),
            weekly_limit_toman=body.get('weekly_limit_toman', 0),
            is_active=body.get('is_active', True),
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        await db.commit()
        await db.refresh(plan)

        return {
            'plan': {
                'id': plan.id,
                'name': plan.name,
                'plan_type': plan.plan_type,
                'monthly_price_toman': plan.monthly_price_toman or 0,
                'gift_credit_toman': plan.gift_credit_toman or 0,
                'cooldown_limit_toman': plan.cooldown_limit_toman or 0,
                'cooldown_hours': plan.cooldown_hours or 5,
                'weekly_limit_toman': plan.weekly_limit_toman or 0,
                'is_active': plan.is_active,
            }
        }


@router.delete('/admin/plans/{plan_id}', response_model=dict)
async def admin_delete_plan(
    plan_id: int,
    user=Depends(get_admin_user),
):
    """Admin: Delete a subscription plan."""
    if not await is_era_db_available():
        raise HTTPException(status_code=503, detail='ERA database not available')

    async with get_era_session() as db:
        plan = await db.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail='Plan not found')

        await db.delete(plan)
        await db.commit()
        return {'ok': True, 'deleted_id': plan_id}


@router.get('/admin/models', response_model=dict)
async def admin_get_models_with_pricing(
    user=Depends(get_admin_user),
):
    """Admin: List all available models with their current pricing."""
    from open_webui.config import MODEL_PRICING_CONFIG
    import json

    try:
        pricing = json.loads(MODEL_PRICING_CONFIG.value)
    except (json.JSONDecodeError, TypeError):
        pricing = {}

    # Models are stored in app.state.MODELS - we can't access that here
    # So return pricing only; frontend already has access to model list
    return {'pricing': pricing}


@router.get('/plans/public', response_model=dict)
async def get_public_plans():
    """Public: List active subscription plans (for upgrade UI)."""
    if not await is_era_db_available():
        return {'plans': []}

    async with get_era_session() as db:
        result = await db.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.monthly_price_toman)
        )
        plans = result.scalars().all()
        return {
            'plans': [{
                'id': p.id,
                'name': p.name,
                'plan_type': p.plan_type,
                'monthly_price_toman': p.monthly_price_toman or 0,
                'gift_credit_toman': p.gift_credit_toman or 0,
                'cooldown_limit_toman': p.cooldown_limit_toman or 0,
                'cooldown_hours': p.cooldown_hours or 5,
                'weekly_limit_toman': p.weekly_limit_toman or 0,
            } for p in plans]
        }


# ── Admin user plan management ────────────────────────────────


@router.get('/admin/user-plan/{user_id}', response_model=dict)
async def admin_get_user_plan(
    user_id: str,
    user=Depends(get_admin_user),
):
    """Admin: Get the ERA plan and limits for any user by webui user_id."""
    if not await is_era_db_available():
        raise HTTPException(status_code=503, detail='ERA database not available')

    from open_webui.models.users import Users
    webui_user = await Users.get_user_by_id(user_id)
    if not webui_user:
        raise HTTPException(status_code=404, detail='User not found')

    tracking_id = _get_era_tracking_id(webui_user)

    async with get_era_session() as db:
        era_user = await _find_era_user(db, tracking_id)
        if not era_user:
            # Try phone-based lookup for OTP phone-auth users
            phone = getattr(webui_user, 'phone', None)
            if phone:
                phone_result = await db.execute(
                    select(UserPreference).where(UserPreference.phone_number == phone)
                )
                era_user = phone_result.scalars().first()

        if not era_user:
            # no era data yet
            return {
                'user_id': user_id,
                'user_name': webui_user.name,
                'user_email': getattr(webui_user, 'email', None),
                'plan': 'free',
                'plan_id': None,
                'subscription': None,
            }

        sub = await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == era_user.id,
                UserSubscription.status == 'active',
                UserSubscription.expires_at > _utcnow(),
            )
            .order_by(UserSubscription.expires_at.desc())
            .limit(1)
        )
        sub_row = sub.scalars().first()

        plan = None
        if sub_row and sub_row.plan_id:
            plan = await db.get(SubscriptionPlan, sub_row.plan_id)

        return {
            'user_id': user_id,
            'user_name': webui_user.name,
            'user_email': getattr(webui_user, 'email', None),
            'plan': plan.plan_type if plan else 'free',
            'plan_id': plan.id if plan else None,
            'plan_name': plan.name if plan else 'رایگان',
            'subscription': {
                'status': sub_row.status if sub_row else 'active',
                'expires_at': sub_row.expires_at.isoformat() if sub_row and sub_row.expires_at else None,
                'cooldown_limit_toman': plan.cooldown_limit_toman if plan else None,
                'cooldown_hours': plan.cooldown_hours if plan else 5,
                'weekly_limit_toman': plan.weekly_limit_toman if plan else None,
                'cooldown_spent_toman': sub_row.cooldown_spent_toman if sub_row else 0,
                'weekly_spent_toman': sub_row.weekly_spent_toman if sub_row else 0,
                'cooldown_ends_at': sub_row.cooldown_ends_at.isoformat() if sub_row and sub_row.cooldown_ends_at else None,
                'week_resets_at': sub_row.week_resets_at.isoformat() if sub_row and sub_row.week_resets_at else None,
            } if sub_row else None,
        }


@router.put('/admin/user-plan/{user_id}', response_model=dict)
async def admin_set_user_plan(
    user_id: str,
    request: Request,
    user=Depends(get_admin_user),
):
    """Admin: Assign a plan to any user by webui user_id.

    Body: { "plan_type": "pro" | "plus" | "max" | "free" }
    """
    if not await is_era_db_available():
        raise HTTPException(status_code=503, detail='ERA database not available')

    body = await request.json()
    plan_type = body.get('plan_type', '').strip().lower()
    if plan_type not in ('free', 'pro', 'plus', 'max'):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan_type: {plan_type}. Must be one of: free, pro, plus, max.",
        )

    from open_webui.models.users import Users
    webui_user = await Users.get_user_by_id(user_id)
    if not webui_user:
        raise HTTPException(status_code=404, detail='User not found')

    tracking_id = _get_era_tracking_id(webui_user)
    now = _utcnow()

    async with get_era_session() as db:
        era_user = await _find_era_user(db, tracking_id)

        if not era_user:
            # Try phone-based lookup for OTP phone-auth users
            phone = getattr(webui_user, 'phone', None)
            if phone:
                phone_result = await db.execute(
                    select(UserPreference).where(UserPreference.phone_number == phone)
                )
                era_user = phone_result.scalars().first()

        if not era_user:
            # auto-create era user
            phone = getattr(webui_user, 'phone', None)
            era_user = UserPreference(
                telegram_user_id=tracking_id,
                first_name=webui_user.name or 'کاربر',
                preferred_name=webui_user.name or 'کاربر',
                phone_number=phone,
                account_status='active',
                created_at=now,
                updated_at=now,
            )
            db.add(era_user)
            await db.flush()

            billing = UserBillingAccount(
                user_id=era_user.id,
                currency='IRR',
                gift_balance_toman=0,
                paid_balance_toman=0,
                created_at=now,
                updated_at=now,
            )
            db.add(billing)

        # Resolve plan
        target_plan_result = await db.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.plan_type == plan_type)
            .limit(1)
        )
        target_plan = target_plan_result.scalars().first()
        if not target_plan:
            raise HTTPException(status_code=404, detail=f'Plan type {plan_type} not found in database')

        # Cancel existing active subscriptions
        existing_result = await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == era_user.id,
                UserSubscription.status == 'active',
            )
        )
        for existing_sub in existing_result.scalars().all():
            existing_sub.status = 'cancelled'

        # Create new subscription
        new_sub = UserSubscription(
            user_id=era_user.id,
            plan_id=target_plan.id,
            status='active',
            purchased_at=now,
            expires_at=now + timedelta(days=36500),
            cooldown_spent_toman=0,
            cooldown_ends_at=now + timedelta(hours=(target_plan.cooldown_hours or 5)),
            weekly_spent_toman=0,
            week_resets_at=now + timedelta(days=7),
        )
        db.add(new_sub)
        await db.commit()

        log.info(
            f'Admin {user.email} set plan of user {webui_user.email} '
            f'(tracking_id={tracking_id}) to {plan_type}'
        )

        return {
            'ok': True,
            'user_id': user_id,
            'plan_type': plan_type,
            'plan_name': target_plan.name or plan_type,
        }
