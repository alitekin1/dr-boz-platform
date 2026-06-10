"""
Billing router for the Bale-bot payment flow.

Auth model
----------
All endpoints under this router require a shared-secret header
`X-Bot-Secret: <BOT_SHARED_SECRET>`. The bot stores this secret in its
.env and sends it on every service-to-service call.

For the admin endpoints we additionally require `X-Bot-Admin-Id: <id>`
that must appear in the configured `BOT_ADMIN_IDS` env (comma separated).

Public endpoints (no auth) under `/billing/public/...` return plan info
and a phone->user_id lookup helper for the bot.
"""

import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from open_webui.internal.db import get_async_session
from open_webui.models.era_db import SubscriptionPlan
from open_webui.models.payment_orders import (
    PaymentOrders,
    PaymentOrderCreateForm,
    PaymentOrderModel,
)
from open_webui.models.subscriptions import Subscriptions, SubscriptionForm
from open_webui.models.users import Users
from open_webui.utils.era_db import get_era_session_factory, is_era_db_available

log = logging.getLogger(__name__)
router = APIRouter()

BOT_SHARED_SECRET = os.environ.get("BOT_SHARED_SECRET", "").strip()
BOT_ADMIN_IDS = {
    x.strip()
    for x in os.environ.get("BOT_ADMIN_IDS", "").split(",")
    if x.strip()
}


# ── Auth dependencies ──────────────────────────────────────────


def _require_bot_secret(x_bot_secret: str = Header(...)):
    if not BOT_SHARED_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot shared secret not configured on server",
        )
    if x_bot_secret != BOT_SHARED_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bot credentials",
        )
    return x_bot_secret


def _require_bot_admin(
    x_bot_secret: str = Depends(_require_bot_secret),
    x_bot_admin_id: str = Header(...),
):
    if not BOT_ADMIN_IDS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No bot admins configured",
        )
    if x_bot_admin_id not in BOT_ADMIN_IDS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privilege required",
        )
    return x_bot_admin_id


# ── Pydantic schemas ───────────────────────────────────────────


class PlanOut(BaseModel):
    id: int
    name: Optional[str] = None
    plan_type: Optional[str] = None
    monthly_price_toman: Optional[int] = None
    gift_credit_toman: Optional[int] = None
    cooldown_limit_toman: Optional[int] = None
    weekly_limit_toman: Optional[int] = None


class UserLookupOut(BaseModel):
    user_id: Optional[str] = None
    found: bool = False


class VerifyInitDataIn(BaseModel):
    initData: str


class VerifyInitDataOut(BaseModel):
    valid: bool = False
    user_id: Optional[str] = None
    bale_user_id: Optional[str] = None


class OrderOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    bale_user_id: Optional[str] = None
    plan_type: Optional[str] = None
    amount_toman: Optional[int] = None
    status: str = "pending"
    payment_method: Optional[str] = None
    receipt_file_id: Optional[str] = None
    admin_notes: Optional[str] = None
    subscription_id: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None


class CreateOrderIn(BaseModel):
    user_id: str
    bale_user_id: Optional[str] = None
    plan_type: str
    amount_toman: int
    payment_method: Optional[str] = None
    receipt_file_id: Optional[str] = None


class AdminCreateOrderIn(BaseModel):
    user_id: str
    bale_user_id: Optional[str] = None
    plan_type: str
    amount_toman: int


# ── Public endpoints ───────────────────────────────────────────


@router.get("/public/plans", response_model=list[PlanOut])
async def list_plans():
    if not is_era_db_available():
        return []
    era_factory = get_era_session_factory()
    async with era_factory() as era_db:
        result = await era_db.execute(select(SubscriptionPlan))
        plans = result.scalars().all()
        return [
            PlanOut(
                id=p.id,
                name=p.name,
                plan_type=p.plan_type,
                monthly_price_toman=p.monthly_price_toman,
                gift_credit_toman=p.gift_credit_toman,
                cooldown_limit_toman=p.cooldown_limit_toman,
                weekly_limit_toman=p.weekly_limit_toman,
            )
            for p in plans
        ]


@router.get("/public/lookup-by-phone", response_model=UserLookupOut)
async def lookup_user_by_phone(
    phone: str,
    db: AsyncSession = Depends(get_async_session),
):
    user = await Users.get_user_by_phone(phone, db=db)
    if user:
        return UserLookupOut(user_id=user.id, found=True)
    return UserLookupOut(found=False)


@router.post("/public/verify-initdata", response_model=VerifyInitDataOut)
async def verify_bale_initdata(
    body: VerifyInitDataIn,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
):
    from open_webui.utils.bale_auth import verify_init_data

    valid = verify_init_data(body.initData)
    if not valid:
        return VerifyInitDataOut(valid=False)

    user_info = verify_init_data(body.initData, extract_user=True)
    bale_user_id = str(user_info.get("id", ""))

    user = await Users.get_user_by_oauth_sub(f"bale_{bale_user_id}", db=db)
    if user:
        return VerifyInitDataOut(valid=True, user_id=user.id, bale_user_id=bale_user_id)
    return VerifyInitDataOut(valid=True, bale_user_id=bale_user_id)


# ── Order endpoints (bot auth) ──────────────────────────────────


@router.post("/orders", response_model=OrderOut, dependencies=[Depends(_require_bot_secret)])
async def create_order(
    body: CreateOrderIn,
    db: AsyncSession = Depends(get_async_session),
):
    order = await PaymentOrders.create_order(
        user_id=body.user_id,
        bale_user_id=body.bale_user_id or "",
        plan_type=body.plan_type,
        amount_toman=body.amount_toman,
        payment_method=body.payment_method,
        db=db,
    )
    return order


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: str,
    x_bot_secret: str = Depends(_require_bot_secret),
    db: AsyncSession = Depends(get_async_session),
):
    order = await PaymentOrders.get_order_by_id(order_id, db=db)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/orders/{order_id}/mark-paid", response_model=OrderOut, dependencies=[Depends(_require_bot_secret)])
async def mark_paid(
    order_id: str,
    db: AsyncSession = Depends(get_async_session),
):
    order = await PaymentOrders.update_status(order_id, "paid", db=db)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Activate subscription when order is paid
    if order.plan_type:
        form = SubscriptionForm(
            plan=order.plan_type,
            status="active",
            payment_provider="bale",
            payment_id=order_id,
        )
        subscription = await Subscriptions.create_or_update_subscription(
            order.user_id, form, db=db
        )
        if subscription:
            await PaymentOrders.update_status(
                order_id, "paid", subscription_id=subscription.id, db=db
            )
            order = await PaymentOrders.get_order_by_id(order_id, db=db)

    return order


@router.post("/orders/{order_id}/reject", response_model=OrderOut, dependencies=[Depends(_require_bot_secret)])
async def reject_order(
    order_id: str,
    db: AsyncSession = Depends(get_async_session),
):
    order = await PaymentOrders.update_status(order_id, "rejected", db=db)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/orders/{order_id}/cancel", response_model=OrderOut, dependencies=[Depends(_require_bot_secret)])
async def cancel_order(
    order_id: str,
    db: AsyncSession = Depends(get_async_session),
):
    order = await PaymentOrders.update_status(order_id, "cancelled", db=db)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ── Admin endpoints ─────────────────────────────────────────────


@router.post("/admin/orders", response_model=OrderOut)
async def admin_create_order(
    body: AdminCreateOrderIn,
    admin_id: str = Depends(_require_bot_admin),
    db: AsyncSession = Depends(get_async_session),
):
    order = await PaymentOrders.create_order(
        user_id=body.user_id,
        bale_user_id=body.bale_user_id or "",
        plan_type=body.plan_type,
        amount_toman=body.amount_toman,
        payment_method="admin",
        db=db,
    )
    return order


@router.get("/admin/orders/pending-card", response_model=list[OrderOut])
async def admin_list_pending_card(
    admin_id: str = Depends(_require_bot_admin),
    db: AsyncSession = Depends(get_async_session),
):
    return await PaymentOrders.list_pending_card(db=db)


@router.post("/admin/orders/{order_id}/approve", response_model=OrderOut)
async def admin_approve(
    order_id: str,
    admin_id: str = Depends(_require_bot_admin),
    db: AsyncSession = Depends(get_async_session),
):
    order = await PaymentOrders.get_order_by_id(order_id, db=db)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order = await PaymentOrders.update_status(order_id, "paid", admin_notes=f"Approved by admin {admin_id}", db=db)

    # Activate subscription
    if order and order.plan_type:
        form = SubscriptionForm(
            plan=order.plan_type,
            status="active",
            payment_provider="card",
            payment_id=order_id,
        )
        subscription = await Subscriptions.create_or_update_subscription(
            order.user_id, form, db=db
        )
        if subscription:
            await PaymentOrders.update_status(
                order_id, "paid", subscription_id=subscription.id, db=db
            )
            order = await PaymentOrders.get_order_by_id(order_id, db=db)

    return order


@router.post("/admin/orders/{order_id}/reject", response_model=OrderOut)
async def admin_reject(
    order_id: str,
    admin_id: str = Depends(_require_bot_admin),
    db: AsyncSession = Depends(get_async_session),
):
    order = await PaymentOrders.update_status(
        order_id, "rejected", admin_notes=f"Rejected by admin {admin_id}", db=db
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
