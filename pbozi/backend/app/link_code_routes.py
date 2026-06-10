import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_session
from app.models import LinkCode, UserPreference
from app.schemas import LinkCodeOut, LinkCodeValidateResponse

router = APIRouter(tags=["link-codes"])

# In-memory rate limiter: {ip: [(timestamp, code)]}
_rate_limit_store: dict[str, list[tuple[float, str]]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_ATTEMPTS = 10


def _check_rate_limit(client_ip: str, code: str) -> bool:
    now = time.time()
    entries = _rate_limit_store[client_ip]
    # Clean old entries
    _rate_limit_store[client_ip] = [(ts, c) for ts, c in entries if now - ts < _RATE_LIMIT_WINDOW]
    entries = _rate_limit_store[client_ip]

    # Check if too many attempts in window
    if len(entries) >= _RATE_LIMIT_MAX_ATTEMPTS:
        return False

    entries.append((now, code))
    return True


def generate_code(length: int = 6) -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(length))


@router.post("/users/{telegram_user_id}/link-code", response_model=LinkCodeOut)
async def create_link_code(
    telegram_user_id: int,
    length: int = 6,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(UserPreference).where(UserPreference.telegram_user_id == telegram_user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    existing = await db.execute(
        select(LinkCode).where(
            LinkCode.user_preference_id == user.id,
            LinkCode.used == False,
            LinkCode.expires_at > datetime.now(timezone.utc)
        )
    )
    for code_obj in existing.scalars().all():
        code_obj.used = True

    code = LinkCode(
        code=generate_code(length),
        user_preference_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(code)
    await db.commit()
    await db.refresh(code)

    display_name = user.preferred_name or user.first_name or user.username or f"User {telegram_user_id}"

    return LinkCodeOut(
        code=code.code,
        expires_at=code.expires_at,
        user_name=display_name,
    )


@router.get("/link-codes/{code}/validate", response_model=LinkCodeValidateResponse)
async def validate_link_code(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    client_ip = request.client.host if request.client else "unknown"

    if not _check_rate_limit(client_ip, code):
        raise HTTPException(429, "Too many attempts. Please try again later.")

    result = await db.execute(
        select(LinkCode).where(
            LinkCode.code == code,
            LinkCode.used == False,
            LinkCode.expires_at > datetime.now(timezone.utc)
        )
    )
    link_code = result.scalar_one_or_none()

    if not link_code:
        raise HTTPException(404, "Invalid or expired code")

    user = await db.get(UserPreference, link_code.user_preference_id)
    if not user:
        raise HTTPException(404, "User not found")

    link_code.used = True
    await db.commit()

    return LinkCodeValidateResponse(
        telegram_user_id=user.telegram_user_id,
        first_name=user.first_name,
        username=user.username,
        is_admin=user.is_admin,
        is_pro=user.is_pro,
        preferred_name=user.preferred_name,
    )
