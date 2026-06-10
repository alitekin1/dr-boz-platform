from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from os import getenv

from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserPreference, StarterCreditConfig
from app.services.wallet_service import credit_usd

_PHONE_DIGITS_RE = re.compile(r"\D+")
_PENDING_STATUSES = {"pending", "pending_onboarding", "onboarding", "needs_onboarding"}


@dataclass(frozen=True)
class AccountOnboardingState:
    missing_phone: bool
    missing_preferred_name: bool
    completed: bool


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_admin_telegram_id(telegram_user_id: int, admin_telegram_id: int | None = None) -> bool:
    if admin_telegram_id is None:
        raw_admin_id = getenv("ADMIN_ID", "")
        admin_telegram_id = int(raw_admin_id) if raw_admin_id.isdigit() else None
    return admin_telegram_id is not None and telegram_user_id == admin_telegram_id


def normalize_phone_number(phone: str | None, *, default_country_code: str = "98") -> str | None:
    """Normalize phone numbers to a compact +<country><number> representation when possible."""
    raw = (phone or "").strip()
    if not raw:
        return None
    has_plus = raw.startswith("+")
    digits = _PHONE_DIGITS_RE.sub("", raw)
    if not digits:
        return None
    if has_plus:
        return f"+{digits}"
    if digits.startswith("00") and len(digits) > 2:
        return f"+{digits[2:]}"
    if default_country_code and digits.startswith("0"):
        return f"+{default_country_code}{digits[1:]}"
    if default_country_code and len(digits) <= 10:
        return f"+{default_country_code}{digits}"
    return f"+{digits}"


def onboarding_state(user: UserPreference) -> AccountOnboardingState:
    if bool(getattr(user, "is_admin", False)):
        return AccountOnboardingState(False, False, True)
    missing_phone = not bool((getattr(user, "phone_number", None) or "").strip())
    missing_name = not bool((getattr(user, "preferred_name", None) or "").strip())
    status = (getattr(user, "account_status", None) or "").strip().lower()
    completed = not missing_phone and not missing_name and status not in _PENDING_STATUSES
    return AccountOnboardingState(missing_phone, missing_name, completed)


def mark_onboarding_state(user: UserPreference) -> bool:
    """Set account_status from current profile fields. Returns True if changed."""
    if bool(getattr(user, "is_admin", False)):
        return False
    state = onboarding_state(user)
    desired = "active" if state.completed else "pending_onboarding"
    if getattr(user, "account_status", None) == desired:
        return False
    user.account_status = desired
    return True


async def apply_starter_credit(db: AsyncSession, user: UserPreference) -> bool:
    """Check if user is eligible for starter credit and apply it if so."""
    # Check if they already have any credit ledger entries (to avoid double-applying)
    from app.models import CreditLedgerEntry, TomanLedgerEntry
    res_usd = await db.execute(select(func.count(CreditLedgerEntry.id)).where(
        CreditLedgerEntry.user_id == user.id,
        CreditLedgerEntry.entry_type == "starter_credit"
    ))
    existing_usd_count = res_usd.scalar() or 0

    res_toman = await db.execute(select(func.count(TomanLedgerEntry.id)).where(
        TomanLedgerEntry.user_id == user.id,
        TomanLedgerEntry.entry_type == "starter_gift_credit"
    ))
    existing_toman_count = res_toman.scalar() or 0

    if existing_usd_count > 0 and existing_toman_count > 0:
        return False

    # Get config
    result = await db.execute(select(StarterCreditConfig).where(StarterCreditConfig.is_active == True).order_by(StarterCreditConfig.id))
    config = result.scalars().first()
    if not config or (config.amount_usd <= 0 and config.amount_toman <= 0):
        return False

    applied = False

    # Apply USD credit if configured
    if config.amount_usd > 0 and existing_usd_count == 0:
        from app.services.wallet_service import credit_usd
        await credit_usd(
            db,
            user=user,
            amount_usd=config.amount_usd,
            entry_type="starter_credit",
            reason="Account signup bonus",
            metadata={"config_id": config.id},
            commit=False
        )
        applied = True

    # Apply Toman gift credit if configured
    if config.amount_toman > 0 and existing_toman_count == 0:
        from app.models import UserBillingAccount, TomanLedgerEntry
        from app.services.toman_billing_service import get_or_create_billing_account
        account = await get_or_create_billing_account(db, user)
        account.gift_balance_toman = int(account.gift_balance_toman or 0) + config.amount_toman
        account.total_gift_granted_toman = int(account.total_gift_granted_toman or 0) + config.amount_toman
        ledger_entry = TomanLedgerEntry(
            user_id=user.id,
            billing_account_id=account.id,
            amount_toman=config.amount_toman,
            gift_delta_toman=config.amount_toman,
            paid_delta_toman=0,
            gift_balance_after_toman=account.gift_balance_toman,
            paid_balance_after_toman=account.paid_balance_toman or 0,
            entry_type="starter_gift_credit",
            status="posted",
            reason="Account signup bonus",
            metadata_json={"config_id": config.id},
        )
        db.add(ledger_entry)
        applied = True

    return applied


async def get_user_by_telegram_id(db: AsyncSession, telegram_user_id: int) -> UserPreference | None:
    result = await db.execute(select(UserPreference).where(UserPreference.telegram_user_id == telegram_user_id))
    return result.scalar_one_or_none()


async def get_user_by_phone(db: AsyncSession, phone: str | None) -> UserPreference | None:
    normalized = normalize_phone_number(phone)
    if not normalized:
        return None
    candidates = {normalized, normalized.lstrip("+")}
    if normalized.startswith("+98"):
        candidates.add("0" + normalized[3:])
    result = await db.execute(select(UserPreference).where(UserPreference.phone_number.in_(candidates)))
    return result.scalar_one_or_none()


async def create_or_restore_user(
    db: AsyncSession,
    *,
    telegram_user_id: int,
    first_name: str | None = None,
    username: str | None = None,
    phone_number: str | None = None,
    preferred_name: str | None = None,
    admin_telegram_id: int | None = None,
    is_admin: bool | None = None,
    commit: bool = True,
) -> UserPreference:
    """Find by Telegram id, restore by phone, or create a UserPreference."""
    normalized_phone = normalize_phone_number(phone_number)
    admin_flag = bool(is_admin) or _is_admin_telegram_id(telegram_user_id, admin_telegram_id)
    result = await db.execute(
        select(UserPreference).where(
            or_(
                UserPreference.telegram_user_id == telegram_user_id,
                UserPreference.phone_number == normalized_phone if normalized_phone else False,
            )
        )
    )
    user = result.scalars().first()
    created = False
    if user is None:
        user = UserPreference(
            telegram_user_id=telegram_user_id,
            first_name=first_name,
            username=username,
            preferred_name=preferred_name,
            phone_number=normalized_phone,
            is_admin=admin_flag,
            account_status="active" if admin_flag else "pending_onboarding",
        )
        db.add(user)
        await db.flush() # Ensure user.id is populated
        await apply_starter_credit(db, user)

        # Automatically grant trial if configured
        from app.models import TrialConfig
        from app.services.trial_service import TrialService
        trial_config_res = await db.execute(select(TrialConfig).limit(1))
        trial_config = trial_config_res.scalar_one_or_none()
        if trial_config and trial_config.apply_automatically:
            try:
                await TrialService.grant_trial_subscription(db, user.id, reason="Automatically granted on signup")
            except Exception:
                # Don't break signup if trial fails
                pass

        created = True
    else:
        if getattr(user, "telegram_user_id", None) != telegram_user_id:
            user.telegram_user_id = telegram_user_id
        if first_name and getattr(user, "first_name", None) != first_name:
            user.first_name = first_name
        if username and getattr(user, "username", None) != username:
            user.username = username
        if preferred_name and getattr(user, "preferred_name", None) != preferred_name:
            user.preferred_name = preferred_name
        if normalized_phone and getattr(user, "phone_number", None) != normalized_phone:
            user.phone_number = normalized_phone
        if admin_flag and not getattr(user, "is_admin", False):
            user.is_admin = True
    mark_onboarding_state(user)
    if commit:
        await db.commit()
        await db.refresh(user)
    elif created:
        await db.flush()
    return user


async def update_contact_profile(
    db: AsyncSession,
    user: UserPreference,
    *,
    phone_number: str | None = None,
    preferred_name: str | None = None,
    commit: bool = True,
) -> UserPreference:
    normalized_phone = normalize_phone_number(phone_number) if phone_number is not None else None
    if phone_number is not None:
        user.phone_number = normalized_phone
    if preferred_name is not None:
        user.preferred_name = (preferred_name or "").strip() or None
    mark_onboarding_state(user)
    if commit:
        await db.commit()
        await db.refresh(user)
    return user
