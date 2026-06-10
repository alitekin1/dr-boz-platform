from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.models import CreditLedgerEntry, UserPreference

MICRO_USD_PER_USD = 1_000_000


@dataclass(frozen=True)
class WalletResult:
    ok: bool
    balance_minor: int
    balance_usd: float
    ledger_entry: Any | None = None
    reason: str | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def usd_to_minor(amount_usd: float | Decimal | str | None) -> int:
    value = Decimal(str(amount_usd or 0)) * Decimal(MICRO_USD_PER_USD)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def minor_to_usd(amount_minor: int | None) -> float:
    return float(Decimal(int(amount_minor or 0)) / Decimal(MICRO_USD_PER_USD))


def _wallet_model():
    return getattr(models, "Wallet", None)


def _ledger_model():
    return getattr(models, "WalletLedgerEntry", None) or getattr(models, "LedgerEntry", None)


def _wallet_balance_attr(wallet: Any) -> str | None:
    for name in ("available_minor", "balance_minor", "credit_balance_minor", "balance_amount_minor", "balance_cents"):
        if hasattr(wallet, name):
            return name
    return None


async def get_user(db: AsyncSession, user_id: int) -> UserPreference | None:
    return await db.get(UserPreference, user_id)


async def get_or_create_wallet(db: AsyncSession, user: UserPreference, *, commit: bool = False) -> Any | None:
    Wallet = _wallet_model()
    if Wallet is None:
        return None
    user_field = "user_id" if hasattr(Wallet, "user_id") else None
    if user_field is None:
        return None
    result = await db.execute(select(Wallet).where(getattr(Wallet, user_field) == user.id))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        kwargs = {user_field: user.id}
        if hasattr(Wallet, "balance_minor"):
            kwargs["balance_minor"] = usd_to_minor(getattr(user, "credit_balance_usd", 0.0))
        if hasattr(Wallet, "available_minor"):
            kwargs["available_minor"] = usd_to_minor(getattr(user, "credit_balance_usd", 0.0))
        elif hasattr(Wallet, "credit_balance_minor"):
            kwargs["credit_balance_minor"] = usd_to_minor(getattr(user, "credit_balance_usd", 0.0))
        wallet = Wallet(**kwargs)
        db.add(wallet)
        await db.flush()
        if commit:
            await db.commit()
            await db.refresh(wallet)
    return wallet


async def get_balance_minor(db: AsyncSession, user: UserPreference) -> int:
    wallet = await get_or_create_wallet(db, user)
    if wallet is not None:
        attr = _wallet_balance_attr(wallet)
        if attr:
            return max(0, int(getattr(wallet, attr) or 0))
    return max(0, usd_to_minor(getattr(user, "credit_balance_usd", 0.0)))


async def has_credit(db: AsyncSession, user: UserPreference, amount_minor: int) -> bool:
    if bool(getattr(user, "is_admin", False)):
        return True
    if amount_minor <= 0:
        return True
    return await get_balance_minor(db, user) >= amount_minor


def _new_wallet_ledger_entry(*, user_id: int, amount_minor: int, entry_type: str, reason: str | None, metadata: dict | None):
    Ledger = _ledger_model()
    if Ledger is None:
        return None
    kwargs = {}
    for key, value in {
        "user_id": user_id,
        "amount_minor": amount_minor,
        "amount_delta_minor": amount_minor,
        "entry_type": entry_type,
        "reason": reason,
        "metadata_json": metadata or {},
    }.items():
        if hasattr(Ledger, key):
            kwargs[key] = value
    return Ledger(**kwargs)


def _new_credit_ledger_entry(
    *,
    user_id: int,
    amount_minor: int,
    balance_after_minor: int | None,
    wallet: Any | None,
    entry_type: str,
    reason: str | None,
    metadata: dict | None,
):
    entry = CreditLedgerEntry(
        user_id=user_id,
        amount_delta_usd=minor_to_usd(amount_minor),
        entry_type=entry_type,
        reason=reason,
        metadata_json=metadata or {},
    )
    for key, value in {
        "wallet_id": getattr(wallet, "id", None),
        "amount_minor": amount_minor,
        "balance_after_minor": balance_after_minor,
        "available_after_minor": balance_after_minor,
        "held_after_minor": getattr(wallet, "held_minor", 0) if wallet is not None else 0,
        "currency": getattr(wallet, "currency", "USD") if wallet is not None else "USD",
        "direction": "credit" if amount_minor >= 0 else "debit",
        "status": "posted",
    }.items():
        if hasattr(entry, key):
            setattr(entry, key, value)
    return entry


async def apply_credit_delta(
    db: AsyncSession,
    *,
    user: UserPreference,
    amount_minor: int,
    entry_type: str,
    reason: str | None = None,
    metadata: dict | None = None,
    allow_negative: bool = False,
    commit: bool = True,
) -> WalletResult:
    """Apply a signed minor-unit delta, writing a ledger entry before committing balance changes."""
    amount_minor = int(amount_minor or 0)
    current = await get_balance_minor(db, user)
    if amount_minor < 0 and not allow_negative and current + amount_minor < 0 and not getattr(user, "is_admin", False):
        return WalletResult(False, current, minor_to_usd(current), reason="insufficient_credit")

    wallet = await get_or_create_wallet(db, user)
    new_balance = current + amount_minor
    ledger_entry = _new_wallet_ledger_entry(
        user_id=user.id,
        amount_minor=amount_minor,
        entry_type=entry_type,
        reason=reason,
        metadata=metadata,
    )
    if ledger_entry is None:
        ledger_entry = _new_credit_ledger_entry(
            user_id=user.id,
            amount_minor=amount_minor,
            balance_after_minor=new_balance,
            wallet=wallet,
            entry_type=entry_type,
            reason=reason,
            metadata=metadata,
        )
    db.add(ledger_entry)

    if wallet is not None:
        for attr in ("balance_minor", "available_minor"):
            if hasattr(wallet, attr):
                setattr(wallet, attr, new_balance)
        if hasattr(wallet, "version"):
            wallet.version = int(getattr(wallet, "version", 0) or 0) + 1
    if hasattr(user, "credit_balance_usd"):
        user.credit_balance_usd = minor_to_usd(new_balance)

    if commit:
        await db.commit()
        await db.refresh(user)
        try:
            await db.refresh(ledger_entry)
        except Exception:
            pass
    else:
        await db.flush()
    return WalletResult(True, max(0, new_balance), minor_to_usd(max(0, new_balance)), ledger_entry=ledger_entry)


async def credit(
    db: AsyncSession,
    *,
    user: UserPreference,
    amount_minor: int,
    entry_type: str = "credit",
    reason: str | None = None,
    metadata: dict | None = None,
    commit: bool = True,
) -> WalletResult:
    return await apply_credit_delta(
        db,
        user=user,
        amount_minor=abs(int(amount_minor or 0)),
        entry_type=entry_type,
        reason=reason,
        metadata=metadata,
        commit=commit,
    )


async def debit(
    db: AsyncSession,
    *,
    user: UserPreference,
    amount_minor: int,
    entry_type: str = "debit",
    reason: str | None = None,
    metadata: dict | None = None,
    commit: bool = True,
) -> WalletResult:
    if getattr(user, "is_admin", False):
        balance = await get_balance_minor(db, user)
        return WalletResult(True, balance, minor_to_usd(balance), reason="admin_bypass")
    return await apply_credit_delta(
        db,
        user=user,
        amount_minor=-abs(int(amount_minor or 0)),
        entry_type=entry_type,
        reason=reason,
        metadata=metadata,
        commit=commit,
    )


async def credit_usd(db: AsyncSession, *, user: UserPreference, amount_usd: float, **kwargs) -> WalletResult:
    return await credit(db, user=user, amount_minor=usd_to_minor(amount_usd), **kwargs)


async def debit_usd(db: AsyncSession, *, user: UserPreference, amount_usd: float, **kwargs) -> WalletResult:
    return await debit(db, user=user, amount_minor=usd_to_minor(amount_usd), **kwargs)
