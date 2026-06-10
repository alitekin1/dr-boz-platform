from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PromoCode, PromoCodeRedemption, TomanLedgerEntry, UserPreference
from app.services.toman_billing_service import get_or_create_billing_account
from app.services.wallet_service import apply_credit_delta, minor_to_usd, usd_to_minor


class PromoCodeRedemptionError(ValueError):
    pass


def normalize_promo_code(code: str | None) -> str:
    value = (code or "").strip().upper().replace(" ", "")
    return value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _bonus_minor(promo_code: PromoCode, charge_minor: int) -> int:
    if promo_code.bonus_type == "percent":
        return max(0, int(round(charge_minor * float(promo_code.bonus_value_usd or 0.0) / 100.0)))
    return max(0, usd_to_minor(float(promo_code.bonus_value_usd or 0.0)))


def _bonus_toman(promo_code: PromoCode, charge_toman: int) -> int:
    if promo_code.bonus_type == "percent":
        return max(0, int(round(charge_toman * float(promo_code.bonus_value_toman or 0.0) / 100.0)))
    return max(0, int(promo_code.bonus_value_toman or 0))


async def redeem_promo_code_for_user(
    db: AsyncSession,
    *,
    user: UserPreference,
    code: str,
    charge_amount_usd: float = 0.0,
    charge_amount_toman: int = 0,
    source: str = "account",
    credit_charge_amount: bool = True,
) -> PromoCodeRedemption:
    normalized_code = normalize_promo_code(code)
    if not normalized_code:
        raise PromoCodeRedemptionError("code is required")

    promo_code = (await db.execute(select(PromoCode).where(PromoCode.code == normalized_code))).scalar_one_or_none()
    if promo_code is None or not bool(promo_code.is_active):
        raise PromoCodeRedemptionError("promo code is invalid or inactive")

    expires_at = _as_utc(promo_code.expires_at)
    if expires_at is not None and expires_at <= _utcnow():
        raise PromoCodeRedemptionError("promo code has expired")

    total_redemptions = int(
        (
            await db.execute(
                select(func.count(PromoCodeRedemption.id)).where(PromoCodeRedemption.promo_code_id == promo_code.id)
            )
        ).scalar_one_or_none()
        or 0
    )
    if promo_code.max_redemptions_total is not None and total_redemptions >= int(promo_code.max_redemptions_total):
        raise PromoCodeRedemptionError("promo code redemption limit reached")

    user_redemptions = int(
        (
            await db.execute(
                select(func.count(PromoCodeRedemption.id)).where(
                    PromoCodeRedemption.promo_code_id == promo_code.id,
                    PromoCodeRedemption.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        or 0
    )
    if int(promo_code.max_redemptions_per_user or 0) > 0 and user_redemptions >= int(promo_code.max_redemptions_per_user):
        raise PromoCodeRedemptionError("you have already used this promo code")

    is_toman = (promo_code.currency or "USD") == "TOMAN"

    if is_toman:
        minimum_charge_toman = int(promo_code.minimum_charge_toman or 0)
        if charge_amount_toman < minimum_charge_toman:
            raise PromoCodeRedemptionError(
                f"minimum charge for this code is {minimum_charge_toman:,} تومان"
            )

        bonus_toman = _bonus_toman(promo_code, charge_amount_toman)
        if bonus_toman <= 0:
            raise PromoCodeRedemptionError("promo code bonus is zero for this charge amount")

        credited_charge_toman = charge_amount_toman if credit_charge_amount else 0
        total_credit_toman = credited_charge_toman + bonus_toman
        if total_credit_toman <= 0:
            raise PromoCodeRedemptionError("total credit amount is invalid")

        account = await get_or_create_billing_account(db, user)
        account.gift_balance_toman = int(account.gift_balance_toman or 0) + total_credit_toman
        account.total_gift_granted_toman = int(account.total_gift_granted_toman or 0) + total_credit_toman
        account.version = int(account.version or 0) + 1

        ledger_entry = TomanLedgerEntry(
            user_id=user.id,
            billing_account_id=account.id,
            amount_toman=total_credit_toman,
            gift_delta_toman=total_credit_toman,
            paid_delta_toman=0,
            gift_balance_after_toman=account.gift_balance_toman,
            paid_balance_after_toman=account.paid_balance_toman,
            entry_type="promo_code_credit",
            reason=f"promo code {promo_code.code}",
            metadata_json={
                "promo_code_id": promo_code.id,
                "promo_code": promo_code.code,
                "charge_amount_toman": charge_amount_toman,
                "credited_charge_amount_toman": credited_charge_toman,
                "bonus_amount_toman": bonus_toman,
                "credit_charge_amount": bool(credit_charge_amount),
                "source": source,
            },
        )
        db.add(ledger_entry)

        redemption = PromoCodeRedemption(
            promo_code_id=promo_code.id,
            user_id=user.id,
            charge_amount_usd=0.0,
            charge_amount_toman=charge_amount_toman,
            bonus_amount_usd=0.0,
            bonus_amount_toman=bonus_toman,
            total_credit_usd=0.0,
            total_credit_toman=total_credit_toman,
            credit_ledger_entry_id=None,
            toman_ledger_entry_id=None,
        )
        db.add(redemption)
        await db.commit()
        await db.refresh(ledger_entry)
        await db.refresh(redemption)
        redemption.toman_ledger_entry_id = ledger_entry.id
        await db.commit()
        await db.refresh(redemption)
        return redemption

    else:
        charge_minor = usd_to_minor(charge_amount_usd)
        if charge_minor < 0:
            raise PromoCodeRedemptionError("charge_amount must be zero or greater")

        minimum_charge_minor = usd_to_minor(float(promo_code.minimum_charge_usd or 0.0))
        if charge_minor < minimum_charge_minor:
            raise PromoCodeRedemptionError(
                f"minimum charge for this code is ${float(promo_code.minimum_charge_usd or 0.0):.2f}"
            )

        bonus_minor = _bonus_minor(promo_code, charge_minor)
        if bonus_minor <= 0:
            raise PromoCodeRedemptionError("promo code bonus is zero for this charge amount")

        credited_charge_minor = charge_minor if credit_charge_amount else 0
        total_credit_minor = credited_charge_minor + bonus_minor
        if total_credit_minor <= 0:
            raise PromoCodeRedemptionError("total credit amount is invalid")

        wallet_result = await apply_credit_delta(
            db,
            user=user,
            amount_minor=total_credit_minor,
            entry_type="promo_code_credit",
            reason=f"promo code {promo_code.code}",
            metadata={
                "promo_code_id": promo_code.id,
                "promo_code": promo_code.code,
                "charge_amount_minor": charge_minor,
                "credited_charge_amount_minor": credited_charge_minor,
                "bonus_amount_minor": bonus_minor,
                "credit_charge_amount": bool(credit_charge_amount),
                "source": source,
            },
            commit=False,
        )
        if not wallet_result.ok:
            raise PromoCodeRedemptionError(wallet_result.reason or "failed to apply promo credit")

        if charge_amount_usd > 0:
            user.total_charged_usd = (user.total_charged_usd or 0.0) + charge_amount_usd
            if user.total_charged_usd >= 1.0:
                user.is_pro = True

        redemption = PromoCodeRedemption(
            promo_code_id=promo_code.id,
            user_id=user.id,
            charge_amount_usd=minor_to_usd(charge_minor),
            charge_amount_toman=0,
            bonus_amount_usd=minor_to_usd(bonus_minor),
            bonus_amount_toman=0,
            total_credit_usd=minor_to_usd(total_credit_minor),
            total_credit_toman=0,
            credit_ledger_entry_id=getattr(wallet_result.ledger_entry, "id", None),
            toman_ledger_entry_id=None,
        )
        db.add(redemption)
        await db.commit()
        await db.refresh(redemption)
        return redemption
