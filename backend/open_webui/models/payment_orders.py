"""
Payment orders for the Bale bot flow.

Lifecycle:
  pending  -> the user clicked "buy" in the bot, awaiting payment
  awaiting_card -> user chose card-to-card, admin needs to verify receipt
  awaiting_invoice -> Bale sendInvoice was sent, waiting for pre_checkout
  paid     -> payment confirmed, subscription activated
  rejected -> admin rejected (card-to-card with bad/missing receipt)
  cancelled -> user cancelled

Stores both Open WebUI user.id (UUID) and Bale user.id so the bot can map
between the two without an extra DB hop.
"""

import secrets
import time
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession

from open_webui.internal.db import Base, get_async_db_context


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=True)
    bale_user_id = Column(String, nullable=True)
    plan_type = Column(String, nullable=True)
    amount_toman = Column(BigInteger, nullable=True)
    status = Column(String, default="pending")
    payment_method = Column(String, nullable=True)
    receipt_file_id = Column(String, nullable=True)
    admin_notes = Column(Text, nullable=True)
    subscription_id = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=True)
    updated_at = Column(BigInteger, nullable=True)


class PaymentOrderModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class PaymentOrderCreateForm(BaseModel):
    user_id: Optional[str] = None
    bale_user_id: Optional[str] = None
    plan_type: str
    amount_toman: int
    payment_method: Optional[str] = None
    receipt_file_id: Optional[str] = None


PaymentOrderTable = PaymentOrder.__table__


class PaymentOrders:
    @staticmethod
    async def create_order(
        user_id: str,
        bale_user_id: str,
        plan_type: str,
        amount_toman: int,
        payment_method: str = None,
        db: AsyncSession = None,
    ) -> PaymentOrderModel:
        order_id = str(uuid.uuid4())
        now = int(time.time())
        order = PaymentOrder(
            id=order_id,
            user_id=user_id,
            bale_user_id=bale_user_id,
            plan_type=plan_type,
            amount_toman=amount_toman,
            status="pending",
            payment_method=payment_method,
            created_at=now,
            updated_at=now,
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)
        return PaymentOrderModel.model_validate(order)

    @staticmethod
    async def get_order_by_id(order_id: str, db: AsyncSession = None) -> Optional[PaymentOrderModel]:
        result = await db.execute(
            select(PaymentOrder).where(PaymentOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if order:
            return PaymentOrderModel.model_validate(order)
        return None

    @staticmethod
    async def update_status(
        order_id: str,
        status: str,
        admin_notes: str = None,
        subscription_id: str = None,
        db: AsyncSession = None,
    ) -> Optional[PaymentOrderModel]:
        result = await db.execute(
            select(PaymentOrder).where(PaymentOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            return None
        order.status = status
        order.updated_at = int(time.time())
        if admin_notes:
            order.admin_notes = admin_notes
        if subscription_id:
            order.subscription_id = subscription_id
        await db.commit()
        await db.refresh(order)
        return PaymentOrderModel.model_validate(order)

    @staticmethod
    async def list_pending_card(db: AsyncSession = None) -> list[PaymentOrderModel]:
        result = await db.execute(
            select(PaymentOrder)
            .where(PaymentOrder.status == "awaiting_card")
            .order_by(PaymentOrder.created_at.desc())
        )
        orders = result.scalars().all()
        return [PaymentOrderModel.model_validate(o) for o in orders]

    @staticmethod
    async def list_orders_by_user(user_id: str, db: AsyncSession = None) -> list[PaymentOrderModel]:
        result = await db.execute(
            select(PaymentOrder)
            .where(PaymentOrder.user_id == user_id)
            .order_by(PaymentOrder.created_at.desc())
        )
        orders = result.scalars().all()
        return [PaymentOrderModel.model_validate(o) for o in orders]
