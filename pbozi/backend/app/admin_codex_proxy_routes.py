from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from datetime import datetime, timezone, timedelta

from app.database import get_session
from app.models import CodexProxyRequestLog, CodexAccount

router = APIRouter(prefix="/api/admin/codex-proxy", tags=["admin-codex-proxy"])


@router.get("/requests")
async def list_proxy_requests(
    limit: int = 50,
    offset: int = 0,
    model: str | None = None,
    status: str | None = None,
    account_id: int | None = None,
    has_image: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    query = select(CodexProxyRequestLog)

    if model:
        query = query.where(CodexProxyRequestLog.model == model)
    if status:
        query = query.where(CodexProxyRequestLog.status == status)
    if account_id:
        query = query.where(CodexProxyRequestLog.account_id == account_id)
    if has_image is not None:
        query = query.where(CodexProxyRequestLog.has_image == has_image)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            query = query.where(CodexProxyRequestLog.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            query = query.where(CodexProxyRequestLog.created_at <= dt_to)
        except ValueError:
            pass

    query = query.order_by(desc(CodexProxyRequestLog.created_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "request_id": log.request_id,
            "model": log.model,
            "account_id": log.account_id,
            "status": log.status,
            "prompt_tokens": log.prompt_tokens,
            "completion_tokens": log.completion_tokens,
            "total_tokens": log.total_tokens,
            "duration_ms": log.duration_ms,
            "has_image": log.has_image,
            "image_count": log.image_count,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/stats")
async def get_proxy_stats(
    hours: int = 24,
    db: AsyncSession = Depends(get_session),
):
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)

    total_req = await db.execute(
        select(func.count(CodexProxyRequestLog.id)).where(CodexProxyRequestLog.created_at >= cutoff)
    )
    total_requests = total_req.scalar() or 0

    success_req = await db.execute(
        select(func.count(CodexProxyRequestLog.id)).where(
            CodexProxyRequestLog.created_at >= cutoff,
            CodexProxyRequestLog.status == "success",
        )
    )
    success_requests = success_req.scalar() or 0

    error_req = await db.execute(
        select(func.count(CodexProxyRequestLog.id)).where(
            CodexProxyRequestLog.created_at >= cutoff,
            CodexProxyRequestLog.status == "error",
        )
    )
    error_requests = error_req.scalar() or 0

    total_tokens = await db.execute(
        select(func.sum(CodexProxyRequestLog.total_tokens)).where(CodexProxyRequestLog.created_at >= cutoff)
    )
    total_tokens_sum = total_tokens.scalar() or 0

    prompt_tokens = await db.execute(
        select(func.sum(CodexProxyRequestLog.prompt_tokens)).where(CodexProxyRequestLog.created_at >= cutoff)
    )
    prompt_tokens_sum = prompt_tokens.scalar() or 0

    completion_tokens = await db.execute(
        select(func.sum(CodexProxyRequestLog.completion_tokens)).where(CodexProxyRequestLog.created_at >= cutoff)
    )
    completion_tokens_sum = completion_tokens.scalar() or 0

    avg_duration = await db.execute(
        select(func.avg(CodexProxyRequestLog.duration_ms)).where(CodexProxyRequestLog.created_at >= cutoff)
    )
    avg_duration_ms = avg_duration.scalar() or 0

    image_requests = await db.execute(
        select(func.count(CodexProxyRequestLog.id)).where(
            CodexProxyRequestLog.created_at >= cutoff,
            CodexProxyRequestLog.has_image == True,
        )
    )
    image_requests_count = image_requests.scalar() or 0

    by_model = await db.execute(
        select(CodexProxyRequestLog.model, func.count(CodexProxyRequestLog.id), func.sum(CodexProxyRequestLog.total_tokens))
        .where(CodexProxyRequestLog.created_at >= cutoff)
        .group_by(CodexProxyRequestLog.model)
    )
    model_stats = [{"model": row[0], "requests": row[1], "total_tokens": row[2] or 0} for row in by_model.all()]

    by_account = await db.execute(
        select(CodexProxyRequestLog.account_id, func.count(CodexProxyRequestLog.id), func.sum(CodexProxyRequestLog.total_tokens))
        .where(CodexProxyRequestLog.created_at >= cutoff)
        .group_by(CodexProxyRequestLog.account_id)
    )
    account_stats = [{"account_id": row[0], "requests": row[1], "total_tokens": row[2] or 0} for row in by_account.all()]

    return {
        "period_hours": hours,
        "total_requests": total_requests,
        "success_requests": success_requests,
        "error_requests": error_requests,
        "total_tokens": total_tokens_sum,
        "prompt_tokens": prompt_tokens_sum,
        "completion_tokens": completion_tokens_sum,
        "avg_duration_ms": round(avg_duration_ms, 1) if avg_duration_ms else 0,
        "image_requests": image_requests_count,
        "by_model": model_stats,
        "by_account": account_stats,
    }


@router.get("/accounts")
async def list_codex_accounts(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(CodexAccount).order_by(CodexAccount.id))
    accounts = result.scalars().all()
    return [
        {
            "id": acct.id,
            "label": acct.label,
            "auth_status": acct.auth_status,
            "is_active": acct.is_active,
            "status": acct.status,
            "five_hour_used": acct.five_hour_used,
            "five_hour_limit": acct.five_hour_limit,
            "weekly_used": acct.weekly_used,
            "weekly_limit": acct.weekly_limit,
            "last_used_at": acct.last_used_at.isoformat() if acct.last_used_at else None,
            "last_error": acct.last_error,
        }
        for acct in accounts
    ]


@router.get("/requests/{request_id}")
async def get_proxy_request(request_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(CodexProxyRequestLog).where(CodexProxyRequestLog.id == request_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(404, "Request log not found")
    return {
        "id": log.id,
        "request_id": log.request_id,
        "model": log.model,
        "account_id": log.account_id,
        "status": log.status,
        "prompt_tokens": log.prompt_tokens,
        "completion_tokens": log.completion_tokens,
        "total_tokens": log.total_tokens,
        "duration_ms": log.duration_ms,
        "has_image": log.has_image,
        "image_count": log.image_count,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
