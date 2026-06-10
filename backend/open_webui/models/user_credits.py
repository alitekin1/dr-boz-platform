import time
import uuid
from typing import Optional
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from open_webui.internal.db import Base, get_async_db_context
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    BigInteger,
    Column,
    String,
    Integer,
)

####################
# User Credits DB Schema
####################


class UserCredits(Base):
    __tablename__ = 'user_credits'

    user_id = Column(String, primary_key=True)
    balance = Column(Integer, default=0)
    total_used = Column(Integer, default=0)
    reset_date = Column(BigInteger, nullable=True)


class CreditTransaction(Base):
    __tablename__ = 'credit_transaction'

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    reference = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class UserCreditsModel(BaseModel):
    user_id: str
    balance: int = 0
    total_used: int = 0
    reset_date: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CreditTransactionModel(BaseModel):
    id: str
    user_id: str
    amount: int
    type: str
    reference: Optional[str] = None
    created_at: int

    model_config = ConfigDict(from_attributes=True)


class CreditsTable:
    async def get_user_credits(
        self, user_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[UserCreditsModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(UserCredits).filter_by(user_id=user_id))
            credits = result.scalars().first()
            if not credits:
                now = int(time.time())
                new_credits = UserCredits(
                    user_id=user_id,
                    balance=50,
                    total_used=0,
                    reset_date=now + 30 * 24 * 3600,
                )
                db.add(new_credits)
                await db.commit()
                await db.refresh(new_credits)
                return UserCreditsModel.model_validate(new_credits)
            return UserCreditsModel.model_validate(credits)

    async def deduct_credit(
        self, user_id: str, amount: int = 1, reference: str = '',
        db: Optional[AsyncSession] = None,
    ) -> bool:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(UserCredits).filter_by(user_id=user_id))
            credits = result.scalars().first()
            if not credits:
                return False
            if credits.balance < amount:
                return False

            credits.balance -= amount
            credits.total_used += amount

            now = int(time.time())
            tx = CreditTransaction(
                id=str(uuid.uuid4()),
                user_id=user_id,
                amount=-amount,
                type='usage',
                reference=reference,
                created_at=now,
            )
            db.add(tx)
            await db.commit()
            return True

    async def add_credits(
        self, user_id: str, amount: int, type: str = 'purchase',
        reference: str = '', db: Optional[AsyncSession] = None,
    ) -> Optional[UserCreditsModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(UserCredits).filter_by(user_id=user_id))
            credits = result.scalars().first()
            if not credits:
                now = int(time.time())
                credits = UserCredits(
                    user_id=user_id,
                    balance=amount,
                    total_used=0,
                    reset_date=now + 30 * 24 * 3600,
                )
                db.add(credits)
                await db.commit()
                await db.refresh(credits)
            else:
                credits.balance += amount

            now = int(time.time())
            tx = CreditTransaction(
                id=str(uuid.uuid4()),
                user_id=user_id,
                amount=amount,
                type=type,
                reference=reference,
                created_at=now,
            )
            db.add(tx)
            await db.commit()
            return UserCreditsModel.model_validate(credits)

    async def get_transaction_history(
        self, user_id: str, skip: int = 0, limit: int = 20,
        db: Optional[AsyncSession] = None,
    ) -> list[CreditTransactionModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(
                select(CreditTransaction)
                .filter_by(user_id=user_id)
                .order_by(CreditTransaction.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
            txs = result.scalars().all()
            return [CreditTransactionModel.model_validate(tx) for tx in txs]

    async def check_and_reset_monthly(
        self, user_id: str, db: Optional[AsyncSession] = None,
    ) -> Optional[UserCreditsModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(UserCredits).filter_by(user_id=user_id))
            credits = result.scalars().first()
            if not credits:
                return None
            now = int(time.time())
            if credits.reset_date and now >= credits.reset_date:
                credits.balance = 50
                credits.total_used = 0
                credits.reset_date = now + 30 * 24 * 3600
                await db.commit()
                await db.refresh(credits)
            return UserCreditsModel.model_validate(credits)


Credits = CreditsTable()
