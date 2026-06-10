import time
from typing import Optional
from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from open_webui.internal.db import Base, get_async_db_context
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    BigInteger,
    Column,
    String,
    Text,
)

####################
# Subscription DB Schema
####################


class Subscription(Base):
    __tablename__ = 'subscription'

    id = Column(String, primary_key=True, unique=True)
    user_id = Column(String, nullable=False)
    plan = Column(String, nullable=False, default='free')
    status = Column(String, nullable=False, default='active')
    payment_provider = Column(String, nullable=True)
    payment_id = Column(String, nullable=True)
    started_at = Column(BigInteger, nullable=False)
    expires_at = Column(BigInteger, nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class SubscriptionModel(BaseModel):
    id: str
    user_id: str
    plan: str = 'free'
    status: str = 'active'
    payment_provider: Optional[str] = None
    payment_id: Optional[str] = None
    started_at: int
    expires_at: Optional[int] = None
    created_at: int
    updated_at: int

    model_config = ConfigDict(from_attributes=True)


class SubscriptionForm(BaseModel):
    plan: str
    status: Optional[str] = 'active'
    payment_provider: Optional[str] = None
    payment_id: Optional[str] = None
    expires_at: Optional[int] = None


class SubscriptionTable:
    async def get_subscription_by_user_id(
        self, user_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[SubscriptionModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(
                select(Subscription).filter_by(user_id=user_id, status='active')
            )
            sub = result.scalars().first()
            return SubscriptionModel.model_validate(sub) if sub else None

    async def create_or_update_subscription(
        self, user_id: str, form_data: SubscriptionForm, db: Optional[AsyncSession] = None
    ) -> Optional[SubscriptionModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(Subscription).filter_by(user_id=user_id, status='active'))
            existing = result.scalars().first()

            now = int(time.time())
            if existing:
                existing.plan = form_data.plan
                existing.status = form_data.status or 'active'
                existing.payment_provider = form_data.payment_provider
                existing.payment_id = form_data.payment_id
                existing.expires_at = form_data.expires_at
                existing.updated_at = now
                await db.commit()
                await db.refresh(existing)
                return SubscriptionModel.model_validate(existing)
            else:
                import uuid
                new_sub = Subscription(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    plan=form_data.plan,
                    status=form_data.status or 'active',
                    payment_provider=form_data.payment_provider,
                    payment_id=form_data.payment_id,
                    started_at=now,
                    expires_at=form_data.expires_at,
                    created_at=now,
                    updated_at=now,
                )
                db.add(new_sub)
                await db.commit()
                await db.refresh(new_sub)
                return SubscriptionModel.model_validate(new_sub)

    async def get_all_subscriptions(
        self,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
        db: Optional[AsyncSession] = None,
    ) -> list[SubscriptionModel]:
        async with get_async_db_context(db) as db:
            stmt = select(Subscription).order_by(Subscription.created_at.desc())
            if skip is not None:
                stmt = stmt.offset(skip)
            if limit is not None:
                stmt = stmt.limit(limit)
            result = await db.execute(stmt)
            subs = result.scalars().all()
            return [SubscriptionModel.model_validate(s) for s in subs]


Subscriptions = SubscriptionTable()
