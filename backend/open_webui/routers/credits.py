import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from open_webui.internal.db import get_async_session
from open_webui.models.users import Users
from open_webui.models.user_credits import Credits, UserCreditsModel
from open_webui.utils.auth import get_verified_user

log = logging.getLogger(__name__)
router = APIRouter()

############################
# GET /status
# Return current user's credit balance + usage
############################


@router.get('/status', response_model=dict)
async def get_credits_status(
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    credits = await Credits.check_and_reset_monthly(user.id, db=db)
    if not credits:
        return {
            'balance': 0,
            'total_used': 0,
            'reset_date': None,
        }
    return {
        'balance': credits.balance,
        'total_used': credits.total_used,
        'reset_date': credits.reset_date,
    }


############################
# GET /history
# Return transaction history
############################


@router.get('/history', response_model=dict)
async def get_credits_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    transactions = await Credits.get_transaction_history(
        user.id, skip=skip, limit=limit, db=db
    )
    return {
        'transactions': [
            {
                'id': tx.id,
                'amount': tx.amount,
                'type': tx.type,
                'reference': tx.reference,
                'created_at': tx.created_at,
            }
            for tx in transactions
        ],
    }
