"""
OTP (phone) authentication router.

Provides:
  - POST /api/v1/otp-auth/request   : generate + store 6-digit OTP for a phone number
  - POST /api/v1/otp-auth/verify    : verify code, issue JWT cookie

Currently MOCKED:
  - SMS delivery is NOT performed. The generated code is logged at INFO level so
    you can copy it from `docker logs open-webui`.
  - The fixed dev code 123456 always succeeds regardless of the stored value,
    so the frontend can be exercised without checking logs.

To wire a real SMS provider later, replace the body of `_deliver_sms` with a
call to Kavenegar / Melipayamak / Ghasedak / etc.
"""

import logging
import re
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from open_webui.models.users import Users, UserModel
from open_webui.utils.auth import create_token
from open_webui.utils.misc import parse_duration
from open_webui.utils.redis import get_redis_client
from open_webui.internal.db import get_async_session
from open_webui.constants import ERROR_MESSAGES

router = APIRouter()
log = logging.getLogger(__name__)

OTP_TTL_SECONDS = 300
RESEND_COOLDOWN_SECONDS = 60
MAX_VERIFY_ATTEMPTS = 5
MOCK_BYPASS_CODE = '123456'
PROVIDER = 'phone'


class OtpRequestForm(BaseModel):
    phone: str


class OtpVerifyForm(BaseModel):
    phone: str
    code: str


class OtpRequestResponse(BaseModel):
    success: bool = True
    expires_in: int = OTP_TTL_SECONDS
    cooldown: int = RESEND_COOLDOWN_SECONDS
    mock: bool = True


class OtpLoginResponse(BaseModel):
    token: str
    token_type: str = 'bearer'
    id: str
    email: str
    name: str
    role: str
    profile_image_url: str


def _normalize_phone(raw: str) -> str:
    """
    Normalize an Iranian mobile number into E.164 +98XXXXXXXXXX.

    Accepts: 09123456789, 9123456789, +989123456789, 00989123456789.
    Returns: +989123456789  (always +98 followed by 10 digits starting with 9)
    Raises HTTPException(400) on anything that does not match.
    """
    if not raw:
        raise HTTPException(400, detail='شماره موبایل وارد نشده است')

    digits = re.sub(r'[^\d+]', '', raw).strip()

    if digits.startswith('+98'):
        digits = digits[3:]
    elif digits.startswith('0098'):
        digits = digits[4:]
    elif digits.startswith('98') and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith('0'):
        digits = digits[1:]

    if not re.fullmatch(r'9\d{9}', digits):
        raise HTTPException(400, detail='شماره موبایل معتبر نیست')

    return f'+98{digits}'


def _generate_code() -> str:
    return f'{secrets.randbelow(1_000_000):06d}'


async def _deliver_sms(phone: str, code: str) -> None:
    """
    MOCK: just log the code at INFO. Replace with provider HTTP call later.
    """
    log.info('[OTP MOCK] phone=%s code=%s (use %s as dev bypass)',
             phone, code, MOCK_BYPASS_CODE)


async def _issue_jwt_response(
    request: Request,
    response: Response,
    user: UserModel,
) -> OtpLoginResponse:
    expires_delta = parse_duration(request.app.state.config.JWT_EXPIRES_IN)

    token = create_token(
        data={'id': user.id},
        expires_delta=expires_delta,
    )

    response.set_cookie(
        key='token',
        value=token,
        httponly=True,
        samesite='lax',
        secure=False,
        max_age=int(expires_delta.total_seconds()) if expires_delta else None,
    )

    return OtpLoginResponse(
        token=token,
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        profile_image_url=user.profile_image_url or '',
    )


# ─── Endpoints ──────────────────────────────────────────────────

@router.post('/request', response_model=OtpRequestResponse)
async def request_otp(form_data: OtpRequestForm):
    """
    Generate a 6-digit OTP, store it in Redis, "send" it (mock = log).
    Enforces a 60s per-phone cooldown.
    """
    phone = _normalize_phone(form_data.phone)
    redis_client = get_redis_client(async_mode=True)

    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='سرویس احراز هویت در دسترس نیست',
        )

    cooldown_key = f'otp:cooldown:{phone}'
    if await redis_client.get(cooldown_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail='لطفاً چند ثانیه دیگر دوباره تلاش کنید',
        )

    code = _generate_code()
    otp_key = f'otp:phone:{phone}'
    attempts_key = f'otp:attempts:{phone}'

    await redis_client.setex(otp_key, OTP_TTL_SECONDS, code)
    await redis_client.delete(attempts_key)
    await redis_client.setex(cooldown_key, RESEND_COOLDOWN_SECONDS, '1')

    await _deliver_sms(phone, code)

    return OtpRequestResponse(
        success=True,
        expires_in=OTP_TTL_SECONDS,
        cooldown=RESEND_COOLDOWN_SECONDS,
        mock=True,
    )


@router.post('/verify', response_model=OtpLoginResponse)
async def verify_otp(
    request: Request,
    response: Response,
    form_data: OtpVerifyForm,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Verify a 6-digit OTP for a phone number, find or create the user, set JWT cookie.

    Acceptance rules:
      - Code 123456 ALWAYS succeeds (dev/mock bypass).
      - Otherwise the code must equal the value stored in Redis under
        otp:phone:{phone}, and must not have expired.
      - After 5 wrong attempts the stored code is invalidated.
    """
    phone = _normalize_phone(form_data.phone)
    code = (form_data.code or '').strip()

    if not re.fullmatch(r'\d{6}', code):
        raise HTTPException(400, detail='کد ۶ رقمی معتبر نیست')

    redis_client = get_redis_client(async_mode=True)
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='سرویس احراز هویت در دسترس نیست',
        )

    otp_key = f'otp:phone:{phone}'
    attempts_key = f'otp:attempts:{phone}'

    if code != MOCK_BYPASS_CODE:
        stored = await redis_client.get(otp_key)
        if not stored:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='کد منقضی شده است. لطفاً مجدداً درخواست دهید',
            )

        attempts = await redis_client.incr(attempts_key)
        if attempts == 1:
            await redis_client.expire(attempts_key, OTP_TTL_SECONDS)
        if int(attempts) > MAX_VERIFY_ATTEMPTS:
            await redis_client.delete(otp_key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='تعداد دفعات مجاز به پایان رسید. لطفاً مجدداً درخواست دهید',
            )

        if str(stored) != code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='کد وارد شده اشتباه است',
            )

    # Code accepted -> burn it
    await redis_client.delete(otp_key, attempts_key)

    # Find or create user
    user = await Users.get_user_by_oauth_sub(PROVIDER, phone, db=db)
    if not user:
        user_id = str(uuid.uuid4())
        synthetic_email = f'phone_{phone.lstrip("+")}@drboz.local'

        user = await Users.insert_new_user(
            id=user_id,
            name=phone,  # default display name; user can change in profile
            email=synthetic_email,
            profile_image_url='/user.png',
            role='user',
            username=None,
            oauth={PROVIDER: {'sub': phone}},
            phone=phone,
            db=db,
        )

        if not user:
            raise HTTPException(500, detail=ERROR_MESSAGES.CREATE_USER_ERROR)
    elif not user.phone:
        # Backfill: if the user was created before the phone column existed,
        # populate it now from the oauth sub.
        try:
            user = await Users.update_user_by_id(user.id, {'phone': phone}, db=db) or user
        except Exception as e:
            log.debug('OTP backfill phone skipped: %s', e)

    return await _issue_jwt_response(request, response, user)
