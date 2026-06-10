import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from open_webui.internal.db import get_async_session
from open_webui.models.users import Users
from open_webui.models.subscriptions import (
    Subscriptions,
    SubscriptionModel,
    SubscriptionForm,
)
from open_webui.utils.auth import get_verified_user, get_admin_user

log = logging.getLogger(__name__)
router = APIRouter()

############################
# GET /status
# Return current user's subscription
############################


@router.get('/status', response_model=dict)
async def get_subscription_status(
    user=Depends(get_verified_user),
    db: AsyncSession = Depends(get_async_session),
):
    sub = await Subscriptions.get_subscription_by_user_id(user.id, db=db)
    if not sub:
        return {
            'plan': 'free',
            'status': 'active',
            'expires_at': None,
            'payment_provider': None,
        }
    return {
        'plan': sub.plan,
        'status': sub.status,
        'expires_at': sub.expires_at,
        'payment_provider': sub.payment_provider,
    }


############################
# Admin endpoints
############################


@router.get('/admin/list', response_model=list[SubscriptionModel])
async def list_subscriptions(
    skip: int = 0,
    limit: int = 50,
    user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_async_session),
):
    return await Subscriptions.get_all_subscriptions(skip=skip, limit=limit, db=db)


@router.post('/admin/create', response_model=SubscriptionModel)
async def create_subscription(
    request: Request,
    user=Depends(get_admin_user),
    db: AsyncSession = Depends(get_async_session),
):
    body = await request.json()
    user_id = body.get('user_id')
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='user_id is required',
        )

    form_data = SubscriptionForm(
        plan=body.get('plan', 'free'),
        status=body.get('status', 'active'),
        payment_provider=body.get('payment_provider'),
        payment_id=body.get('payment_id'),
        expires_at=body.get('expires_at'),
    )
    return await Subscriptions.create_or_update_subscription(user_id, form_data, db=db)
