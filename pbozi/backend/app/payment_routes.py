import os
import uuid
import shutil
import asyncio
from datetime import datetime, timezone
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Security, UploadFile, File, Form
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import ADMIN_PASSWORD
from app.database import get_session
from app.models import PaymentMethod, PaymentRequest, UserPreference, AdminAction, TomanLedgerEntry, UserBillingAccount
from app.schemas import (
    PaymentMethodCreate,
    PaymentMethodUpdate,
    PaymentMethodOut,
    PaymentRequestCreate,
    PaymentRequestOut,
    PaymentRequestApprove,
    PaymentRequestReject,
)

router = APIRouter(tags=["payments"])
security = HTTPBearer(auto_error=False)


UPLOAD_DIR = Path("uploads/receipts")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def verify_admin(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not credentials or credentials.credentials.strip() != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


def _save_receipt(file: UploadFile) -> str:
    ext = Path(file.filename or "").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return str(file_path)


def _format_toman(amount: int) -> str:
    return f"{amount:,}"


async def _get_user_by_telegram(db: AsyncSession, telegram_user_id: int) -> UserPreference:
    user = (
        await db.execute(
            select(UserPreference).where(UserPreference.telegram_user_id == telegram_user_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")
    return user


async def _get_or_create_billing_account(db: AsyncSession, user: UserPreference) -> UserBillingAccount:
    account = (
        await db.execute(
            select(UserBillingAccount).where(UserBillingAccount.user_id == user.id)
        )
    ).scalar_one_or_none()
    if account is None:
        account = UserBillingAccount(user_id=user.id, currency="TOMAN")
        db.add(account)
        await db.flush()
    return account


async def _record_admin_action(db: AsyncSession, admin_user_id: int, action_type: str, target_type: str, target_id: int, reason: str, before: dict | None = None, after: dict | None = None):
    action = AdminAction(
        admin_user_id=admin_user_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        before_json=before,
        after_json=after,
    )
    db.add(action)
    await db.flush()
    return action


# ========================
# Admin Payment Methods
# ========================

@router.get("/api/admin/payment-methods", response_model=List[PaymentMethodOut])
async def list_payment_methods(_=Depends(verify_admin), db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(PaymentMethod).order_by(PaymentMethod.sort_order, PaymentMethod.id))
    return result.scalars().all()


@router.post("/api/admin/payment-methods", response_model=PaymentMethodOut)
async def create_payment_method(
    data: PaymentMethodCreate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    existing = (
        await db.execute(select(PaymentMethod).where(PaymentMethod.card_number == data.card_number))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="شماره کارت قبلاً ثبت شده است")
    method = PaymentMethod(**data.model_dump())
    db.add(method)
    await db.commit()
    await db.refresh(method)
    return method


@router.patch("/api/admin/payment-methods/{method_id}", response_model=PaymentMethodOut)
async def update_payment_method(
    method_id: int,
    data: PaymentMethodUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    method = (await db.execute(select(PaymentMethod).where(PaymentMethod.id == method_id))).scalar_one_or_none()
    if not method:
        raise HTTPException(status_code=404, detail="روش پرداخت یافت نشد")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(method, key, value)
    await db.commit()
    await db.refresh(method)
    return method


@router.delete("/api/admin/payment-methods/{method_id}")
async def delete_payment_method(
    method_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    method = (await db.execute(select(PaymentMethod).where(PaymentMethod.id == method_id))).scalar_one_or_none()
    if not method:
        raise HTTPException(status_code=404, detail="روش پرداخت یافت نشد")
    await db.delete(method)
    await db.commit()
    return {"ok": True}


# ========================
# Admin Payment Requests
# ========================

@router.get("/api/admin/payment-requests", response_model=List[PaymentRequestOut])
async def list_payment_requests(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    query = select(PaymentRequest).options(
        selectinload(PaymentRequest.user),
        selectinload(PaymentRequest.approver),
    ).order_by(desc(PaymentRequest.created_at)).limit(limit)
    if status:
        query = query.where(PaymentRequest.status == status)
    result = await db.execute(query)
    requests = result.scalars().all()
    out = []
    for req in requests:
        out.append(PaymentRequestOut(
            id=req.id,
            user_id=req.user_id,
            first_name=req.user.first_name if req.user else None,
            username=req.user.username if req.user else None,
            amount_toman=req.amount_toman,
            receipt_image_path=req.receipt_image_path,
            description=req.description,
            payment_type=getattr(req, "payment_type", "topup") or "topup",
            plan_id=getattr(req, "plan_id", None),
            status=req.status,
            admin_note=req.admin_note,
            approved_by=req.approved_by,
            approved_at=req.approved_at,
            created_at=req.created_at,
            updated_at=req.updated_at,
        ))
    return out


@router.get("/api/admin/payment-requests/{request_id}", response_model=PaymentRequestOut)
async def get_payment_request(
    request_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    req = (
        await db.execute(
            select(PaymentRequest).options(
                selectinload(PaymentRequest.user),
                selectinload(PaymentRequest.approver),
            ).where(PaymentRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="درخواست پرداخت یافت نشد")
    return PaymentRequestOut(
        id=req.id,
        user_id=req.user_id,
        first_name=req.user.first_name if req.user else None,
        username=req.user.username if req.user else None,
        amount_toman=req.amount_toman,
        receipt_image_path=req.receipt_image_path,
        description=req.description,
        payment_type=getattr(req, "payment_type", "topup") or "topup",
        plan_id=getattr(req, "plan_id", None),
        status=req.status,
        admin_note=req.admin_note,
        approved_by=req.approved_by,
        approved_at=req.approved_at,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


@router.post("/api/admin/payment-requests/{request_id}/approve", response_model=PaymentRequestOut)
async def approve_payment_request(
    request_id: int,
    data: PaymentRequestApprove = PaymentRequestApprove(),
    db: AsyncSession = Depends(get_session),
    admin_user=Depends(verify_admin),
):
    req = (
        await db.execute(
            select(PaymentRequest).options(selectinload(PaymentRequest.user)).where(PaymentRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="درخواست پرداخت یافت نشد")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="درخواست قبلاً بررسی شده است")
    if not req.user:
        raise HTTPException(status_code=404, detail="کاربر مرتبط یافت نشد")

    payment_type = getattr(req, "payment_type", "topup") or "topup"
    plan_id = getattr(req, "plan_id", None)

    if payment_type == "subscription" and plan_id:
        from app.models import SubscriptionPlan, UserSubscription
        from app.services.toman_billing_service import purchase_toman_subscription

        plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))).scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="پلن اشتراک یافت نشد")

        user = req.user
        idempotency_key = f"subscription:manual:{user.id}:{plan_id}:{req.id}"

        result = await purchase_toman_subscription(
            db,
            user=user,
            plan=plan,
            idempotency_key=idempotency_key,
            payment_confirmed=True,
            wallet_payment_toman=0,
            grant_gift_toman_balance=True,
        )

        if not result.ok:
            raise HTTPException(status_code=500, detail=f"خطا در فعال‌سازی اشتراک: {result.error}")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        req.status = "approved"
        req.admin_note = data.admin_note or req.admin_note
        req.approved_by = admin_user if isinstance(admin_user, int) else None
        req.approved_at = now

        await _record_admin_action(
            db,
            admin_user_id=(admin_user if isinstance(admin_user, int) else None),
            action_type="approve_subscription_payment",
            target_type="payment_request",
            target_id=req.id,
            reason=f"تأیید پرداخت اشتراک {plan.name} برای کاربر {user.id}",
            before={},
            after={"subscription_id": result.subscription.id if result.subscription else None},
        )
    else:
        user = req.user
        account = await _get_or_create_billing_account(db, user)

        before = {
            "paid_balance_toman": int(account.paid_balance_toman or 0),
            "total_paid_topup_toman": int(account.total_paid_topup_toman or 0),
        }

        account.paid_balance_toman = int(account.paid_balance_toman or 0) + req.amount_toman
        account.total_paid_topup_toman = int(account.total_paid_topup_toman or 0) + req.amount_toman
        account.version = int(account.version or 0) + 1

        ledger_entry = TomanLedgerEntry(
            user_id=user.id,
            billing_account_id=account.id,
            amount_toman=req.amount_toman,
            gift_delta_toman=0,
            paid_delta_toman=req.amount_toman,
            paid_balance_after_toman=int(account.paid_balance_toman or 0),
            entry_type="manual_payment",
            status="posted",
            reason="پرداخت دستی تأیید شده",
            metadata_json={
                "payment_request_id": req.id,
                "receipt_path": req.receipt_image_path,
            },
        )
        db.add(ledger_entry)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        req.status = "approved"
        req.admin_note = data.admin_note or req.admin_note
        req.approved_by = admin_user if isinstance(admin_user, int) else None
        req.approved_at = now

        await _record_admin_action(
            db,
            admin_user_id=(admin_user if isinstance(admin_user, int) else None),
            action_type="approve_payment",
            target_type="payment_request",
            target_id=req.id,
            reason=f"تأیید پرداخت {_format_toman(req.amount_toman)} تومان برای کاربر {user.id}",
            before=before,
            after={
                "paid_balance_toman": int(account.paid_balance_toman or 0),
                "total_paid_topup_toman": int(account.total_paid_topup_toman or 0),
            },
        )

    await db.commit()
    await db.refresh(req)

    payment_type = getattr(req, "payment_type", "topup") or "topup"
    user_telegram_id = req.user.telegram_user_id if req.user else None
    if user_telegram_id:
        try:
            from app.bot import notify_user_payment_result
            asyncio.create_task(notify_user_payment_result(
                user_telegram_id,
                approved=True,
                amount_toman=req.amount_toman,
                payment_type=payment_type,
            ))
        except Exception:
            pass

    return PaymentRequestOut(
        id=req.id,
        user_id=req.user_id,
        first_name=req.user.first_name if req.user else None,
        username=req.user.username if req.user else None,
        amount_toman=req.amount_toman,
        receipt_image_path=req.receipt_image_path,
        description=req.description,
        payment_type=getattr(req, "payment_type", "topup") or "topup",
        plan_id=getattr(req, "plan_id", None),
        status=req.status,
        admin_note=req.admin_note,
        approved_by=req.approved_by,
        approved_at=req.approved_at,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


@router.post("/api/admin/payment-requests/{request_id}/reject", response_model=PaymentRequestOut)
async def reject_payment_request(
    request_id: int,
    data: PaymentRequestReject,
    db: AsyncSession = Depends(get_session),
    admin_user=Depends(verify_admin),
):
    req = (await db.execute(select(PaymentRequest).options(selectinload(PaymentRequest.user)).where(PaymentRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="درخواست پرداخت یافت نشد")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="درخواست قبلاً بررسی شده است")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    req.status = "rejected"
    req.admin_note = data.admin_note
    req.approved_by = admin_user if isinstance(admin_user, int) else None
    req.approved_at = now

    await _record_admin_action(
        db,
        admin_user_id=(admin_user if isinstance(admin_user, int) else None),
        action_type="reject_payment",
        target_type="payment_request",
        target_id=req.id,
        reason=f"رد پرداخت {_format_toman(req.amount_toman)} تومان: {data.admin_note}",
    )

    await db.commit()
    await db.refresh(req)

    user_telegram_id = req.user.telegram_user_id if req.user else None
    if user_telegram_id:
        try:
            from app.bot import notify_user_payment_result
            asyncio.create_task(notify_user_payment_result(
                user_telegram_id,
                approved=False,
                amount_toman=req.amount_toman,
                payment_type=getattr(req, "payment_type", "topup") or "topup",
                admin_note=req.admin_note,
            ))
        except Exception:
            pass

    return PaymentRequestOut(
        id=req.id,
        user_id=req.user_id,
        first_name=req.user.first_name if req.user else None,
        username=req.user.username if req.user else None,
        amount_toman=req.amount_toman,
        receipt_image_path=req.receipt_image_path,
        description=req.description,
        payment_type=getattr(req, "payment_type", "topup") or "topup",
        plan_id=getattr(req, "plan_id", None),
        status=req.status,
        admin_note=req.admin_note,
        approved_by=req.approved_by,
        approved_at=req.approved_at,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


# ========================
# User Payment Methods (public)
# ========================

@router.get("/api/user/payment-methods", response_model=List[PaymentMethodOut])
async def get_active_payment_methods(db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(PaymentMethod).where(PaymentMethod.is_active == True).order_by(PaymentMethod.sort_order, PaymentMethod.id)
    )
    return result.scalars().all()


# ========================
# User Payment Requests
# ========================

@router.post("/api/user/payment-requests", response_model=PaymentRequestOut)
async def create_payment_request(
    telegram_user_id: int,
    amount_toman: int = Form(...),
    description: Optional[str] = Form(None),
    receipt: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    user = await _get_user_by_telegram(db, telegram_user_id)

    if amount_toman <= 0:
        raise HTTPException(status_code=400, detail="مبلغ باید بیشتر از صفر باشد")

    receipt_path = _save_receipt(receipt)

    request = PaymentRequest(
        user_id=user.id,
        amount_toman=amount_toman,
        receipt_image_path=receipt_path,
        description=description,
        status="pending",
        payment_type="topup",
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)

    try:
        from app.transactions_bot import send_new_payment_notification
        asyncio.create_task(send_new_payment_notification(request.id))
    except Exception as e:
        pass

    return PaymentRequestOut(
        id=request.id,
        user_id=request.user_id,
        first_name=user.first_name,
        username=user.username,
        amount_toman=request.amount_toman,
        receipt_image_path=request.receipt_image_path,
        description=request.description,
        payment_type=getattr(request, "payment_type", "topup") or "topup",
        plan_id=getattr(request, "plan_id", None),
        status=request.status,
        admin_note=request.admin_note,
        approved_by=request.approved_by,
        approved_at=request.approved_at,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


@router.get("/api/user/payment-requests", response_model=List[PaymentRequestOut])
async def get_user_payment_requests(
    telegram_user_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
):
    user = await _get_user_by_telegram(db, telegram_user_id)
    result = await db.execute(
        select(PaymentRequest)
        .where(PaymentRequest.user_id == user.id)
        .order_by(desc(PaymentRequest.created_at))
        .limit(limit)
    )
    requests = result.scalars().all()
    return [
        PaymentRequestOut(
            id=r.id,
            user_id=r.user_id,
            first_name=user.first_name,
            username=user.username,
            amount_toman=r.amount_toman,
            receipt_image_path=r.receipt_image_path,
            description=r.description,
            payment_type=getattr(r, "payment_type", "topup") or "topup",
            plan_id=getattr(r, "plan_id", None),
            status=r.status,
            admin_note=r.admin_note,
            approved_by=r.approved_by,
            approved_at=r.approved_at,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in requests
    ]
