from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.services.wallet_service import usd_to_minor


@dataclass(frozen=True)
class UsageTokens:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_usage_token(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def extract_usage_tokens(usage: dict | None) -> UsageTokens:
    if not isinstance(usage, dict):
        return UsageTokens()
    input_tokens = parse_usage_token(usage.get("prompt_tokens"))
    if input_tokens == 0:
        input_tokens = parse_usage_token(usage.get("input_tokens"))
    if input_tokens == 0:
        input_tokens = parse_usage_token(usage.get("prompt_token_count"))
    if input_tokens == 0:
        input_tokens = parse_usage_token(usage.get("cached_prompt_tokens"))

    output_tokens = parse_usage_token(usage.get("completion_tokens"))
    if output_tokens == 0:
        output_tokens = parse_usage_token(usage.get("output_tokens"))
    if output_tokens == 0:
        output_tokens = parse_usage_token(usage.get("candidates_token_count"))
    if output_tokens == 0:
        total_tokens = parse_usage_token(usage.get("total_tokens"))
        if total_tokens > input_tokens:
            output_tokens = total_tokens - input_tokens
    return UsageTokens(input_tokens=input_tokens, output_tokens=output_tokens)


def sum_usage_tokens(usages: list[dict | None] | tuple[dict | None, ...]) -> UsageTokens:
    input_total = 0
    output_total = 0
    for usage in usages:
        tokens = extract_usage_tokens(usage)
        input_total += tokens.input_tokens
        output_total += tokens.output_tokens
    return UsageTokens(input_total, output_total)


def estimate_text_tokens(text: str | None) -> int:
    if not text:
        return 1
    return max(1, (len(text) + 3) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        role = str(msg.get("role") or "")
        total += max(2, len(role))
        content = msg.get("content")
        if isinstance(content, str):
            total += estimate_text_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += estimate_text_tokens(str(part.get("text") or ""))
                elif isinstance(part, dict) and part.get("type") == "image_url":
                    total += 250
                else:
                    total += estimate_text_tokens(str(part))
        else:
            total += estimate_text_tokens(str(content))
    return max(total, 1)


def usage_cost_usd(model: Any, input_tokens: int, output_tokens: int) -> float:
    price_in = float(getattr(model, "pricing_input", 0.0) or 0.0)
    price_out = float(getattr(model, "pricing_output", 0.0) or 0.0)
    return max(0.0, ((input_tokens / 1_000_000.0) * price_in) + ((output_tokens / 1_000_000.0) * price_out))


def _usage_event_model():
    return getattr(models, "UsageEvent", None)


def _set_if_present(obj: Any, name: str, value: Any) -> None:
    if hasattr(obj, name):
        setattr(obj, name, value)


def _event_kwargs(Event: Any, values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if hasattr(Event, key)}


async def create_usage_event(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    telegram_user_id: int | None = None,
    chat_id: int | None = None,
    message_id: int | None = None,
    provider_name: str | None = None,
    model_name: str | None = None,
    provider_id: int | None = None,
    model_id: int | None = None,
    uploaded_file_id: int | None = None,
    channel: str = "telegram",
    operation: str = "chat_completion",
    status: str = "pending",
    metadata: dict | None = None,
    commit: bool = False,
) -> Any | None:
    Event = _usage_event_model()
    if Event is None:
        return None
    event = Event(**_event_kwargs(Event, {
        "user_id": user_id,
        "telegram_user_id": telegram_user_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "uploaded_file_id": uploaded_file_id,
        "provider_id": provider_id,
        "provider_name": provider_name,
        "provider_name_snapshot": provider_name,
        "model_id": model_id,
        "model_name": model_name,
        "model_name_snapshot": model_name,
        "operation": operation,
        "operation_type": operation,
        "event_type": operation,
        "channel": channel,
        "status": status,
        "metadata_json": metadata or {},
        "created_at": utcnow(),
        "started_at": utcnow(),
    }))
    db.add(event)
    if commit:
        await db.commit()
        await db.refresh(event)
    else:
        await db.flush()
    return event


async def complete_usage_event(
    db: AsyncSession,
    event: Any | None,
    *,
    usage: dict | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    cost_minor: int | None = None,
    usage_source: str | None = None,
    status: str = "completed",
    error: str | None = None,
    metadata: dict | None = None,
    commit: bool = False,
) -> Any | None:
    if event is None:
        return None
    tokens = extract_usage_tokens(usage)
    input_count = int(input_tokens if input_tokens is not None else tokens.input_tokens)
    output_count = int(output_tokens if output_tokens is not None else tokens.output_tokens)
    _set_if_present(event, "input_tokens", input_count)
    _set_if_present(event, "prompt_tokens", input_count)
    _set_if_present(event, "output_tokens", output_count)
    _set_if_present(event, "completion_tokens", output_count)
    _set_if_present(event, "total_tokens", input_count + output_count)
    if cost_usd is not None:
        _set_if_present(event, "cost_usd", float(cost_usd))
        _set_if_present(event, "actual_cost_minor", usd_to_minor(cost_usd))
    if cost_minor is not None:
        _set_if_present(event, "actual_cost_minor", int(cost_minor))
    if usage_source is not None:
        _set_if_present(event, "usage_source", usage_source)
    _set_if_present(event, "status", status if error is None else "failed")
    _set_if_present(event, "error", error)
    _set_if_present(event, "completed_at", utcnow())
    if metadata is not None and hasattr(event, "metadata_json"):
        current = getattr(event, "metadata_json", None) or {}
        current.update(metadata)
        event.metadata_json = current
    if commit:
        await db.commit()
        await db.refresh(event)
    else:
        await db.flush()
    return event
