"""
Spending tracker for Dr. Boz SAAS.

Calculates toman cost from token usage × model pricing,
then updates the ERA database (user_subscriptions, billing accounts, ledger).

Called from chat_messages.py after usage data is saved to the DB.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from open_webui.config import MODEL_PRICING_CONFIG

log = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_pricing() -> dict:
    """Load model pricing from PersistentConfig (JSON string)."""
    try:
        return json.loads(MODEL_PRICING_CONFIG.value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _calculate_cost(model_id: str, usage: dict, output_text: str = '') -> int:
    """
    Calculate cost in toman from token usage and model pricing.

    Model pricing format:
      {"model_id": {"input": 1000, "output": 2000}}
    where values are toman per MILLION tokens (1,000,000 tokens).

    Falls back to default pricing if model not found. Returns 0 when usage
    is unavailable so the caller can decide whether to record the charge.
    """
    pricing = _get_pricing()

    model_price = pricing.get(model_id, {})
    if not model_price:
        for key, val in pricing.items():
            if key in model_id or model_id in key:
                model_price = val
                break

    input_price = model_price.get('input', 500)
    output_price = model_price.get('output', 1000)

    input_tokens = int(usage.get('input_tokens', 0) or 0)
    output_tokens = int(usage.get('output_tokens', 0) or 0)

    if input_tokens == 0 and output_tokens == 0:
        total_tokens = int(usage.get('total_tokens', 0) or 0)
        if total_tokens > 0:
            # Split evenly as a last resort; OpenAI-style usage normally
            # already provides both fields separately.
            input_tokens = total_tokens // 2
            output_tokens = total_tokens - input_tokens

    if output_tokens == 0 and output_text:
        # Provider didn't return usage in the stream. Estimate from text
        # length so we don't silently under-charge. ~4 chars per token
        # is a reasonable midpoint for mixed English/Persian content.
        output_tokens = max(1, len(output_text) // 4)

    if input_tokens == 0 and output_tokens == 0:
        return 0

    input_cost = (input_tokens / 1_000_000) * input_price
    output_cost = (output_tokens / 1_000_000) * output_price
    total_cost = int(input_cost + output_cost)

    if total_cost <= 0:
        total_cost = 1

    log.debug(
        f'Cost: model={model_id}, in={input_tokens}t×{input_price}=>{input_cost:.1f}toman, '
        f'out={output_tokens}t×{output_price}=>{output_cost:.1f}toman, total={total_cost}toman'
    )
    return total_cost


async def _get_era_tracking_id(user_id: str) -> int:
    """
    Map any Open WebUI user to a deterministic ERA tracking ID.

    Telegram/Bale users use their real telegram_user_id.
    Email/password users get a synthetic integer derived from the webui user_id
    so the ERA database (which uses telegram_user_id as its primary key) can
    still track their spending.  The synthetic range starts at 9_000_000_000
    to stay well above real Telegram IDs (typically 6–9 digits).
    """
    from open_webui.internal.db import get_async_db_context
    from open_webui.models.users import Users

    try:
        user = await Users.get_user_by_id(user_id)
        if not user:
            return _synthetic_era_id(user_id)
        oauth = getattr(user, 'oauth', None) or {}
        for provider in ('telegram', 'bale'):
            provider_data = oauth.get(provider)
            if provider_data and 'sub' in provider_data:
                try:
                    return int(provider_data['sub'])
                except (ValueError, TypeError):
                    continue
        # No Telegram/Bale link → generate a deterministic synthetic ID
        return _synthetic_era_id(user_id)
    except Exception as e:
        log.warning(f'Cannot resolve ERA tracking id for user {user_id}: {e}')
        return _synthetic_era_id(user_id)


def _synthetic_era_id(user_id: str) -> int:
    """Derive a stable integer from a webui user_id via MD5.

    Range: 9_000_000_000 .. 9_999_999_999, well above real Telegram IDs.
    """
    import hashlib
    h = hashlib.md5(user_id.encode()).hexdigest()[:10]
    return 9_000_000_000 + (int(h, 16) % 1_000_000_000)


async def _find_era_user_id(db, telegram_id: int) -> Optional[int]:
    """Find ERA user_preferences.id by telegram_user_id."""
    from sqlalchemy import select
    from open_webui.models.era_db import UserPreference

    result = await db.execute(
        select(UserPreference).where(UserPreference.telegram_user_id == telegram_id)
    )
    era_user = result.scalars().first()
    return era_user.id if era_user else None


async def _get_active_sub(db, era_user_id: int):
    """Get active subscription for ERA user."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from open_webui.models.era_db import UserSubscription

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


async def _get_billing_account(db, era_user_id: int):
    """Get or create billing account for ERA user."""
    from sqlalchemy import select
    from open_webui.models.era_db import UserBillingAccount

    result = await db.execute(
        select(UserBillingAccount).where(UserBillingAccount.user_id == era_user_id)
    )
    billing = result.scalars().first()
    if not billing:
        billing = UserBillingAccount(
            user_id=era_user_id,
            currency='IRR',
            gift_balance_toman=0,
            paid_balance_toman=0,
        )
        db.add(billing)
        await db.flush()
    return billing


async def _ledger_exists(db, message_id: str) -> bool:
    """Check if a ledger entry already exists for this message (idempotency)."""
    from sqlalchemy import select
    from open_webui.models.era_db import TomanLedgerEntry

    result = await db.execute(
        select(TomanLedgerEntry).where(TomanLedgerEntry.idempotency_key == f'msg:{message_id}')
    )
    return result.scalars().first() is not None


async def record_spending_from_message(
    user_id: str,
    model_id: Optional[str],
    usage: dict,
    message_id: str,
    output_text: str = '',
):
    """
    Called after chat completion when usage data is available.

    1. Calculate toman cost from token usage × model pricing
    2. Map Open WebUI user → ERA user
    3. Update user_subscriptions (cooldown/weekly spent)
    4. Create toman_ledger_entry
    5. Deduct from billing account
    """
    from open_webui.utils.era_db import get_era_session, is_era_db_available

    try:
        if not await is_era_db_available():
            log.debug('ERA DB not available, skipping spending record')
            return

        cost = _calculate_cost(model_id or 'unknown', usage, output_text=output_text)
        if cost <= 0:
            log.warning(
                f'No usage and no output text for message {message_id} (model={model_id}); '
                f'skipping spending record. Check that the provider returns usage.'
            )
            return

        era_tracking_id = await _get_era_tracking_id(user_id)

        async with get_era_session() as db:
            era_user_id = await _find_era_user_id(db, era_tracking_id)
            if era_user_id is None:
                # Auto-create ERA user for this tracking ID
                from open_webui.models.era_db import UserPreference, UserBillingAccount, UserSubscription, SubscriptionPlan
                from sqlalchemy import select

                now = _utcnow()

                # Get free plan
                free_plan_result = await db.execute(
                    select(SubscriptionPlan).where(SubscriptionPlan.plan_type == 'free').limit(1)
                )
                free_plan = free_plan_result.scalars().first()

                era_user = UserPreference(
                    telegram_user_id=era_tracking_id,
                    first_name='کاربر',
                    preferred_name='کاربر',
                    account_status='active',
                    created_at=now,
                    updated_at=now,
                )
                db.add(era_user)
                await db.flush()
                era_user_id = era_user.id

                # Create billing account
                billing = UserBillingAccount(
                    user_id=era_user_id,
                    currency='IRR',
                    gift_balance_toman=0,
                    paid_balance_toman=0,
                    created_at=now,
                    updated_at=now,
                )
                db.add(billing)

                # Create free subscription
                if free_plan:
                    sub = UserSubscription(
                        user_id=era_user_id,
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
                log.info(f'Auto-created ERA user for tracking_id={era_tracking_id} (from spending tracker)')

            if await _ledger_exists(db, message_id):
                log.debug(f'Spending already recorded for message {message_id}')
                return

            sub = await _get_active_sub(db, era_user_id)
            now = _utcnow()

            cooldown_limit = 0
            cooldown_hours = 5
            weekly_limit = 0

            if sub:
                plan_obj = sub.plan
                cooldown_limit = getattr(plan_obj, 'cooldown_limit_toman', 0) or 0
                cooldown_hours = getattr(plan_obj, 'cooldown_hours', 5) or 5
                weekly_limit = getattr(plan_obj, 'weekly_limit_toman', 0) or 0

                # Reset cooldown if expired
                if sub.cooldown_ends_at and now >= sub.cooldown_ends_at:
                    sub.cooldown_spent_toman = 0
                    sub.cooldown_ends_at = None

                # Reset weekly if needed
                if sub.week_resets_at and now >= sub.week_resets_at:
                    sub.weekly_spent_toman = 0
                    sub.week_resets_at = now + timedelta(days=7)

                # Initialize timers if not set
                if sub.cooldown_ends_at is None:
                    sub.cooldown_ends_at = now + timedelta(hours=cooldown_hours)
                    sub.cooldown_spent_toman = 0

                if sub.week_resets_at is None:
                    sub.week_resets_at = now + timedelta(days=7)
                    sub.weekly_spent_toman = 0

                # Update spending
                sub.cooldown_spent_toman = (sub.cooldown_spent_toman or 0) + cost
                sub.weekly_spent_toman = (sub.weekly_spent_toman or 0) + cost

            # Deduct from billing account (spend from gift first, then paid)
            billing = await _get_billing_account(db, era_user_id)
            gift_used = 0
            paid_used = 0
            remaining = cost

            gift_balance = billing.gift_balance_toman or 0
            if gift_balance > 0:
                gift_used = min(gift_balance, remaining)
                billing.gift_balance_toman = gift_balance - gift_used
                billing.total_gift_spent_toman = (billing.total_gift_spent_toman or 0) + gift_used
                remaining -= gift_used

            if remaining > 0:
                paid_balance = billing.paid_balance_toman or 0
                paid_used = min(paid_balance, remaining)
                billing.paid_balance_toman = paid_balance - paid_used
                billing.total_paid_spent_toman = (billing.total_paid_spent_toman or 0) + paid_used
                remaining -= paid_used

            # Create ledger entry
            from open_webui.models.era_db import TomanLedgerEntry
            ledger = TomanLedgerEntry(
                user_id=era_user_id,
                billing_account_id=billing.id,
                amount_toman=-cost,
                gift_delta_toman=-gift_used,
                paid_delta_toman=-paid_used,
                gift_balance_after_toman=billing.gift_balance_toman,
                paid_balance_after_toman=billing.paid_balance_toman,
                entry_type='chat_completion_usage',
                reason=f'Chat completion: {model_id or "unknown"}',
                idempotency_key=f'msg:{message_id}',
                metadata_json={
                    'model_id': model_id,
                    'message_id': message_id,
                    'input_tokens': usage.get('input_tokens', 0),
                    'output_tokens': usage.get('output_tokens', 0),
                    'cost_toman': cost,
                },
                created_at=now,
            )
            db.add(ledger)
            await db.commit()

            log.info(
                f'Spending recorded: user={user_id}, era_user={era_user_id}, '
                f'model={model_id}, cost={cost}toman, gift_used={gift_used}, paid_used={paid_used}'
            )

    except Exception as e:
        log.error(f'Failed to record spending for message {message_id}: {e}', exc_info=True)
