from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CapacityPool, CodexAccount, Provider, UserSubscription


class CodexCapacityError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CodexCapacitySelection:
    account: CodexAccount | None
    pool: CapacityPool | None
    fallback: dict[str, int | str] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _effective_limit(limit: int | None, safety_buffer_percent: float | None) -> int:
    raw_limit = max(0, _coerce_int(limit))
    if raw_limit == 0:
        return 0
    buffer_percent = min(95.0, max(0.0, _coerce_float(safety_buffer_percent, 30.0)))
    return int(raw_limit * (1.0 - (buffer_percent / 100.0)))


def codex_account_remaining_capacity(account: CodexAccount) -> int:
    five_hour_effective = _effective_limit(account.five_hour_limit, account.safety_buffer_percent)
    weekly_effective = _effective_limit(account.weekly_limit, account.safety_buffer_percent)
    five_hour_remaining = five_hour_effective - max(0, _coerce_int(account.five_hour_used))
    weekly_remaining = weekly_effective - max(0, _coerce_int(account.weekly_used))
    return min(five_hour_remaining, weekly_remaining)


async def recalculate_pool_active_users(db: AsyncSession, pool_id: int) -> int:
    now = _utc_now()
    result = await db.execute(
        select(func.count(UserSubscription.id)).where(
            UserSubscription.pool_id == pool_id,
            UserSubscription.status == "active",
            UserSubscription.expires_at > now,
        )
    )
    active_users = _coerce_int(result.scalar_one_or_none())
    pool = await db.get(CapacityPool, pool_id)
    if pool is not None:
        pool.active_users = active_users
    return active_users


async def assign_subscription_pool(db: AsyncSession, subscription: UserSubscription) -> CapacityPool:
    if subscription.pool_id is not None:
        pool = await db.get(CapacityPool, subscription.pool_id)
        if pool is None:
            raise CodexCapacityError("codex_capacity_unavailable", "Subscription capacity pool not found")
        return pool

    result = await db.execute(
        select(CapacityPool)
        .where(
            CapacityPool.status == "active",
            CapacityPool.active_users < CapacityPool.max_users,
        )
        .order_by(CapacityPool.id)
        .limit(1)
    )
    pool = result.scalar_one_or_none()
    if pool is None:
        raise CodexCapacityError("codex_capacity_unavailable", "No Codex capacity pool has available user capacity")

    subscription.pool_id = pool.id
    pool.active_users = min(max(0, _coerce_int(pool.active_users)) + 1, max(0, _coerce_int(pool.max_users)))
    return pool


async def get_active_user_subscription(db: AsyncSession, user_id: int) -> UserSubscription | None:
    now = _utc_now()
    result = await db.execute(
        select(UserSubscription)
        .where(
            UserSubscription.user_id == user_id,
            UserSubscription.status == "active",
            UserSubscription.expires_at > now,
        )
        .order_by(UserSubscription.expires_at.desc(), UserSubscription.id.desc())
        .limit(1)
    )
    return result.scalars().first()


def build_codex_capacity_fallback(pool: CapacityPool | None) -> dict[str, int | str] | None:
    if pool is None:
        return None
    if pool.fallback_behavior == "fallback_model" and pool.fallback_model_id is not None:
        return {"behavior": "fallback_model", "model_id": int(pool.fallback_model_id)}
    return None


async def select_codex_account_for_subscription(
    db: AsyncSession,
    *,
    provider: Provider | None,
    user_id: int,
) -> CodexAccount | None:
    subscription = await get_active_user_subscription(db, user_id)
    if subscription is None or subscription.pool_id is None:
        return None

    now = _utc_now()
    conditions = [
        CodexAccount.pool_id == subscription.pool_id,
        CodexAccount.is_active == True,
        CodexAccount.status == "active",
        CodexAccount.auth_status == "authenticated",
        or_(CodexAccount.cooldown_until == None, CodexAccount.cooldown_until <= now),
    ]
    if provider is not None and getattr(provider, "id", None) is not None:
        conditions.append(or_(CodexAccount.provider_id == provider.id, CodexAccount.provider_id == None))

    result = await db.execute(select(CodexAccount).where(*conditions).order_by(CodexAccount.id))
    candidates = [
        account
        for account in result.scalars().all()
        if codex_account_remaining_capacity(account) > 0
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda account: (
            codex_account_remaining_capacity(account),
            _as_aware_utc(account.last_used_at) is None,
            -account.id,
        ),
    )


async def resolve_codex_capacity_selection(
    db: AsyncSession,
    *,
    provider: Provider | None,
    user_id: int | None,
) -> CodexCapacitySelection:
    if user_id is None:
        return CodexCapacitySelection(account=None, pool=None)

    subscription = await get_active_user_subscription(db, user_id)
    if subscription is None or subscription.pool_id is None:
        raise CodexCapacityError("codex_subscription_required", "Active Codex subscription with a capacity pool is required")

    pool = await db.get(CapacityPool, subscription.pool_id)
    if pool is None or pool.status != "active":
        raise CodexCapacityError("codex_capacity_unavailable", "Codex capacity pool is not available")

    account = await select_codex_account_for_subscription(db, provider=provider, user_id=user_id)
    return CodexCapacitySelection(account=account, pool=pool, fallback=build_codex_capacity_fallback(pool))


def record_codex_account_usage(account: CodexAccount, usage: dict[str, Any] | None) -> int:
    usage = usage or {}
    total_tokens = _coerce_int(usage.get("total_tokens"))
    if total_tokens <= 0:
        total_tokens = _coerce_int(usage.get("input_tokens")) + _coerce_int(usage.get("output_tokens"))
    if total_tokens <= 0:
        total_tokens = 1

    account.five_hour_used = max(0, _coerce_int(account.five_hour_used)) + total_tokens
    account.weekly_used = max(0, _coerce_int(account.weekly_used)) + total_tokens
    account.last_used_at = _utc_now()
    return total_tokens
