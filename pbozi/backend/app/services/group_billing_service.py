from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.models as models
from app.services.wallet_service import get_balance_minor, has_credit

DEFAULT_GROUP_TRIGGER_PHRASES = [
    "hey doctor boz",
]

_TRIGGER_PUNCTUATION = " \t\r\n:,-!?.،؛؟"
_COMPLETED_SHARE_STATUSES = {"posted", "charged", "completed"}


@dataclass(frozen=True)
class BillingPrecheckMember:
    user_id: int
    telegram_user_id: int | None
    required_share_minor: int
    balance_minor: int
    has_credit: bool
    is_admin: bool = False


@dataclass(frozen=True)
class BillingPrecheckResult:
    ok: bool
    reason: str | None
    estimated_cost_minor: int
    split_member_count: int
    shares_minor: dict[int, int]
    members: list[BillingPrecheckMember]


@dataclass(frozen=True)
class GroupUsageShareInput:
    user_id: int
    estimated_share_minor: int = 0
    actual_share_minor: int = 0
    ledger_entry_id: int | None = None
    status: str = "pending"
    error: str | None = None
    metadata_json: dict[str, Any] | None = None
    completed_at: datetime | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _collapse_spaces(value: str) -> str:
    val = " ".join(str(value or "").strip().split())
    # Persian normalization
    val = val.replace("ي", "ی").replace("ك", "ک")
    return val


def normalize_trigger_phrases(raw_phrases: Sequence[str] | None, *, fallback: Sequence[str] | None = None) -> list[str]:
    source = raw_phrases if raw_phrases is not None else (fallback if fallback is not None else DEFAULT_GROUP_TRIGGER_PHRASES)
    normalized: list[str] = []
    seen: set[str] = set()
    for phrase in source:
        if not isinstance(phrase, str):
            continue
        cleaned = _collapse_spaces(phrase).casefold()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    if normalized:
        return normalized

    fallback_normalized: list[str] = []
    for phrase in DEFAULT_GROUP_TRIGGER_PHRASES:
        cleaned = _collapse_spaces(phrase).casefold()
        if cleaned and cleaned not in fallback_normalized:
            fallback_normalized.append(cleaned)
    return fallback_normalized


def detect_group_trigger(text: str | None, trigger_phrases: Sequence[str] | None) -> tuple[str | None, str | None]:
    normalized_text = _collapse_spaces(text or "")
    if not normalized_text:
        return None, None
    triggers = normalize_trigger_phrases(trigger_phrases)
    lowered_text = normalized_text.casefold()
    for trigger in triggers:
        if lowered_text == trigger:
            return trigger, ""
        if not lowered_text.startswith(trigger):
            continue
        if len(lowered_text) > len(trigger):
            next_char = lowered_text[len(trigger)]
            if (not next_char.isspace()) and next_char not in _TRIGGER_PUNCTUATION:
                continue
        question = normalized_text[len(trigger) :].lstrip(_TRIGGER_PUNCTUATION)
        return trigger, question
    return None, None


async def list_active_billing_members(db: AsyncSession, *, group_id: int) -> list[models.TelegramGroupMember]:
    result = await db.execute(
        select(models.TelegramGroupMember)
        .options(selectinload(models.TelegramGroupMember.user))
        .where(models.TelegramGroupMember.group_id == group_id)
        .where(models.TelegramGroupMember.status == "active")
        .where(models.TelegramGroupMember.shared_billing_enabled == True)
        .order_by(models.TelegramGroupMember.user_id.asc(), models.TelegramGroupMember.id.asc())
    )
    return list(result.scalars().all())


def split_cost_minor_with_remainder_rule(
    total_cost_minor: int,
    user_ids: Sequence[int],
    *,
    remainder_user_id: int | None = None,
) -> dict[int, int]:
    ordered_ids = sorted({int(uid) for uid in user_ids if int(uid) > 0})
    if not ordered_ids:
        return {}
    total = max(0, int(total_cost_minor or 0))
    base_share, remainder = divmod(total, len(ordered_ids))
    shares = {uid: base_share for uid in ordered_ids}
    if remainder <= 0:
        return shares
    anchor_user_id = remainder_user_id if remainder_user_id in shares else ordered_ids[0]
    shares[anchor_user_id] += remainder
    return shares


async def estimate_split_and_strict_precheck(
    db: AsyncSession,
    *,
    group_id: int,
    estimated_cost_minor: int,
    remainder_user_id: int | None = None,
) -> BillingPrecheckResult:
    group = await db.get(models.TelegramGroup, group_id)
    if group is None:
        return BillingPrecheckResult(
            ok=False,
            reason="group_not_found",
            estimated_cost_minor=max(0, int(estimated_cost_minor or 0)),
            split_member_count=0,
            shares_minor={},
            members=[],
        )
    if str(group.status or "").lower() != "active":
        return BillingPrecheckResult(
            ok=False,
            reason="group_inactive",
            estimated_cost_minor=max(0, int(estimated_cost_minor or 0)),
            split_member_count=0,
            shares_minor={},
            members=[],
        )

    members = await list_active_billing_members(db, group_id=group_id)
    min_active_members = max(1, int(group.min_active_members or 1))
    if len(members) < min_active_members:
        return BillingPrecheckResult(
            ok=False,
            reason="not_enough_active_members",
            estimated_cost_minor=max(0, int(estimated_cost_minor or 0)),
            split_member_count=len(members),
            shares_minor={},
            members=[],
        )

    user_ids = [member.user_id for member in members if member.user_id is not None]
    shares = split_cost_minor_with_remainder_rule(
        estimated_cost_minor,
        user_ids,
        remainder_user_id=remainder_user_id,
    )

    member_states: list[BillingPrecheckMember] = []
    all_ok = True
    for member in members:
        user = member.user
        required_share = int(shares.get(member.user_id, 0))
        if user is None:
            member_state = BillingPrecheckMember(
                user_id=member.user_id,
                telegram_user_id=member.telegram_user_id,
                required_share_minor=required_share,
                balance_minor=0,
                has_credit=False,
                is_admin=False,
            )
            all_ok = False
            member_states.append(member_state)
            continue
        balance_minor = await get_balance_minor(db, user)
        can_pay = await has_credit(db, user, required_share)
        member_state = BillingPrecheckMember(
            user_id=user.id,
            telegram_user_id=getattr(user, "telegram_user_id", None),
            required_share_minor=required_share,
            balance_minor=balance_minor,
            has_credit=can_pay,
            is_admin=bool(getattr(user, "is_admin", False)),
        )
        if not can_pay:
            all_ok = False
        member_states.append(member_state)

    return BillingPrecheckResult(
        ok=all_ok,
        reason=None if all_ok else "insufficient_credit_member",
        estimated_cost_minor=max(0, int(estimated_cost_minor or 0)),
        split_member_count=len(members),
        shares_minor=shares,
        members=member_states,
    )


async def persist_group_usage_event_and_shares(
    db: AsyncSession,
    *,
    group_id: int,
    triggered_by_user_id: int | None = None,
    usage_event_id: int | None = None,
    request_id: str | None = None,
    telegram_chat_id: int | None = None,
    telegram_message_id: int | None = None,
    operation_type: str = "chat_completion",
    estimated_cost_minor: int = 0,
    actual_cost_minor: int = 0,
    status: str = "completed",
    error: str | None = None,
    metadata_json: dict[str, Any] | None = None,
    shares: Sequence[GroupUsageShareInput] | None = None,
    commit: bool = False,
) -> tuple[models.GroupUsageEvent, list[models.GroupUsageShare]]:
    if request_id:
        existing_result = await db.execute(
            select(models.GroupUsageEvent)
            .options(selectinload(models.GroupUsageEvent.shares))
            .where(models.GroupUsageEvent.request_id == request_id)
        )
        existing_event = existing_result.scalar_one_or_none()
        if existing_event is not None:
            return existing_event, list(existing_event.shares or [])

    share_inputs = list(shares or [])
    completed_at = _utcnow() if status in {"completed", "failed", "billing_failed"} else None
    event = models.GroupUsageEvent(
        group_id=group_id,
        usage_event_id=usage_event_id,
        triggered_by_user_id=triggered_by_user_id,
        request_id=request_id,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
        operation_type=operation_type,
        estimated_cost_minor=max(0, int(estimated_cost_minor or 0)),
        actual_cost_minor=max(0, int(actual_cost_minor or 0)),
        split_member_count=len(share_inputs),
        status=status,
        error=error,
        metadata_json=metadata_json or {},
        completed_at=completed_at,
    )
    db.add(event)
    await db.flush()

    created_shares: list[models.GroupUsageShare] = []
    for share in share_inputs:
        share_completed_at = share.completed_at
        if share_completed_at is None and share.status in _COMPLETED_SHARE_STATUSES:
            share_completed_at = _utcnow()
        row = models.GroupUsageShare(
            group_usage_event_id=event.id,
            group_id=group_id,
            user_id=share.user_id,
            ledger_entry_id=share.ledger_entry_id,
            estimated_share_minor=max(0, int(share.estimated_share_minor or 0)),
            actual_share_minor=max(0, int(share.actual_share_minor or 0)),
            status=share.status,
            error=share.error,
            metadata_json=share.metadata_json or {},
            completed_at=share_completed_at,
        )
        db.add(row)
        created_shares.append(row)
    await db.flush()

    if commit:
        await db.commit()
        await db.refresh(event)
    return event, created_shares


__all__ = [
    "BillingPrecheckMember",
    "BillingPrecheckResult",
    "GroupUsageShareInput",
    "DEFAULT_GROUP_TRIGGER_PHRASES",
    "normalize_trigger_phrases",
    "detect_group_trigger",
    "list_active_billing_members",
    "split_cost_minor_with_remainder_rule",
    "estimate_split_and_strict_precheck",
    "persist_group_usage_event_and_shares",
]
