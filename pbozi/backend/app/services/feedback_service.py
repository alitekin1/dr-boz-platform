from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FeedbackEntry, UserPreference

SMALLTALK_TEXT_RE = re.compile(r"^[\s\W_]*(سلام|مرسی|ممنون|تشکر|hi|hello|thanks|thank you|ok|باشه)[\s\W_]*$", re.I)
DEFAULT_MIN_REPLY_CHARS = 120
DEFAULT_PROBABILITY = 0.18
DEFAULT_COOLDOWN_SECONDS = 15 * 60


@dataclass(frozen=True)
class RatingDecision:
    should_request: bool
    reason: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_smalltalk(text: str | None) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return True
    if len(normalized) <= 18 and SMALLTALK_TEXT_RE.match(normalized):
        return True
    if len(normalized.split()) <= 3 and SMALLTALK_TEXT_RE.match(normalized):
        return True
    return False


def basic_rating_decision(
    user_text: str | None,
    assistant_text: str | None,
    *,
    min_reply_chars: int = DEFAULT_MIN_REPLY_CHARS,
    probability: float = DEFAULT_PROBABILITY,
) -> RatingDecision:
    if not assistant_text or len(assistant_text.strip()) < min_reply_chars:
        return RatingDecision(False, "reply_too_short")
    if is_smalltalk(user_text):
        return RatingDecision(False, "user_smalltalk")
    if is_smalltalk(assistant_text):
        return RatingDecision(False, "assistant_smalltalk")
    if probability < 1.0 and random.random() >= max(0.0, probability):
        return RatingDecision(False, "sampled_out")
    return RatingDecision(True, "eligible")


async def recently_requested_or_rated(
    db: AsyncSession,
    *,
    user: UserPreference | None = None,
    telegram_user_id: int | None = None,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
) -> bool:
    cutoff = utcnow() - timedelta(seconds=max(0, cooldown_seconds))
    stmt = select(FeedbackEntry).where(FeedbackEntry.created_at >= cutoff).order_by(desc(FeedbackEntry.created_at)).limit(1)
    if user is not None:
        stmt = stmt.where(FeedbackEntry.user_id == user.id)
    elif telegram_user_id is not None:
        stmt = stmt.where(FeedbackEntry.telegram_user_id == telegram_user_id)
    else:
        return False
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def should_request_rating(
    db: AsyncSession,
    *,
    user: UserPreference | None = None,
    telegram_user_id: int | None = None,
    user_text: str | None,
    assistant_text: str | None,
    min_reply_chars: int = DEFAULT_MIN_REPLY_CHARS,
    probability: float = DEFAULT_PROBABILITY,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
) -> RatingDecision:
    decision = basic_rating_decision(
        user_text,
        assistant_text,
        min_reply_chars=min_reply_chars,
        probability=probability,
    )
    if not decision.should_request:
        return decision
    if await recently_requested_or_rated(db, user=user, telegram_user_id=telegram_user_id, cooldown_seconds=cooldown_seconds):
        return RatingDecision(False, "cooldown")
    return decision


async def create_feedback_entry(
    db: AsyncSession,
    *,
    user: UserPreference | None = None,
    telegram_user_id: int | None = None,
    chat_id: int | None = None,
    message_id: int | None = None,
    rating_value: int,
    note: str | None = None,
    reaction_raw_text: str | None = None,
    source: str = "telegram_inline_button",
    sample_reason: str | None = None,
    commit: bool = True,
) -> FeedbackEntry:
    entry = FeedbackEntry(
        user_id=user.id if user is not None else None,
        telegram_user_id=telegram_user_id if telegram_user_id is not None else getattr(user, "telegram_user_id", None),
        chat_id=chat_id,
        message_id=message_id,
        rating_value=1 if rating_value > 0 else -1,
        note=note,
        reaction_raw_text=reaction_raw_text,
    )
    if hasattr(entry, "source"):
        entry.source = source
    if hasattr(entry, "sample_reason"):
        entry.sample_reason = sample_reason
    db.add(entry)
    if commit:
        await db.commit()
        await db.refresh(entry)
    else:
        await db.flush()
    return entry
