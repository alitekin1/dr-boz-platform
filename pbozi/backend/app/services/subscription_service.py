from datetime import datetime, timezone
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import UserPreference, SubscriptionPlan, UserSubscription, UserSubscriptionQuota
from app.services.toman_billing_service import purchase_toman_subscription

@dataclass
class PurchaseResult:
    ok: bool
    subscription: UserSubscription | None = None
    quotas: list[UserSubscriptionQuota] | None = None
    error: str | None = None

async def purchase_subscription(db: AsyncSession, user: UserPreference, plan: SubscriptionPlan) -> PurchaseResult:
    result = await purchase_toman_subscription(
        db,
        user=user,
        plan=plan,
        idempotency_key=f"subscription:{user.id}:{plan.id}:{datetime.now(timezone.utc).date().isoformat()}",
    )
    if not result.ok:
        return PurchaseResult(ok=False, error=result.reason or "purchase_failed")
    return PurchaseResult(ok=True, subscription=result.subscription, quotas=[])

async def evaluate_usage_cost(
    db: AsyncSession, 
    user_id: int, 
    model_id: int, 
    chat_id: int, 
    standard_cost_usd: float, 
    input_tokens: int, 
    output_tokens: int, 
    free_tokens_per_chat: int = 100000
) -> tuple[float, bool]:
    # Check global toggle
    from app.models import SubscriptionConfig
    cfg_res = await db.execute(select(SubscriptionConfig))
    cfg = cfg_res.scalars().first()
    if cfg and not cfg.is_enabled:
        return standard_cost_usd, False

    # Returns (final_cost_usd, is_discounted)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    sub_query = select(UserSubscriptionQuota).join(UserSubscription).where(
        UserSubscription.user_id == user_id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now,
        UserSubscriptionQuota.model_id == model_id
    )
    quota = (await db.execute(sub_query)).scalar_one_or_none()
    
    if not quota:
        return standard_cost_usd, False
        
    chat_str = str(chat_id)
    # create a copy of the json or init empty dict
    quotas_json = dict(quota.chat_token_quotas_json) if quota.chat_token_quotas_json else {}
    total_tokens = input_tokens + output_tokens
    
    if chat_str in quotas_json:
        remaining = quotas_json[chat_str]
        if total_tokens <= remaining:
            quotas_json[chat_str] = remaining - total_tokens
            quota.chat_token_quotas_json = quotas_json
            db.add(quota)
            await db.commit()
            return 0.0, True
        else:
            # Consumed the rest, charge the remainder at discount
            excess_tokens = total_tokens - remaining
            excess_ratio = excess_tokens / total_tokens if total_tokens > 0 else 0
            base_cost_for_excess = standard_cost_usd * excess_ratio
            quotas_json[chat_str] = 0
            quota.chat_token_quotas_json = quotas_json
            db.add(quota)
            await db.commit()
            discounted_cost = base_cost_for_excess * (1.0 - (quota.discount_percent / 100.0))
            return discounted_cost, True
            
    elif quota.free_chats_remaining > 0:
        quota.free_chats_remaining -= 1
        remaining = max(0, free_tokens_per_chat - total_tokens)
        quotas_json[chat_str] = remaining
        quota.chat_token_quotas_json = quotas_json
        db.add(quota)
        await db.commit()
        if total_tokens <= free_tokens_per_chat:
            return 0.0, True
        else:
            excess_tokens = total_tokens - free_tokens_per_chat
            excess_ratio = excess_tokens / total_tokens
            base_cost = standard_cost_usd * excess_ratio
            discounted = base_cost * (1.0 - (quota.discount_percent / 100.0))
            return discounted, True
            
    else:
        # No free chats, apply discount
        discounted = standard_cost_usd * (1.0 - (quota.discount_percent / 100.0))
        return discounted, True
