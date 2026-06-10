from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import UserPreference
from app.schemas import LearningPreferencesSkipRequest, LearningPreferencesTurnRequest, PromoCodeRedemptionCreate, PromoCodeRedemptionOut
from app.services.account_service import (
    create_or_restore_user,
    get_user_by_telegram_id,
    normalize_phone_number,
    onboarding_state,
)
from app.services.promo_code_service import PromoCodeRedemptionError, redeem_promo_code_for_user
from app.services.learning_preferences_service import (
    finalize_learning_preferences_onboarding,
    get_learning_preferences_status,
    skip_learning_preferences_onboarding,
    start_learning_preferences_onboarding,
    submit_learning_preferences_answer,
)

router = APIRouter(prefix="/account", tags=["account"])


def _mask_phone(phone_number: str | None) -> str | None:
    normalized = normalize_phone_number(phone_number)
    if not normalized:
        return None
    visible = normalized[-4:]
    return f"{'*' * max(len(normalized) - 4, 0)}{visible}"


def _account_state_payload(user: UserPreference) -> dict:
    state = onboarding_state(user)
    return {
        "account_status": user.account_status,
        "onboarding": {
            "missing_phone": state.missing_phone,
            "missing_preferred_name": state.missing_preferred_name,
            "completed": state.completed,
        },
    }


def _account_summary_payload(user: UserPreference) -> dict:
    return {
        "id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "first_name": user.first_name,
        "username": user.username,
        "preferred_name": user.preferred_name,
        "phone_number": _mask_phone(user.phone_number),
        "is_admin": bool(user.is_admin),
        "learning_preferences_status": user.learning_preferences_status,
        "learning_preferences_summary": user.learning_preferences_summary,
        "learning_preferences_completed_at": user.learning_preferences_completed_at,
        **_account_state_payload(user),
    }


async def _get_or_create_user_for_telegram_onboarding(db: AsyncSession, telegram_user_id: int) -> UserPreference:
    user = await get_user_by_telegram_id(db, telegram_user_id)
    if user:
        return user
    return await create_or_restore_user(db, telegram_user_id=telegram_user_id, commit=True)


@router.get("/normalize-phone")
async def preview_normalized_phone(phone: str = Query(..., min_length=1)) -> dict:
    normalized = normalize_phone_number(phone)
    return {
        "normalized": normalized is not None,
        "phone_number": _mask_phone(normalized),
    }


@router.get("/status/by-telegram/{telegram_user_id}")
async def get_account_status_by_telegram_id(
    telegram_user_id: int,
    db: AsyncSession = Depends(get_session),
) -> dict:
    user = await get_user_by_telegram_id(db, telegram_user_id)
    if not user:
        return {
            "exists": False,
            "telegram_user_id": telegram_user_id,
            "account_status": None,
            "onboarding": None,
        }
    return {
        "exists": True,
        "user_id": user.id,
        "telegram_user_id": user.telegram_user_id,
        **_account_state_payload(user),
    }


@router.get("/summary/{user_id}")
async def get_account_summary(
    user_id: int,
    db: AsyncSession = Depends(get_session),
) -> dict:
    user = await db.get(UserPreference, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _account_summary_payload(user)


@router.post("/promo-codes/by-telegram/{telegram_user_id}/redeem", response_model=PromoCodeRedemptionOut)
async def redeem_promo_code_by_telegram(
    telegram_user_id: int,
    data: PromoCodeRedemptionCreate,
    db: AsyncSession = Depends(get_session),
) -> PromoCodeRedemptionOut:
    user = await _get_or_create_user_for_telegram_onboarding(db, telegram_user_id)
    try:
        redemption = await redeem_promo_code_for_user(
            db,
            user=user,
            code=data.code,
            charge_amount_usd=float(data.charge_amount or 0.0),
            source="account_by_telegram",
        )
    except PromoCodeRedemptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return redemption


@router.get("/learning-preferences/{user_id}")
async def get_learning_preferences(user_id: int, db: AsyncSession = Depends(get_session)) -> dict:
    user = await db.get(UserPreference, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    payload = await get_learning_preferences_status(user)
    return {
        "user_id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "learning_preferences": payload,
    }


@router.get("/learning-preferences/by-telegram/{telegram_user_id}")
async def get_learning_preferences_by_telegram(
    telegram_user_id: int,
    db: AsyncSession = Depends(get_session),
) -> dict:
    user = await get_user_by_telegram_id(db, telegram_user_id)
    if not user:
        return {
            "exists": False,
            "telegram_user_id": telegram_user_id,
            "learning_preferences": {
                "status": "not_started",
                "in_progress": False,
                "completed": False,
                "skipped": False,
                "questions_answered": 0,
                "next_question": None,
                "summary": None,
                "prompt_context": None,
                "profile": None,
                "completed_at": None,
            },
        }
    payload = await get_learning_preferences_status(user)
    return {
        "exists": True,
        "user_id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "learning_preferences": payload,
    }


@router.post("/learning-preferences/by-telegram/{telegram_user_id}/start")
async def start_learning_preferences_by_telegram(
    telegram_user_id: int,
    restart: bool = False,
    db: AsyncSession = Depends(get_session),
) -> dict:
    user = await _get_or_create_user_for_telegram_onboarding(db, telegram_user_id)
    payload = await start_learning_preferences_onboarding(db, user=user, restart=restart)
    return {
        "user_id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "learning_preferences": payload,
    }


@router.post("/learning-preferences/by-telegram/{telegram_user_id}/turn")
async def submit_learning_preferences_turn_by_telegram(
    telegram_user_id: int,
    data: LearningPreferencesTurnRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    user = await _get_or_create_user_for_telegram_onboarding(db, telegram_user_id)
    try:
        payload = await submit_learning_preferences_answer(db, user=user, message=data.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "user_id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "learning_preferences": payload,
    }


@router.post("/learning-preferences/by-telegram/{telegram_user_id}/skip")
async def skip_learning_preferences_by_telegram(
    telegram_user_id: int,
    data: LearningPreferencesSkipRequest | None = None,
    db: AsyncSession = Depends(get_session),
) -> dict:
    user = await _get_or_create_user_for_telegram_onboarding(db, telegram_user_id)
    payload = await skip_learning_preferences_onboarding(db, user=user, reason=(data.reason if data else None))
    return {
        "user_id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "learning_preferences": payload,
    }


@router.post("/learning-preferences/by-telegram/{telegram_user_id}/finalize")
async def finalize_learning_preferences_by_telegram(
    telegram_user_id: int,
    db: AsyncSession = Depends(get_session),
) -> dict:
    user = await _get_or_create_user_for_telegram_onboarding(db, telegram_user_id)
    payload = await finalize_learning_preferences_onboarding(db, user=user)
    return {
        "user_id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "learning_preferences": payload,
    }
