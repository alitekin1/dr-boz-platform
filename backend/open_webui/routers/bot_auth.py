"""
Bot-based authentication router for Telegram and Bale mini-apps.
Provides endpoints for:
  - Telegram mini-app auto-login (initData verification)
  - Bale mini-app auto-login (initData verification)  
  - Desktop auth code verification (bot-generated code flow)
"""

import logging
import secrets
import string
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from open_webui.models.auths import MiniAppAuthForm, AuthCodeForm
from open_webui.models.users import Users, UserModel
from open_webui.utils.auth import create_token
from open_webui.utils.telegram_auth import verify_telegram_init_data
from open_webui.utils.bale_auth import verify_bale_init_data
from open_webui.utils.misc import parse_duration
from open_webui.utils.redis import get_redis_client
from open_webui.internal.db import get_async_session
from open_webui.constants import ERROR_MESSAGES

router = APIRouter()

log = logging.getLogger(__name__)


class MiniAppLoginResponse(BaseModel):
    token: str
    token_type: str = 'bearer'
    id: str
    email: str
    name: str
    role: str
    profile_image_url: str


def _generate_code(length: int = 8) -> str:
    """Generate a random alphanumeric auth code."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def _get_or_create_user_by_oauth(
    provider: str,
    sub: str,
    name: str,
    username: Optional[str] = None,
    phone: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> UserModel:
    """
    Find existing user by OAuth provider+sub, or create a new user.

    Args:
        provider: 'telegram' or 'bale'
        sub: User ID from the provider
        name: Display name (first_name + last_name)
        username: Optional username from provider
        phone: Optional E.164 phone number to persist for new users

    Returns:
        UserModel instance
    """
    # Try to find existing user
    user = await Users.get_user_by_oauth_sub(provider, sub, db=db)

    if user:
        # Update OAuth sub if needed (shouldn't normally change)
        await Users.update_user_oauth_by_id(user.id, provider, sub, db=db)
        return user

    # Create new user
    user_id = str(uuid.uuid4())
    email = f'{provider}_{sub}@drboz.local'  # Internal synthetic email

    user = await Users.insert_new_user(
        id=user_id,
        name=name,
        email=email,
        profile_image_url='/user.png',
        role='user',  # Default role for bot-login users
        username=username,
        oauth={provider: {'sub': sub}},
        phone=phone,
        db=db,
    )

    if not user:
        raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)

    return user


async def _create_auth_response(
    request: Request,
    response: Response,
    user: UserModel,
) -> MiniAppLoginResponse:
    """Create JWT token, set cookie, and return user data."""
    expires_delta = parse_duration(request.app.state.config.JWT_EXPIRES_IN)
    expires_at = None
    if expires_delta:
        expires_at = int(time.time()) + int(expires_delta.total_seconds())
    
    token = create_token(
        data={'id': user.id},
        expires_delta=expires_delta,
    )
    
    # Set HttpOnly auth cookie
    response.set_cookie(
        key='token',
        value=token,
        httponly=True,
        samesite='lax',
        secure=False,
        max_age=int(expires_delta.total_seconds()) if expires_delta else None,
    )
    
    return MiniAppLoginResponse(
        token=token,
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        profile_image_url=user.profile_image_url or '',
    )


# ─── Endpoints ──────────────────────────────────────────────────

@router.post('/telegram/miniapp', response_model=MiniAppLoginResponse)
async def telegram_miniapp_login(
    request: Request,
    response: Response,
    form_data: MiniAppAuthForm,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Auto-login via Telegram Mini App initData.
    Verifies HMAC-SHA256 signature, finds/creates user, returns JWT.
    """
    bot_token = getattr(request.app.state.config, 'TELEGRAM_BOT_TOKEN', None)
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Telegram bot token not configured',
        )
    
    # Debug: log raw initData details
    raw = form_data.initData
    log.info('DEBUG initData len=%d repr(first 200)=%r', len(raw), raw[:200])
    log.info('DEBUG initData repr(last 100)=%r', raw[-100:])
    
    # Verify initData signature
    user_data = verify_telegram_init_data(form_data.initData, bot_token)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid Telegram initData',
        )
    
    telegram_id = str(user_data.get('id'))
    first_name = user_data.get('first_name', '')
    last_name = user_data.get('last_name', '')
    username = user_data.get('username', None)
    
    display_name = f'{first_name} {last_name}'.strip() or f'User_{telegram_id}'
    
    # Optional: check auth_date freshness (max 24h)
    auth_date = user_data.get('auth_date', 0)
    if auth_date:
        current_time = int(time.time())
        if current_time - int(auth_date) > 86400:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='initData is too old (max 24h)',
            )
    
    user = await _get_or_create_user_by_oauth(
        provider='telegram',
        sub=telegram_id,
        name=display_name,
        username=username,
        db=db,
    )
    
    return await _create_auth_response(request, response, user)


@router.post('/bale/miniapp', response_model=MiniAppLoginResponse)
async def bale_miniapp_login(
    request: Request,
    response: Response,
    form_data: MiniAppAuthForm,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Auto-login via Bale Mini App initData.
    """
    bot_token = getattr(request.app.state.config, 'BALE_BOT_TOKEN', None)
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Bale bot token not configured',
        )
    
    user_data = verify_bale_init_data(form_data.initData, bot_token)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid Bale initData',
        )
    
    bale_id = str(user_data.get('id'))
    first_name = user_data.get('first_name', '')
    last_name = user_data.get('last_name', '')
    username = user_data.get('username', None)
    
    display_name = f'{first_name} {last_name}'.strip() or f'User_{bale_id}'
    
    user = await _get_or_create_user_by_oauth(
        provider='bale',
        sub=bale_id,
        name=display_name,
        username=username,
        db=db,
    )
    
    return await _create_auth_response(request, response, user)


@router.post('/code', response_model=MiniAppLoginResponse)
async def verify_bot_auth_code(
    request: Request,
    response: Response,
    form_data: AuthCodeForm,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Verify auth code from bot flow (desktop scenario).
    
    1. Look up code in Redis: auth:code:{CODE}
    2. Extract user_id, provider, telegram_id
    3. Find/create user
    4. Delete code from Redis
    5. Return JWT
    """
    redis_client = get_redis_client(async_mode=True)
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Redis not available',
        )
    
    code = form_data.code.strip().upper()
    provider = form_data.provider  # 'telegram' or 'bale'
    
    if provider not in ('telegram', 'bale'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invalid provider. Must be "telegram" or "bale".',
        )
    
    # Look up code in Redis
    redis_key = f'auth:code:{code}'
    stored = await redis_client.get(redis_key)
    
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired auth code',
        )
    
    try:
        import json as json_module
        data = json_module.loads(stored)
        user_id = data.get('user_id')
        provider_stored = data.get('provider')
        sub = data.get('sub')
    except (json_module.JSONDecodeError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid auth code data',
        )
    
    # Verify provider matches
    if provider_stored != provider:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Provider mismatch',
        )
    
    # Delete code immediately (one-time use)
    await redis_client.delete(redis_key)

    # Extract extra fields from stored payload
    raw_phone = data.get('phone')
    preferred_name = data.get('preferred_name') or data.get('name')

    # Try to find an existing user by phone first (merge with phone-OTP users)
    user = None
    normalized_phone: Optional[str] = None
    if raw_phone:
        try:
            from open_webui.routers.otp_auth import _normalize_phone
            normalized_phone = _normalize_phone(raw_phone)
        except HTTPException:
            normalized_phone = None
        except Exception as e:
            log.debug('phone normalization failed: %s', e)
            normalized_phone = None

        if normalized_phone:
            user = await Users.get_user_by_phone(normalized_phone, db=db)

    if not user:
        # Try OAuth-based lookup
        user = await Users.get_user_by_oauth_sub(provider, sub, db=db)

    if not user:
        # Create new user from stored bot data
        user_name = preferred_name or f'User_{sub}'
        user = await _get_or_create_user_by_oauth(
            provider=provider,
            sub=sub,
            name=user_name,
            username=data.get('username'),
            phone=normalized_phone,
            db=db,
        )
    else:
        # Existing user — merge bot OAuth and fill in missing fields
        try:
            await Users.update_user_oauth_by_id(user.id, provider, str(sub), db=db)
        except Exception as e:
            log.debug('update_user_oauth_by_id failed: %s', e)

        updates: dict = {}
        # Backfill phone column if missing
        if normalized_phone and not user.phone:
            updates['phone'] = normalized_phone
        # Upgrade name if user currently has a placeholder (phone, "+98...", etc.)
        placeholder = (
            not user.name
            or user.name == user.phone
            or user.name == normalized_phone
            or (user.name or '').startswith('+')
            or (user.name or '').isdigit()
        )
        if placeholder and preferred_name:
            updates['name'] = preferred_name
        if updates:
            try:
                updated_user = await Users.update_user_by_id(user.id, updates, db=db)
                if updated_user:
                    user = updated_user
            except Exception as e:
                log.debug('merge update_user_by_id failed: %s', e)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found',
        )

    return await _create_auth_response(request, response, user)
