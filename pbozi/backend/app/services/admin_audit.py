from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _admin_action_model():
    return getattr(models, "AdminAction", None)


def _kwargs_for(Model: Any, values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if hasattr(Model, key)}


async def create_admin_action(
    db: AsyncSession,
    *,
    admin_user_id: int | None = None,
    admin_telegram_user_id: int | None = None,
    action: str,
    target_type: str | None = "unknown",
    target_id: int | str | None = None,
    before_json: dict | None = None,
    after_json: dict | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    commit: bool = False,
) -> Any | None:
    """Create AdminAction when that model exists; otherwise no-op."""
    AdminAction = _admin_action_model()
    if AdminAction is None:
        return None
    item = AdminAction(**_kwargs_for(AdminAction, {
        "admin_user_id": admin_user_id,
        "admin_telegram_user_id": admin_telegram_user_id,
        "user_id": admin_user_id,
        "action": action,
        "action_type": action,
        "target_type": target_type or "unknown",
        "target_id": int(target_id) if isinstance(target_id, int) or (isinstance(target_id, str) and target_id.isdigit()) else None,
        "before_json": before_json,
        "after_json": after_json,
        "reason": reason,
        "metadata_json": metadata or {},
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": utcnow(),
    }))
    db.add(item)
    if commit:
        await db.commit()
        await db.refresh(item)
    else:
        await db.flush()
    return item
