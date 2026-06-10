from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models


TELEGRAM_SOURCE = "telegram"
_MODEL_CANDIDATES = (
    "TelegramUpdateLog",
    "TelegramUpdateIdempotencyLog",
    "TelegramIdempotencyLog",
    "IdempotencyRecord",
    "IdempotencyKey",
    "ProcessedUpdate",
)
_KEY_COLUMNS = ("update_key", "idempotency_key", "key", "request_id")
_METADATA_COLUMNS = ("metadata_json", "metadata")
_PROCESSED_AT_COLUMNS = ("processed_at", "created_at")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _call_or_value(value: Any) -> Any:
    if callable(value):
        try:
            return value()
        except TypeError:
            return None
    return value


def _nested_attr(value: Any, *names: str) -> Any:
    current = value
    for name in names:
        if current is None:
            return None
        current = _call_or_value(_get_attr(current, name))
    return current


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _model_candidates() -> list[Any]:
    return [model for name in _MODEL_CANDIDATES if (model := getattr(models, name, None)) is not None]


def _key_column(Model: Any) -> str | None:
    return next((name for name in _KEY_COLUMNS if hasattr(Model, name)), None)


def _metadata_column(Model: Any) -> str | None:
    return next((name for name in _METADATA_COLUMNS if hasattr(Model, name)), None)


def _processed_at_column(Model: Any) -> str | None:
    return next((name for name in _PROCESSED_AT_COLUMNS if hasattr(Model, name)), None)


def _idempotency_model() -> tuple[Any | None, str | None]:
    for Model in _model_candidates():
        key_column = _key_column(Model)
        if key_column is not None:
            return Model, key_column
    return None, None


def _kwargs_for(Model: Any, values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if hasattr(Model, key)}


def _chat_id(update: Any) -> Any:
    return _first_present(
        _nested_attr(update, "effective_chat", "id"),
        _nested_attr(update, "message", "chat", "id"),
        _nested_attr(update, "callback_query", "message", "chat", "id"),
        _nested_attr(update, "edited_message", "chat", "id"),
        _nested_attr(update, "channel_post", "chat", "id"),
    )


def _message_id(update: Any) -> Any:
    return _first_present(
        _nested_attr(update, "effective_message", "message_id"),
        _nested_attr(update, "message", "message_id"),
        _nested_attr(update, "callback_query", "message", "message_id"),
        _nested_attr(update, "edited_message", "message_id"),
        _nested_attr(update, "channel_post", "message_id"),
    )


def _callback_query_id(update: Any) -> Any:
    return _nested_attr(update, "callback_query", "id")


def build_update_key(update: Any) -> str | None:
    """Return a stable idempotency key for a Telegram update.

    `bot.py` should call this at the start of an update handler, then call
    `was_processed(db, key)` or `should_skip_update(db, update)` before doing
    side effects. Telegram `update_id` is preferred because it is unique per bot;
    message/callback fields are only fallback keys for tests or partial payloads.
    """
    update_id = _get_attr(update, "update_id")
    if update_id is not None:
        return f"telegram:update:{update_id}"

    callback_query_id = _callback_query_id(update)
    if callback_query_id is not None:
        return f"telegram:callback:{callback_query_id}"

    chat_id = _chat_id(update)
    message_id = _message_id(update)
    if chat_id is not None and message_id is not None:
        return f"telegram:chat:{chat_id}:message:{message_id}"

    return None


async def was_processed(db: AsyncSession, key: str | None) -> bool:
    """Return whether `key` is already recorded as processed.

    This is defensive: if no compatible log model/table has been added yet, or
    the table is unavailable during startup/migration, it returns `False` so
    `bot.py` keeps current behavior instead of dropping updates.
    """
    if not key:
        return False

    Model, key_column = _idempotency_model()
    if Model is None or key_column is None:
        return False

    try:
        column = getattr(Model, key_column)
        result = await db.execute(select(Model).where(column == key).limit(1))
        return result.scalar_one_or_none() is not None
    except SQLAlchemyError:
        return False


async def mark_processed(
    db: AsyncSession,
    key: str | None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """Record `key` as processed and return the log row when supported.

    `bot.py` should call this after an update's side effects have completed,
    usually before the surrounding unit of work commits. The function flushes but
    does not commit. If no compatible model/table exists, it is a no-op and
    returns `None`.
    """
    if not key:
        return None

    Model, key_column = _idempotency_model()
    if Model is None or key_column is None:
        return None

    existing = None
    try:
        column = getattr(Model, key_column)
        result = await db.execute(select(Model).where(column == key).limit(1))
        existing = result.scalar_one_or_none()
    except SQLAlchemyError:
        return None

    if existing is not None:
        return existing

    now = utcnow()
    values: dict[str, Any] = {
        key_column: key,
        "source": TELEGRAM_SOURCE,
        "channel": TELEGRAM_SOURCE,
        "status": "processed",
        "created_at": now,
        "updated_at": now,
    }

    processed_at_column = _processed_at_column(Model)
    if processed_at_column is not None:
        values[processed_at_column] = now

    metadata_column = _metadata_column(Model)
    if metadata_column is not None:
        values[metadata_column] = metadata or {}

    try:
        async with db.begin_nested():
            item = Model(**_kwargs_for(Model, values))
            db.add(item)
            await db.flush()
    except IntegrityError:
        # A concurrent worker may have recorded the same update first. Avoid
        # raising from idempotency bookkeeping; the caller can still finish its
        # main transaction according to existing bot behavior.
        return None
    except SQLAlchemyError:
        return None
    return item


async def should_skip_update(db: AsyncSession, update: Any) -> bool:
    """Return `True` when `update` has already been processed.

    Intended `bot.py` pattern:

    ```python
    if await should_skip_update(db, update):
        return
    ...handle update side effects...
    await mark_processed(db, build_update_key(update), {"handler": "..."})
    ```

    When no future Telegram update log table exists, this returns `False` so the
    service is safe to import before the schema is introduced.
    """
    return await was_processed(db, build_update_key(update))
