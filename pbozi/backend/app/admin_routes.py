import httpx
import csv
import io
import json
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.inspection import inspect as sa_inspect

from fastapi import APIRouter, Depends, HTTPException, Query, Security, UploadFile, File, Form
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import app.models as app_models
import app.schemas as app_schemas
from app.config import ADMIN_PASSWORD
from app.database import get_session
from app.llm import (
    AUTO_ROUTER_CONFIG_KEY,
    AUTO_ROUTER_MODEL_TYPE,
    BUILTIN_TOOLS,
    NORMAL_MODEL_TYPE,
    ensure_builtin_tools,
    validate_auto_router_config,
)
from app.services.telegram_bot_runtime import get_bot_status, start_bot, stop_bot
from app.services.promo_code_service import PromoCodeRedemptionError, normalize_promo_code, redeem_promo_code_for_user
from app.services.prompt_service import PromptService
from app.services.codex_runtime import (
    CODEX_SUBSCRIPTION_PROVIDER_KIND,
    CODEX_MODEL_PRESETS,
    build_codex_home,
    build_codex_login_command,
    check_codex_login_status,
    ensure_codex_home,
    normalize_provider_kind,
    refresh_codex_limit_status,
)

ZAL_MODEL_PRESETS = [
    {
        "name": "gpt-5.5",
        "display_name": "GPT-5.5 (ZAL Multimodal)",
        "pricing_input": 0.0,
        "pricing_output": 0.0,
        "context_window": 128000,
    },
    {
        "name": "gpt-5.4",
        "display_name": "GPT-5.4 (ZAL)",
        "pricing_input": 0.0,
        "pricing_output": 0.0,
        "context_window": 128000,
    },
    {
        "name": "gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini (ZAL)",
        "pricing_input": 0.0,
        "pricing_output": 0.0,
        "context_window": 128000,
    },
    {
        "name": "gpt-5.3-codex",
        "display_name": "GPT-5.3 Codex (ZAL)",
        "pricing_input": 0.0,
        "pricing_output": 0.0,
        "context_window": 128000,
    },
]
from app.services.trial_service import TrialService, TrialServiceError
from app.models import (
    Chat,
    AdminAction,
    CapacityPool,
    CodexAccount,
    CreditLedgerEntry,
    EmbeddingConfig,
    FeedbackEntry,
    Message,
    Model as DBModel,
    UsageEvent,
    Project,
    Provider,
    SystemPrompt,
    Tool,
    ToolBinding,
    ToolCall,
    TranscriptionConfig,
    TomanLedgerEntry,
    UserPreference,
    UserBillingAccount,
    Wallet,
    PromoCode,
    PromoCodeRedemption,
    WebSearchConfig,
    StarterCreditConfig,
    TrialConfig,
    ErrorLog,
    BotStartScenario,
    AdminMessageButton,
    PromotionalLink,
    PromotionalLinkClick,
    SubscriptionPlan,
)
from app.schemas import (
    AdminActionOut,
    BotStartScenarioSchema,
    BotStartScenarioCreate,
    BotStartScenarioUpdate,
    BulkGrantTrialOut,
    BulkGrantTrialRequest,
    CapacityPoolCreate,
    CapacityPoolOut,
    CapacityPoolUpdate,
    CodexAccountAuthStartOut,
    CodexAccountLimitStatusOut,
    CodexAccountCreate,
    CodexAccountOut,
    CodexAccountStatusOut,
    CodexAccountUpdate,
    CreditAdjustmentCreate,
    EmbeddingConfigCreate,
    EmbeddingConfigOut,
    EmbeddingConfigUpdate,
    FeedbackEntryOut,
    ModelCreate,
    ModelOut,
    ModelUpdate,
    ModelBulkAction,
    ProviderCreate,
    ProviderModelDiscoverOut,
    ProviderModelDiscoverRequest,
    ProviderOut,
    ProviderUpdate,
    PromoCodeCreate,
    PromoCodeOut,
    PromoCodeRedemptionCreate,
    PromoCodeRedemptionOut,
    PromoCodeUpdate,
    SystemPromptCreate,
    SystemPromptOut,
    SystemPromptUpdate,
    ToolBindingCreate,
    ToolBindingOut,
    ToolBindingUpdate,
    ToolCallOut,
    ToolCreate,
    ToolOut,
    ToolUpdate,
    TelegramBotStatusOut,
    TranscriptionConfigOut,
    TranscriptionConfigUpdate,
    CreditLedgerEntryOut,
    TomanLedgerEntryOut,
    UsageEventOut,
    UserPreferenceOut,
    UserTomanBillingSummaryOut,
    UserPreferenceUpdate,
    WalletOut,
    WebSearchConfigOut,
    WebSearchConfigUpdate,
    StarterCreditConfigOut,
    StarterCreditConfigUpdate,
    TrialConfigOut,
    TrialConfigUpdate,
    BroadcastRequest,
    BroadcastOut,
    ErrorLogResponse,
    PromotionalLinkCreate,
    PromotionalLinkUpdate,
    PromotionalLinkOut,
    PromotionalLinkClickOut,
    PromotionalLinkStats,
)

router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBearer(auto_error=False)


class _OpenSchema(BaseModel):
    class Config:
        extra = "allow"


class _TelegramGroupOutFallback(_OpenSchema):
    id: int


class _TelegramGroupMemberOutFallback(_OpenSchema):
    id: int


class _GroupUsageShareOutFallback(_OpenSchema):
    id: int


class _GroupUsageEventOutFallback(_OpenSchema):
    id: int


class _GroupUsageEventDetailOutFallback(_GroupUsageEventOutFallback):
    shares: list[dict] = []


class _TelegramGroupUpdateFallback(BaseModel):
    trigger_phrases_json: list[str] | None = None
    trigger_phrases: list[str] | None = None
    is_enabled: bool | None = None
    enabled: bool | None = None
    min_active_members: int | None = None
    minimum_active_members: int | None = None


TelegramGroupOutSchema = getattr(app_schemas, "TelegramGroupOut", _TelegramGroupOutFallback)
TelegramGroupMemberOutSchema = getattr(app_schemas, "TelegramGroupMemberOut", _TelegramGroupMemberOutFallback)
GroupUsageShareOutSchema = getattr(app_schemas, "GroupUsageShareOut", _GroupUsageShareOutFallback)
GroupUsageEventOutSchema = getattr(app_schemas, "GroupUsageEventOut", _GroupUsageEventOutFallback)
GroupUsageEventDetailOutSchema = getattr(
    app_schemas,
    "GroupUsageEventDetailOut",
    getattr(app_schemas, "GroupUsageEventWithSharesOut", _GroupUsageEventDetailOutFallback),
)
TelegramGroupUpdateSchema = getattr(
    app_schemas,
    "TelegramGroupUpdate",
    getattr(app_schemas, "TelegramGroupBillingSettingsUpdate", _TelegramGroupUpdateFallback),
)


async def verify_admin(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not credentials or credentials.credentials.strip() != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@router.get("/auth-check")
async def auth_check(_=Depends(verify_admin)):
    return {"ok": True}


@router.get("/telegram-bot/status", response_model=TelegramBotStatusOut)
async def telegram_bot_status(_=Depends(verify_admin)):
    return get_bot_status()


@router.post("/telegram-bot/start", response_model=TelegramBotStatusOut)
async def telegram_bot_start(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    await _record_admin_action(
        db,
        action_type="telegram_bot_start",
        target_type="system",
        target_id=None,
        reason="Admin started Telegram bot"
    )
    await db.commit()
    return start_bot()


@router.post("/telegram-bot/stop", response_model=TelegramBotStatusOut)
async def telegram_bot_stop(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    await _record_admin_action(
        db,
        action_type="telegram_bot_stop",
        target_type="system",
        target_id=None,
        reason="Admin stopped Telegram bot"
    )
    await db.commit()
    return stop_bot()


@router.post("/broadcast", response_model=BroadcastOut)
async def broadcast_message(
    message: str = Form(...),
    target_user_ids: Optional[str] = Form(None), # This will now be treated as target_identifiers
    target_groups: Optional[str] = Form(None),
    referral_campaign_id: Optional[int] = Form(None),
    buttons: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    from app.config import BOT_TOKEN, BALE_API_BASE_URL
    import json
    from sqlalchemy import or_

    # Parse JSON strings if provided
    try:
        # We treat target_user_ids as a list of identifiers (can be ID, Telegram ID, or Phone)
        identifiers = json.loads(target_user_ids) if isinstance(target_user_ids, str) and target_user_ids.strip() else None
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON in target_user_ids")

    if identifiers is not None and not isinstance(identifiers, list):
         raise HTTPException(400, "target_user_ids must be a JSON list")

    try:
        groups = json.loads(target_groups) if isinstance(target_groups, str) and target_groups.strip() else None
    except json.JSONDecodeError:
         raise HTTPException(400, "Invalid JSON in target_groups")

    if groups is not None and not isinstance(groups, list):
         raise HTTPException(400, "target_groups must be a JSON list")

    # Parse custom buttons
    reply_markup = None
    if isinstance(buttons, str) and buttons.strip():
        try:
            btn_list = json.loads(buttons)

            if not isinstance(btn_list, list):
                raise ValueError("buttons must be a list")
            
            inline_keyboard = []
            for btn_data in btn_list:
                label = btn_data.get("label")
                btype = btn_data.get("type")
                value = btn_data.get("value")
                
                if not label or not btype or not value:
                    continue
                
                if btype == "url":
                    inline_keyboard.append([{"text": label, "url": value}])
                elif btype == "prompt":
                    # Create a persistent button record
                    db_btn = AdminMessageButton(prompt=value)
                    db.add(db_btn)
                    await db.flush() # Get ID
                    inline_keyboard.append([{"text": label, "callback_data": f"admin_btn_{db_btn.id}"}])
            
            if inline_keyboard:
                reply_markup = json.dumps({"inline_keyboard": inline_keyboard})
                # Commit buttons before broadcast loop starts
                await db.commit()
        except Exception as e:
            raise HTTPException(400, f"Invalid buttons JSON: {str(e)}")

    # 1. Identify target users
    query = select(UserPreference).where(UserPreference.telegram_user_id.is_not(None))
    
    if identifiers:
        # Resolve identifiers: can be internal ID, telegram_user_id, or phone_number
        id_list = []
        phone_list = []
        for val in identifiers:
            if isinstance(val, int) or (isinstance(val, str) and val.isdigit()):
                id_list.append(int(val))
            if isinstance(val, str):
                phone_list.append(val)
        
        query = query.where(
            or_(
                UserPreference.id.in_(id_list),
                UserPreference.telegram_user_id.in_(id_list),
                UserPreference.phone_number.in_(phone_list)
            )
        )
    
    if groups:
        query = query.where(UserPreference.account_status.in_(groups))

    if referral_campaign_id:
        query = query.where(UserPreference.referral_campaign_id == referral_campaign_id)
        
    result = await db.execute(query)
    users = result.scalars().all()
    
    if not users:
        return BroadcastOut(success_count=0, failure_count=0, total_targeted=0)

    # 2. Prepare for sending
    success_count = 0
    failure_count = 0
    errors = []
    
    base_url = f"{BALE_API_BASE_URL.rstrip('/')}/bot{BOT_TOKEN}"
    
    # Read photo content if provided
    photo_content = None
    photo_filename = None
    if photo:
        photo_content = await photo.read()
        photo_filename = photo.filename
        url = f"{base_url}/sendPhoto"
    else:
        url = f"{base_url}/sendMessage"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for user in users:
            try:
                if photo_content:
                    files = {"photo": (photo_filename, photo_content)}
                    data = {
                        "chat_id": user.telegram_user_id,
                        "caption": message,
                    }
                    if reply_markup:
                        data["reply_markup"] = reply_markup
                    resp = await client.post(url, data=data, files=files)
                else:
                    payload = {
                        "chat_id": user.telegram_user_id,
                        "text": message,
                    }
                    if reply_markup:
                        payload["reply_markup"] = reply_markup
                    resp = await client.post(url, json=payload)
                    
                if resp.status_code == 200:
                    success_count += 1
                else:
                    failure_count += 1
                    try:
                        error_detail = resp.json()
                    except:
                        error_detail = resp.text[:200]
                    errors.append({
                        "user_id": user.id,
                        "telegram_id": user.telegram_user_id,
                        "status_code": resp.status_code,
                        "response": error_detail
                    })
            except Exception as e:
                failure_count += 1
                errors.append({
                    "user_id": user.id,
                    "error": str(e)
                })
                
    await _record_admin_action(
        db,
        action_type="broadcast_message",
        target_type="multiple_users",
        target_id=None,
        metadata={
            "success_count": success_count,
            "failure_count": failure_count,
            "total_targeted": len(users),
            "identifiers": identifiers,
            "groups": groups,
            "referral_campaign_id": referral_campaign_id,
            "has_buttons": buttons is not None,
            "has_photo": photo is not None
        },
        reason="Admin broadcast message"
    )
    await db.commit()

    return BroadcastOut(
        success_count=success_count,
        failure_count=failure_count,
        total_targeted=len(users),
        errors=errors if errors else None
    )


def _validate_binding_scope(scope_type: str, scope_id: int | None):
    if scope_type not in {"global", "project", "chat"}:
        raise HTTPException(400, "scope_type must be one of: global, project, chat")
    if scope_type == "global" and scope_id is not None:
        raise HTTPException(400, "global bindings cannot have scope_id")
    if scope_type in {"project", "chat"} and scope_id is None:
        raise HTTPException(400, f"{scope_type} bindings require scope_id")


def _normalize_prompt_payload(payload: dict) -> dict:
    if isinstance(payload.get("tool_guidance_style"), str):
        payload["tool_guidance_style"] = payload["tool_guidance_style"].strip().lower()
    if isinstance(payload.get("tool_guidance_template"), str):
        normalized = payload["tool_guidance_template"].strip()
        payload["tool_guidance_template"] = normalized or None
    return payload


def _usd_to_minor(amount: float) -> int:
    return int(round(float(amount) * 1_000_000))


def _minor_to_usd(amount_minor: int) -> float:
    return float(amount_minor or 0) / 1_000_000.0


def _promo_code_admin_snapshot(promo_code: PromoCode) -> dict:
    return {
        "id": promo_code.id,
        "code": promo_code.code,
        "description": promo_code.description,
        "bonus_type": promo_code.bonus_type,
        "currency": promo_code.currency or "USD",
        "bonus_value_usd": float(promo_code.bonus_value_usd or 0.0),
        "bonus_value_toman": int(promo_code.bonus_value_toman or 0),
        "minimum_charge_usd": float(promo_code.minimum_charge_usd or 0.0),
        "minimum_charge_toman": int(promo_code.minimum_charge_toman or 0),
        "max_redemptions_total": promo_code.max_redemptions_total,
        "max_redemptions_per_user": int(promo_code.max_redemptions_per_user or 0),
        "is_active": bool(promo_code.is_active),
        "expires_at": promo_code.expires_at,
    }


def _normalize_promo_code_payload(payload: dict) -> dict:
    model_payload: dict = {}
    if "code" in payload:
        normalized_code = normalize_promo_code(payload.get("code"))
        if not normalized_code:
            raise HTTPException(400, "code is required")
        model_payload["code"] = normalized_code

    if "description" in payload:
        description = payload.get("description")
        if description is None:
            model_payload["description"] = None
        elif isinstance(description, str):
            model_payload["description"] = description.strip() or None
        else:
            raise HTTPException(400, "description must be a string")

    if "bonus_type" in payload:
        bonus_type = str(payload.get("bonus_type") or "").strip().lower()
        if bonus_type not in {"fixed", "percent"}:
            raise HTTPException(400, "bonus_type must be fixed or percent")
        model_payload["bonus_type"] = bonus_type

    if "currency" in payload:
        currency = str(payload.get("currency") or "USD").strip().upper()
        if currency not in {"USD", "TOMAN"}:
            raise HTTPException(400, "currency must be USD or TOMAN")
        model_payload["currency"] = currency

    if "bonus_value" in payload:
        bonus_value = float(payload.get("bonus_value") or 0.0)
        if bonus_value <= 0:
            raise HTTPException(400, "bonus_value must be greater than zero")
        currency = payload.get("currency", "USD")
        if currency == "TOMAN":
            model_payload["bonus_value_toman"] = int(bonus_value)
        else:
            model_payload["bonus_value_usd"] = bonus_value

    if "minimum_charge" in payload:
        minimum_charge = float(payload.get("minimum_charge") or 0.0)
        if minimum_charge < 0:
            raise HTTPException(400, "minimum_charge must be zero or greater")
        currency = payload.get("currency", "USD")
        if currency == "TOMAN":
            model_payload["minimum_charge_toman"] = int(minimum_charge)
        else:
            model_payload["minimum_charge_usd"] = minimum_charge

    if "max_redemptions_total" in payload:
        max_total = payload.get("max_redemptions_total")
        if max_total is None:
            model_payload["max_redemptions_total"] = None
        else:
            value = int(max_total)
            if value <= 0:
                raise HTTPException(400, "max_redemptions_total must be greater than zero")
            model_payload["max_redemptions_total"] = value

    if "max_redemptions_per_user" in payload:
        per_user = int(payload.get("max_redemptions_per_user") or 0)
        if per_user <= 0:
            raise HTTPException(400, "max_redemptions_per_user must be greater than zero")
        model_payload["max_redemptions_per_user"] = per_user

    if "is_active" in payload:
        model_payload["is_active"] = bool(payload.get("is_active"))

    if "expires_at" in payload:
        model_payload["expires_at"] = payload.get("expires_at")

    return model_payload


def _extract_model_names(payload: dict) -> list[str]:
    raw_models = payload.get("data")
    if not isinstance(raw_models, list):
        raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        return []

    model_names: list[str] = []
    for item in raw_models:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("id") or "").strip()
        else:
            name = ""
        if name:
            model_names.append(name)
    # Keep API order while removing duplicates.
    return list(dict.fromkeys(model_names))


async def _fetch_openai_compatible_model_names(base_url: str, api_key: str | None) -> list[str]:
    normalized_base_url = (base_url or "").strip().rstrip("/")
    if not normalized_base_url:
        raise HTTPException(400, "base_url is required")

    models_url = f"{normalized_base_url}/models"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(models_url, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise HTTPException(400, "Model discovery failed: provider rejected credentials")
        raise HTTPException(400, f"Model discovery failed with status {exc.response.status_code}")
    except httpx.HTTPError as exc:
        raise HTTPException(400, f"Model discovery failed: {exc}")

    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(400, "Model discovery failed: provider returned non-JSON response")

    model_names = _extract_model_names(payload)
    if not model_names:
        raise HTTPException(400, "No models were returned by this provider")
    return model_names


def _coerce_imported_model_configs(imported_models: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for item in imported_models or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        display_name = item.get("display_name")
        display_name = str(display_name).strip() if isinstance(display_name, str) else None
        normalized.append(
            {
                "name": name,
                "display_name": display_name or name,
                "pricing_input": float(item.get("pricing_input") or 0.0),
                "pricing_output": float(item.get("pricing_output") or 0.0),
                "context_window": max(1, int(item.get("context_window") or 128000)),
                "is_active": bool(item.get("is_active", False)),
            }
        )
    # Keep first-seen order and de-duplicate by model name.
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in normalized:
        if row["name"] in seen:
            continue
        seen.add(row["name"])
        deduped.append(row)
    return deduped


async def _sync_provider_models(
    db: AsyncSession,
    provider: Provider,
    *,
    model_names: list[str] | None = None,
    imported_models: list[dict] | None = None,
    activate_new_models: bool = False,
) -> int:
    imported_configs = _coerce_imported_model_configs(imported_models)
    imported_by_name = {item["name"]: item for item in imported_configs}

    names = [name.strip() for name in (model_names or []) if isinstance(name, str) and name.strip()]
    if imported_configs:
        names = [item["name"] for item in imported_configs]
    if not names:
        names = await _fetch_openai_compatible_model_names(provider.base_url, provider.api_key)

    names = list(dict.fromkeys(names))
    existing_result = await db.execute(select(DBModel).where(DBModel.provider_id == provider.id))
    existing_by_name = {model.name: model for model in existing_result.scalars().all()}

    created_count = 0
    for model_name in names:
        config = imported_by_name.get(model_name)
        existing_model = existing_by_name.get(model_name)
        if existing_model:
            if config:
                existing_model.display_name = config["display_name"]
                existing_model.pricing_input = config["pricing_input"]
                existing_model.pricing_output = config["pricing_output"]
                existing_model.context_window = config["context_window"]
                existing_model.is_active = config["is_active"]
            continue
        display_name = model_name
        pricing_input = 0.0
        pricing_output = 0.0
        context_window = 128000
        is_active = activate_new_models
        if config:
            display_name = config["display_name"]
            pricing_input = config["pricing_input"]
            pricing_output = config["pricing_output"]
            context_window = config["context_window"]
            is_active = config["is_active"]
        db.add(
            DBModel(
                name=model_name,
                display_name=display_name,
                provider_id=provider.id,
                pricing_input=pricing_input,
                pricing_output=pricing_output,
                context_window=context_window,
                is_active=is_active,
            )
        )
        created_count += 1
    return created_count


def _user_admin_snapshot(user: UserPreference) -> dict:
    return {
        "id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "preferred_name": user.preferred_name,
        "phone_number": user.phone_number,
        "account_status": user.account_status,
        "credit_balance_usd": float(user.credit_balance_usd or 0.0),
        "is_admin": bool(user.is_admin),
        "learning_preferences_status": user.learning_preferences_status,
        "learning_preferences_summary": user.learning_preferences_summary,
    }


def _web_search_snapshot(config: WebSearchConfig) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "base_url": config.base_url,
        "api_key_set": bool(config.api_key),
        "search_type": config.search_type,
        "max_results": config.max_results,
        "include_domains": config.include_domains,
        "exclude_domains": config.exclude_domains,
        "contents_options": config.contents_options,
        "is_active": config.is_active,
    }


def _web_search_out(config: WebSearchConfig) -> dict:
    return {
        **_web_search_snapshot(config),
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def _transcription_snapshot(config: TranscriptionConfig) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "api_key_set": bool(config.api_key),
        "pricing_input": float(config.pricing_input or 0.0),
        "pricing_output": float(config.pricing_output or 0.0),
        "is_active": bool(config.is_active),
    }


def _transcription_out(config: TranscriptionConfig) -> dict:
    return {
        **_transcription_snapshot(config),
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }


def _resolve_model(candidates: list[str]):
    for name in candidates:
        model = getattr(app_models, name, None)
        if model is not None:
            return model
    return None


def _resolve_attr_name(entity, candidates: list[str]) -> str | None:
    for name in candidates:
        if hasattr(entity, name):
            return name
    return None


def _serialize_model_row(instance) -> dict:
    from datetime import datetime
    mapper = sa_inspect(instance.__class__)
    data = {}
    for column in mapper.columns:
        val = getattr(instance, column.key)
        if isinstance(val, datetime):
            val = val.isoformat()
        data[column.key] = val
    return data


def _normalize_trigger_phrases(value) -> list[str]:
    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raise HTTPException(400, "trigger_phrases must be a list or comma-separated string")

    normalized: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            continue
        phrase = item.strip().replace("ي", "ی").replace("ك", "ک")
        if phrase:
            normalized.append(phrase)
    return list(dict.fromkeys(normalized))


def _order_column_for(model):
    for key in ("created_at", "updated_at", "id"):
        column = getattr(model, key, None)
        if column is not None:
            return column.desc()
    return None


def _load_group_billing_models(required_share: bool = False) -> tuple[object, object, object, object | None]:
    group_model = _resolve_model(["TelegramGroup", "TelegramBillingGroup"])
    member_model = _resolve_model(["TelegramGroupMember", "TelegramBillingMember"])
    usage_event_model = _resolve_model(["GroupUsageEvent", "TelegramGroupUsageEvent"])
    share_model = _resolve_model(["GroupUsageShare", "GroupUsageEventShare", "TelegramGroupUsageShare"])

    if group_model is None or member_model is None or usage_event_model is None:
        raise HTTPException(
            status_code=501,
            detail="Telegram group billing models are not available in this backend build yet",
        )
    if required_share and share_model is None:
        raise HTTPException(
            status_code=501,
            detail="Group usage share model is not available in this backend build yet",
        )
    return group_model, member_model, usage_event_model, share_model


async def _get_or_create_web_search_config(db: AsyncSession) -> WebSearchConfig:
    result = await db.execute(select(WebSearchConfig).order_by(WebSearchConfig.is_active.desc(), WebSearchConfig.id))
    config = result.scalars().first()
    if config:
        return config
    config = WebSearchConfig(
        name="default",
        provider="exa",
        base_url="https://api.exa.ai/search",
        search_type="auto",
        max_results=5,
        contents_options={"highlights": {"maxCharacters": 1200}},
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def _get_or_create_transcription_config(db: AsyncSession) -> TranscriptionConfig:
    result = await db.execute(select(TranscriptionConfig).order_by(TranscriptionConfig.is_active.desc(), TranscriptionConfig.id))
    config = result.scalars().first()
    if config:
        return config
    config = TranscriptionConfig(
        name="default",
        provider="google",
        model="gemini-1.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        pricing_input=0.5,
        pricing_output=1.5,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def _get_or_create_starter_credit_config(db: AsyncSession) -> StarterCreditConfig:
    result = await db.execute(select(StarterCreditConfig).order_by(StarterCreditConfig.is_active.desc(), StarterCreditConfig.id))
    config = result.scalars().first()
    if config:
        return config
    config = StarterCreditConfig(
        name="default",
        amount_usd=0.0,
        amount_toman=0,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@router.get("/starter-credit-config", response_model=StarterCreditConfigOut)
async def get_starter_credit_config(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    config = await _get_or_create_starter_credit_config(db)
    return config


@router.patch("/starter-credit-config", response_model=StarterCreditConfigOut)
async def update_starter_credit_config(
    data: StarterCreditConfigUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    config = await _get_or_create_starter_credit_config(db)
    before_json = {
        "amount_usd": config.amount_usd,
        "amount_toman": config.amount_toman,
        "welcome_message": config.welcome_message,
        "is_active": config.is_active,
    }
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(config, key, value)

    after_json = {
        "amount_usd": config.amount_usd,
        "amount_toman": config.amount_toman,
        "welcome_message": config.welcome_message,
        "is_active": config.is_active,
    }

    await _record_admin_action(
        db,
        action_type="update_starter_credit_config",
        target_type="starter_credit_config",
        target_id=config.id,
        before_json=before_json,
        after_json=after_json,
        reason="Admin updated starter credit config"
    )

    await db.commit()
    await db.refresh(config)
    return config


async def _get_or_create_trial_config(db: AsyncSession) -> TrialConfig:
    result = await db.execute(select(TrialConfig).limit(1))
    config = result.scalar_one_or_none()
    if not config:
        config = TrialConfig()
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config


@router.get("/trial-config", response_model=TrialConfigOut)
async def get_trial_config(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    config = await _get_or_create_trial_config(db)
    return config


@router.patch("/trial-config", response_model=TrialConfigOut)
async def update_trial_config(
    data: TrialConfigUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    config = await _get_or_create_trial_config(db)
    before_json = _serialize_model_row(config)
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(config, key, value)

    await _record_admin_action(
        db,
        action_type="update_trial_config",
        target_type="trial_config",
        target_id=config.id,
        before_json=before_json,
        after_json=_serialize_model_row(config),
        reason="Admin updated trial config",
    )

    await db.commit()
    await db.refresh(config)
    return config


@router.post("/users/{user_id}/grant-trial")
async def grant_trial(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    try:
        subscription = await TrialService.grant_trial_subscription(db, user_id)
        return {
            "ok": True,
            "subscription_id": subscription.id,
            "expires_at": subscription.expires_at,
        }
    except TrialServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.post("/users/bulk-grant-trial", response_model=BulkGrantTrialOut)
async def bulk_grant_trial(
    data: BulkGrantTrialRequest,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    from app.services.trial_service import TrialServiceError

    if data.user_ids:
        query = select(UserPreference).where(
            UserPreference.id.in_(data.user_ids),
            UserPreference.telegram_user_id.is_not(None),
            UserPreference.account_status != "deleted",
        )
    else:
        query = select(UserPreference).where(
            UserPreference.telegram_user_id.is_not(None),
            UserPreference.account_status != "deleted",
        )

    result = await db.execute(query)
    users = result.scalars().all()

    success_count = 0
    skipped_count = 0
    error_count = 0
    details = []

    for user in users:
        try:
            if user.trial_used and data.skip_if_used:
                skipped_count += 1
                details.append({
                    "user_id": user.id,
                    "telegram_user_id": user.telegram_user_id,
                    "status": "skipped",
                    "reason": "trial_already_used",
                })
                continue

            sub_result = await db.execute(
                select(app_models.UserSubscription)
                .where(
                    app_models.UserSubscription.user_id == user.id,
                    app_models.UserSubscription.status == "active",
                )
                .limit(1)
            )
            if sub_result.scalar_one_or_none():
                skipped_count += 1
                details.append({
                    "user_id": user.id,
                    "telegram_user_id": user.telegram_user_id,
                    "status": "skipped",
                    "reason": "has_active_subscription",
                })
                continue

            if user.trial_used and not data.skip_if_used:
                user.trial_used = False
                await db.flush()

            subscription = await TrialService.grant_trial_subscription(db, user.id, reason="Bulk grant by admin")
            success_count += 1
            details.append({
                "user_id": user.id,
                "telegram_user_id": user.telegram_user_id,
                "status": "success",
                "subscription_id": subscription.id,
                "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
            })
        except TrialServiceError as e:
            error_count += 1
            details.append({
                "user_id": user.id,
                "telegram_user_id": user.telegram_user_id,
                "status": "error",
                "reason": str(e),
            })
        except Exception as e:
            error_count += 1
            details.append({
                "user_id": user.id,
                "telegram_user_id": user.telegram_user_id,
                "status": "error",
                "reason": f"Internal error: {str(e)}",
            })

    await _record_admin_action(
        db,
        action_type="bulk_grant_trial",
        target_type="multiple_users",
        target_id=None,
        metadata={
            "success_count": success_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "total_targeted": len(users),
            "skip_if_used": data.skip_if_used,
            "user_ids_filter": data.user_ids,
        },
        reason="Admin bulk granted trial subscriptions",
    )
    await db.commit()

    return BulkGrantTrialOut(
        success_count=success_count,
        skipped_count=skipped_count,
        error_count=error_count,
        total_targeted=len(users),
        details=details,
    )


@router.post("/broadcast-trial-invite", response_model=BroadcastOut)
async def broadcast_trial_invite(
    message: str = Form(None),
    button_text: str = Form(None),
    target_user_ids: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    from app.config import BOT_TOKEN, BALE_API_BASE_URL
    import json
    from sqlalchemy import or_

    try:
        identifiers = json.loads(target_user_ids) if isinstance(target_user_ids, str) and target_user_ids.strip() else None
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON in target_user_ids")

    if identifiers is not None and not isinstance(identifiers, list):
        raise HTTPException(400, "target_user_ids must be a JSON list")

    query = select(UserPreference).where(
        UserPreference.telegram_user_id.is_not(None),
        UserPreference.account_status != "deleted",
        UserPreference.trial_used == False,
    )

    if identifiers:
        id_list = []
        phone_list = []
        for val in identifiers:
            if isinstance(val, int) or (isinstance(val, str) and val.isdigit()):
                id_list.append(int(val))
            if isinstance(val, str):
                phone_list.append(val)

        query = query.where(
            or_(
                UserPreference.id.in_(id_list),
                UserPreference.telegram_user_id.in_(id_list),
                UserPreference.phone_number.in_(phone_list),
            )
        )

    result = await db.execute(query)
    users = result.scalars().all()

    if not users:
        return BroadcastOut(success_count=0, failure_count=0, total_targeted=0)

    trial_config_result = await db.execute(select(TrialConfig).limit(1))
    trial_config = trial_config_result.scalar_one_or_none()

    default_message = trial_config.invitation_message if trial_config and trial_config.invitation_message else "🎁 اشتراک تست ۲۴ ساعته رایگان برای شما فعال نشده است.\nآیا می‌خواهید آن را فعال کنید؟"
    text_to_send = message.strip() if message and message.strip() else default_message

    btn_text = button_text.strip() if button_text and button_text.strip() else (trial_config.invitation_button_text if trial_config and trial_config.invitation_button_text else "فعال‌سازی اشتراک رایگان")

    reply_markup = json.dumps({
        "inline_keyboard": [[{"text": btn_text, "callback_data": "activate_trial"}]],
    })

    success_count = 0
    failure_count = 0
    errors = []

    base_url = f"{BALE_API_BASE_URL.rstrip('/')}/bot{BOT_TOKEN}"
    url = f"{base_url}/sendMessage"

    import httpx
    async with httpx.AsyncClient(timeout=60.0) as client:
        for user in users:
            try:
                payload = {
                    "chat_id": user.telegram_user_id,
                    "text": text_to_send,
                    "reply_markup": reply_markup,
                }
                resp = await client.post(url, json=payload)

                if resp.status_code == 200:
                    success_count += 1
                else:
                    failure_count += 1
                    try:
                        error_detail = resp.json()
                    except:
                        error_detail = resp.text[:200]
                    errors.append({
                        "user_id": user.id,
                        "telegram_id": user.telegram_user_id,
                        "status_code": resp.status_code,
                        "response": error_detail,
                    })
            except Exception as e:
                failure_count += 1
                errors.append({
                    "user_id": user.id,
                    "error": str(e),
                })

    await _record_admin_action(
        db,
        action_type="broadcast_trial_invite",
        target_type="multiple_users",
        target_id=None,
        metadata={
            "success_count": success_count,
            "failure_count": failure_count,
            "total_targeted": len(users),
            "identifiers": identifiers,
        },
        reason="Admin broadcast trial invitation",
    )
    await db.commit()

    return BroadcastOut(
        success_count=success_count,
        failure_count=failure_count,
        total_targeted=len(users),
        errors=errors if errors else None,
    )


async def _ensure_wallet(db: AsyncSession, user: UserPreference) -> Wallet:
    result = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
    wallet = result.scalar_one_or_none()
    if wallet:
        return wallet
    opening_minor = _usd_to_minor(float(user.credit_balance_usd or 0.0))
    wallet = Wallet(
        user_id=user.id,
        currency="USD",
        balance_minor=opening_minor,
        available_minor=opening_minor,
        held_minor=0,
    )
    db.add(wallet)
    await db.flush()
    if opening_minor:
        db.add(
            CreditLedgerEntry(
                user_id=user.id,
                wallet_id=wallet.id,
                amount_delta_usd=_minor_to_usd(opening_minor),
                amount_minor=abs(opening_minor),
                balance_after_minor=wallet.balance_minor,
                available_after_minor=wallet.available_minor,
                held_after_minor=wallet.held_minor,
                currency=wallet.currency,
                direction="credit" if opening_minor >= 0 else "debit",
                entry_type="opening_balance",
                status="posted",
                reason="wallet backfill from user credit balance",
                idempotency_key=f"wallet:{wallet.id}:opening",
            )
        )
    return wallet


async def _record_admin_action(
    db: AsyncSession,
    *,
    action_type: str,
    target_type: str,
    target_id: int | None,
    before_json: dict | None = None,
    after_json: dict | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
) -> AdminAction:
    action = AdminAction(
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        before_json=before_json,
        after_json=after_json,
        reason=reason,
        metadata_json=metadata or {},
    )
    db.add(action)
    await db.flush()
    return action


# ---- Providers ----
def _normalize_provider_payload(payload: dict, *, default_kind: bool = False) -> dict:
    if "kind" in payload:
        payload["kind"] = normalize_provider_kind(payload.get("kind"))
    elif default_kind:
        payload["kind"] = normalize_provider_kind(payload.get("kind"))
    if payload.get("kind") == CODEX_SUBSCRIPTION_PROVIDER_KIND:
        payload["base_url"] = (payload.get("base_url") or "codex://subscription").strip() or "codex://subscription"
        payload["api_key"] = payload.get("api_key") or ""
    return payload


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Provider))
    return result.scalars().all()


@router.post("/providers/discover-models", response_model=ProviderModelDiscoverOut)
async def discover_provider_models(data: ProviderModelDiscoverRequest, _=Depends(verify_admin)):
    model_names = await _fetch_openai_compatible_model_names(data.base_url, data.api_key)
    return {"models": model_names}


@router.post("/providers", response_model=ProviderOut, status_code=201)
async def create_provider(data: ProviderCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    payload = _normalize_provider_payload(data.model_dump(), default_kind=True)
    sync_models = bool(payload.pop("sync_models", False))
    model_names = payload.pop("model_names", None)
    imported_models = payload.pop("imported_models", None)
    sync_models = sync_models or bool(imported_models)
    activate_imported_models = bool(payload.pop("activate_imported_models", False))

    provider = Provider(**payload)
    db.add(provider)
    await db.flush()
    if sync_models:
        await _sync_provider_models(
            db,
            provider,
            model_names=model_names,
            imported_models=imported_models,
            activate_new_models=activate_imported_models,
        )
    
    await _record_admin_action(
        db,
        action_type="provider_create",
        target_type="provider",
        target_id=provider.id,
        after_json=_serialize_model_row(provider),
        reason=f"Admin created provider: {provider.name}"
    )

    await db.commit()
    await db.refresh(provider)
    return provider


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: int, data: ProviderUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(404, "Provider not found")

    payload = _normalize_provider_payload(data.model_dump(exclude_unset=True))
    sync_models = bool(payload.pop("sync_models", False))
    model_names = payload.pop("model_names", None)
    imported_models = payload.pop("imported_models", None)
    sync_models = sync_models or bool(imported_models)
    activate_imported_models = bool(payload.pop("activate_imported_models", False))
    before_json = _serialize_model_row(provider)
    for key, value in payload.items():
        setattr(provider, key, value)
    if sync_models:
        await _sync_provider_models(
            db,
            provider,
            model_names=model_names,
            imported_models=imported_models,
            activate_new_models=activate_imported_models,
        )
    
    await _record_admin_action(
        db,
        action_type="provider_update",
        target_type="provider",
        target_id=provider_id,
        before_json=before_json,
        after_json=_serialize_model_row(provider),
        reason=f"Admin updated provider: {provider.name}"
    )

    await db.commit()
    await db.refresh(provider)
    return provider


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(404, "Provider not found")
    
    await _record_admin_action(
        db,
        action_type="provider_delete",
        target_type="provider",
        target_id=provider_id,
        before_json=_serialize_model_row(provider),
        reason=f"Admin deleted provider: {provider.name}"
    )

    await db.delete(provider)
    await db.commit()
    return {"ok": True}


# ---- Codex subscription accounts ----
def _validate_capacity_pool_values(payload: dict):
    if "name" in payload and payload["name"] is not None:
        payload["name"] = str(payload["name"]).strip()
        if not payload["name"]:
            raise HTTPException(400, "Pool name is required")
    for field in ("max_users", "active_users"):
        if field in payload and payload[field] is not None:
            value = int(payload[field])
            if value < 0:
                raise HTTPException(400, f"{field} must be zero or greater")
            payload[field] = value
    if "status" in payload and payload["status"] is not None:
        status = str(payload["status"]).strip().lower()
        if status not in {"active", "disabled"}:
            raise HTTPException(400, "Pool status must be active or disabled")
        payload["status"] = status
    if "fallback_behavior" in payload and payload["fallback_behavior"] is not None:
        behavior = str(payload["fallback_behavior"]).strip().lower()
        if behavior not in {"reject", "fallback_model"}:
            raise HTTPException(400, "fallback_behavior must be reject or fallback_model")
        payload["fallback_behavior"] = behavior
    return payload


async def _validate_capacity_account_values(db: AsyncSession, payload: dict):
    if "pool_id" in payload and payload["pool_id"] is not None:
        pool = await db.get(CapacityPool, int(payload["pool_id"]))
        if pool is None:
            raise HTTPException(400, "Capacity pool not found")
        payload["pool_id"] = pool.id
    if "status" in payload and payload["status"] is not None:
        status = str(payload["status"]).strip().lower()
        if status not in {"active", "limited", "disabled"}:
            raise HTTPException(400, "Codex account status must be active, limited, or disabled")
        payload["status"] = status
    for field in ("max_users", "five_hour_limit", "five_hour_used", "weekly_limit", "weekly_used"):
        if field in payload and payload[field] is not None:
            value = int(payload[field])
            if value < 0:
                raise HTTPException(400, f"{field} must be zero or greater")
            payload[field] = value
    if "safety_buffer_percent" in payload and payload["safety_buffer_percent"] is not None:
        value = float(payload["safety_buffer_percent"])
        if value < 0 or value > 95:
            raise HTTPException(400, "safety_buffer_percent must be between 0 and 95")
        payload["safety_buffer_percent"] = value
    return payload


@router.get("/capacity-pools", response_model=list[CapacityPoolOut])
async def list_capacity_pools(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(CapacityPool).order_by(CapacityPool.id))
    return result.scalars().all()


@router.post("/capacity-pools", response_model=CapacityPoolOut, status_code=201)
async def create_capacity_pool(data: CapacityPoolCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    payload = _validate_capacity_pool_values(data.model_dump())
    if payload.get("fallback_model_id") is not None:
        model = await db.get(DBModel, int(payload["fallback_model_id"]))
        if model is None:
            raise HTTPException(400, "Fallback model not found")
    pool = CapacityPool(**payload)
    db.add(pool)
    await db.flush()
    await _record_admin_action(
        db,
        action_type="capacity_pool_create",
        target_type="capacity_pool",
        target_id=pool.id,
        after_json=_serialize_model_row(pool),
        reason=f"Admin created capacity pool: {pool.name}",
    )
    await db.commit()
    await db.refresh(pool)
    return pool


@router.patch("/capacity-pools/{pool_id}", response_model=CapacityPoolOut)
async def update_capacity_pool(pool_id: int, data: CapacityPoolUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    pool = await db.get(CapacityPool, pool_id)
    if pool is None:
        raise HTTPException(404, "Capacity pool not found")
    payload = _validate_capacity_pool_values(data.model_dump(exclude_unset=True))
    if payload.get("fallback_model_id") is not None:
        model = await db.get(DBModel, int(payload["fallback_model_id"]))
        if model is None:
            raise HTTPException(400, "Fallback model not found")
    before_json = _serialize_model_row(pool)
    for key, value in payload.items():
        setattr(pool, key, value)
    await _record_admin_action(
        db,
        action_type="capacity_pool_update",
        target_type="capacity_pool",
        target_id=pool.id,
        before_json=before_json,
        after_json=_serialize_model_row(pool),
        reason=f"Admin updated capacity pool: {pool.name}",
    )
    await db.commit()
    await db.refresh(pool)
    return pool


@router.delete("/capacity-pools/{pool_id}")
async def delete_capacity_pool(pool_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    pool = await db.get(CapacityPool, pool_id)
    if pool is None:
        raise HTTPException(404, "Capacity pool not found")
    usage = await db.execute(select(CodexAccount.id).where(CodexAccount.pool_id == pool_id).limit(1))
    if usage.scalar_one_or_none() is not None:
        raise HTTPException(400, "Capacity pool has Codex accounts")
    subs = await db.execute(select(app_models.UserSubscription.id).where(app_models.UserSubscription.pool_id == pool_id).limit(1))
    if subs.scalar_one_or_none() is not None:
        raise HTTPException(400, "Capacity pool has user subscriptions")
    await _record_admin_action(
        db,
        action_type="capacity_pool_delete",
        target_type="capacity_pool",
        target_id=pool.id,
        before_json=_serialize_model_row(pool),
        reason=f"Admin deleted capacity pool: {pool.name}",
    )
    await db.delete(pool)
    await db.commit()
    return {"ok": True}


@router.post("/codex/default-provider", response_model=ProviderOut)
async def ensure_default_codex_provider(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Provider).where(Provider.kind == CODEX_SUBSCRIPTION_PROVIDER_KIND))
    provider = result.scalars().first()
    if provider is None:
        provider = Provider(
            name="Codex Subscription",
            base_url="codex://subscription",
            api_key="",
            kind=CODEX_SUBSCRIPTION_PROVIDER_KIND,
            is_active=True,
        )
        db.add(provider)
        await db.flush()

    for preset in CODEX_MODEL_PRESETS:
        existing = await db.execute(
            select(DBModel).where(DBModel.provider_id == provider.id, DBModel.name == preset["name"])
        )
        model = existing.scalar_one_or_none()
        if model is None:
            db.add(
                DBModel(
                    name=preset["name"],
                    display_name=preset["display_name"],
                    provider_id=provider.id,
                    pricing_input=preset["pricing_input"],
                    pricing_output=preset["pricing_output"],
                    context_window=preset["context_window"],
                    is_active=True,
                    capabilities={"model_type": NORMAL_MODEL_TYPE, "image_input": False},
                )
            )
        elif float(model.pricing_input or 0.0) == 0.0 and float(model.pricing_output or 0.0) == 0.0:
            model.pricing_input = preset["pricing_input"]
            model.pricing_output = preset["pricing_output"]
    await db.commit()
    await db.refresh(provider)
    return provider


@router.post("/zal/default-provider", response_model=ProviderOut)
async def ensure_default_zal_provider(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Provider).where(func.lower(Provider.name) == "zal"))
    provider = result.scalars().first()
    if provider is None:
        provider = Provider(
            name="Zal",
            base_url="http://localhost:1212/v1",
            api_key="zal-not-needed",
            kind="openai_compatible",
            is_active=True,
        )
        db.add(provider)
        await db.flush()

    for preset in ZAL_MODEL_PRESETS:
        existing = await db.execute(
            select(DBModel).where(DBModel.provider_id == provider.id, DBModel.name == preset["name"])
        )
        model = existing.scalar_one_or_none()
        if model is None:
            db.add(
                DBModel(
                    name=preset["name"],
                    display_name=preset["display_name"],
                    provider_id=provider.id,
                    pricing_input=preset["pricing_input"],
                    pricing_output=preset["pricing_output"],
                    context_window=preset["context_window"],
                    is_active=True,
                    capabilities={
                        "model_type": NORMAL_MODEL_TYPE, 
                        "image_input": True,
                        "supports_file_input": True
                    },
                )
            )
    await db.commit()
    await db.refresh(provider)
    return provider


@router.get("/codex-accounts", response_model=list[CodexAccountOut])
async def list_codex_accounts(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(CodexAccount).order_by(CodexAccount.id))
    return result.scalars().all()


@router.post("/codex-accounts", response_model=CodexAccountOut, status_code=201)
async def create_codex_account(data: CodexAccountCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    payload = await _validate_capacity_account_values(db, data.model_dump())
    provider_id = payload.get("provider_id")
    if provider_id is not None:
        provider_result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = provider_result.scalar_one_or_none()
        if not provider:
            raise HTTPException(400, "Provider not found")
        if normalize_provider_kind(provider.kind) != CODEX_SUBSCRIPTION_PROVIDER_KIND:
            raise HTTPException(400, "Provider must be a Codex subscription provider")

    account = CodexAccount(
        label=str(payload["label"]).strip() or "Codex account",
        provider_id=provider_id,
        pool_id=payload.get("pool_id"),
        codex_home=ensure_codex_home(build_codex_home()),
        auth_status="pending",
        is_active=bool(payload.get("is_active", True)),
        status=payload.get("status") or "active",
        max_users=payload.get("max_users", 50),
        five_hour_limit=payload.get("five_hour_limit", 0),
        five_hour_used=payload.get("five_hour_used", 0),
        weekly_limit=payload.get("weekly_limit", 0),
        weekly_used=payload.get("weekly_used", 0),
        safety_buffer_percent=payload.get("safety_buffer_percent", 30.0),
    )
    db.add(account)
    await db.flush()
    await _record_admin_action(
        db,
        action_type="codex_account_create",
        target_type="codex_account",
        target_id=account.id,
        after_json=_serialize_model_row(account),
        reason=f"Admin created Codex account: {account.label}",
    )
    await db.commit()
    await db.refresh(account)
    return account


@router.patch("/codex-accounts/{account_id}", response_model=CodexAccountOut)
async def update_codex_account(account_id: int, data: CodexAccountUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(CodexAccount).where(CodexAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Codex account not found")

    update_data = data.model_dump(exclude_unset=True)
    provider_id = update_data.get("provider_id")
    if provider_id is not None:
        provider_result = await db.execute(select(Provider).where(Provider.id == provider_id))
        provider = provider_result.scalar_one_or_none()
        if not provider:
            raise HTTPException(400, "Provider not found")
        if normalize_provider_kind(provider.kind) != CODEX_SUBSCRIPTION_PROVIDER_KIND:
            raise HTTPException(400, "Provider must be a Codex subscription provider")

    before_json = _serialize_model_row(account)
    if "label" in update_data:
        update_data["label"] = update_data["label"].strip() or account.label
    update_data = await _validate_capacity_account_values(db, update_data)
    for key, value in update_data.items():
        setattr(account, key, value)

    await _record_admin_action(
        db,
        action_type="codex_account_update",
        target_type="codex_account",
        target_id=account.id,
        before_json=before_json,
        after_json=_serialize_model_row(account),
        reason=f"Admin updated Codex account: {account.label}",
    )
    await db.commit()
    await db.refresh(account)
    return account


@router.delete("/codex-accounts/{account_id}")
async def delete_codex_account(account_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(CodexAccount).where(CodexAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Codex account not found")

    await _record_admin_action(
        db,
        action_type="codex_account_delete",
        target_type="codex_account",
        target_id=account.id,
        before_json=_serialize_model_row(account),
        reason=f"Admin deleted Codex account: {account.label}",
    )
    await db.delete(account)
    await db.commit()
    return {"ok": True}


@router.post("/codex-accounts/{account_id}/auth/start", response_model=CodexAccountAuthStartOut)
async def start_codex_account_auth(account_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(CodexAccount).where(CodexAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Codex account not found")
    command = build_codex_login_command(account)
    account.auth_status = "pending"
    account.last_error = None
    await db.commit()
    return {"account_id": account.id, "codex_home": account.codex_home, **command}


@router.post("/codex-accounts/{account_id}/auth/status", response_model=CodexAccountStatusOut)
async def refresh_codex_account_auth_status(account_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(CodexAccount).where(CodexAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Codex account not found")
    try:
        status = await check_codex_login_status(account)
    except Exception as exc:
        account.auth_status = "error"
        account.last_error = str(exc)[:1000]
        await db.commit()
        return {
            "account_id": account.id,
            "auth_status": account.auth_status,
            "is_authenticated": False,
            "stdout": "",
            "stderr": account.last_error,
        }

    account.auth_status = status["auth_status"]
    account.last_error = None if status["is_authenticated"] else (status.get("stderr") or status.get("stdout") or None)
    await db.commit()
    return {"account_id": account.id, **status}


@router.post("/codex-accounts/{account_id}/limits/status", response_model=CodexAccountLimitStatusOut)
async def refresh_codex_account_limit_status(account_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(CodexAccount).where(CodexAccount.id == account_id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Codex account not found")
    try:
        status = await refresh_codex_limit_status(account)
    except Exception as exc:
        account.last_error = str(exc)[:1000]
        await db.commit()
        raise HTTPException(502, f"Codex limit status failed: {str(exc)[:300]}") from exc

    metadata = dict(account.metadata_json or {})
    metadata["limit_status"] = status
    account.metadata_json = metadata
    account.last_error = None
    await db.commit()
    return {"account_id": account.id, **status}


# ---- Models ----
def _payload_model_type(payload: dict) -> str:
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        return NORMAL_MODEL_TYPE
    return str(capabilities.get("model_type") or NORMAL_MODEL_TYPE).strip() or NORMAL_MODEL_TYPE


async def _validate_model_payload_for_save(
    db: AsyncSession,
    payload: dict,
    *,
    current_model_id: int | None = None,
) -> None:
    model_type = _payload_model_type(payload)
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
        payload["capabilities"] = capabilities

    if model_type == AUTO_ROUTER_MODEL_TYPE:
        capabilities["model_type"] = AUTO_ROUTER_MODEL_TYPE
        payload["provider_id"] = None
        errors = await validate_auto_router_config(
            db,
            capabilities.get(AUTO_ROUTER_CONFIG_KEY),
            current_model_id=current_model_id,
        )
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        return

    capabilities["model_type"] = NORMAL_MODEL_TYPE
    provider_id = payload.get("provider_id")
    if not provider_id:
        raise HTTPException(status_code=400, detail="Provider not found")

    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Provider not found")


async def _model_with_toman(db: AsyncSession, model: DBModel) -> dict:
    from app.services.toman_billing_service import get_or_create_subscription_config, DEFAULT_USD_TO_TOMAN_RATE
    config = await get_or_create_subscription_config(db)
    rate = int(config.usd_to_toman_rate) if config else DEFAULT_USD_TO_TOMAN_RATE
    data = _serialize_model_row(model)
    data["pricing_input_toman"] = int(round(float(getattr(model, "pricing_input", 0.0) or 0.0) * rate))
    data["pricing_output_toman"] = int(round(float(getattr(model, "pricing_output", 0.0) or 0.0) * rate))
    return data


@router.get("/models", response_model=list[ModelOut])
async def list_models(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(DBModel))
    models = result.scalars().all()
    return [await _model_with_toman(db, m) for m in models]


@router.post("/models", response_model=ModelOut, status_code=201)
async def create_model(data: ModelCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    payload = data.model_dump()
    await _validate_model_payload_for_save(db, payload)

    if payload.get("is_default") and not payload.get("is_active"):
        raise HTTPException(status_code=400, detail="Default model must be active")

    model = DBModel(**payload)
    db.add(model)
    await db.flush()

    if model.is_default:
        await db.execute(
            update(DBModel)
            .where(DBModel.id != model.id)
            .values(is_default=False)
        )
    
    await _record_admin_action(
        db,
        action_type="model_create",
        target_type="model",
        target_id=model.id,
        after_json=_serialize_model_row(model),
        reason=f"Admin created model: {model.name}"
    )

    await db.commit()
    await db.refresh(model)
    return await _model_with_toman(db, model)


@router.patch("/models/{model_id}", response_model=ModelOut)
async def update_model(model_id: int, data: ModelUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(DBModel).where(DBModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "Model not found")

    update_data = data.model_dump(exclude_unset=True)
    effective_payload = {
        "name": update_data.get("name", model.name),
        "display_name": update_data.get("display_name", model.display_name),
        "provider_id": update_data.get("provider_id", model.provider_id),
        "pricing_input": update_data.get("pricing_input", model.pricing_input),
        "pricing_output": update_data.get("pricing_output", model.pricing_output),
        "context_window": update_data.get("context_window", model.context_window),
        "is_active": update_data.get("is_active", model.is_active),
        "is_default": update_data.get("is_default", model.is_default),
        "capabilities": update_data.get("capabilities", model.capabilities),
    }
    await _validate_model_payload_for_save(db, effective_payload, current_model_id=model.id)

    will_be_default = update_data.get("is_default", model.is_default)
    will_be_active = update_data.get("is_active", model.is_active)

    if will_be_default and not will_be_active:
        raise HTTPException(status_code=400, detail="Default model must be active")

    before_json = _serialize_model_row(model)
    if _payload_model_type(effective_payload) == AUTO_ROUTER_MODEL_TYPE:
        update_data["provider_id"] = None
    if "capabilities" in effective_payload:
        update_data["capabilities"] = effective_payload["capabilities"]
    for key, value in update_data.items():
        setattr(model, key, value)

    if update_data.get("is_default") is True:
        await db.execute(
            update(DBModel)
            .where(DBModel.id != model.id)
            .values(is_default=False)
        )
    
    await _record_admin_action(
        db,
        action_type="model_update",
        target_type="model",
        target_id=model_id,
        before_json=before_json,
        after_json=_serialize_model_row(model),
        reason=f"Admin updated model: {model.name}"
    )

    await db.commit()
    await db.refresh(model)
    return await _model_with_toman(db, model)


@router.delete("/models/{model_id}")
async def delete_model(model_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(DBModel).where(DBModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "Model not found")
    
    await _record_admin_action(
        db,
        action_type="model_delete",
        target_type="model",
        target_id=model_id,
        before_json=_serialize_model_row(model),
        reason=f"Admin deleted model: {model.name}"
    )

    await db.delete(model)
    await db.commit()
    return {"ok": True}


@router.post("/models/bulk")
async def bulk_models_action(data: ModelBulkAction, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    if not data.ids:
        return {"ok": True, "count": 0}

    if data.action == "delete":
        # Check if any of them are default
        result = await db.execute(select(DBModel).where(DBModel.id.in_(data.ids), DBModel.is_default == True))
        if result.scalar_one_or_none():
            raise HTTPException(400, "Cannot delete the default model. Change default first.")

        await _record_admin_action(
            db,
            action_type="bulk_model_delete",
            target_type="multiple_models",
            metadata={"ids": data.ids},
            target_id=None,
            reason=f"Admin bulk deleted {len(data.ids)} models"
        )
        await db.execute(delete(DBModel).where(DBModel.id.in_(data.ids)))
    
    elif data.action in ["enable", "disable"]:
        is_active = (data.action == "enable")
        
        # If disabling, check if any of them are default
        if not is_active:
            result = await db.execute(select(DBModel).where(DBModel.id.in_(data.ids), DBModel.is_default == True))
            if result.scalar_one_or_none():
                raise HTTPException(400, "Cannot disable the default model. Change default first.")

        await _record_admin_action(
            db,
            action_type=f"bulk_model_{data.action}",
            target_type="multiple_models",
            metadata={"ids": data.ids},
            target_id=None,
            reason=f"Admin bulk {data.action}d {len(data.ids)} models"
        )
        await db.execute(
            update(DBModel)
            .where(DBModel.id.in_(data.ids))
            .values(is_active=is_active)
        )

    await db.commit()
    return {"ok": True, "count": len(data.ids)}


@router.get("/models/price-suggestions")
async def model_price_suggestions(
    pricing_input: float = Query(...),
    pricing_output: float = Query(...),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    from app.services.toman_billing_service import get_or_create_subscription_config, DEFAULT_USD_TO_TOMAN_RATE
    from decimal import Decimal, ROUND_HALF_UP

    config = await get_or_create_subscription_config(db)
    rate = int(config.usd_to_toman_rate) if config else DEFAULT_USD_TO_TOMAN_RATE

    def _suggest(usd_price: float) -> dict:
        base_toman = int(round(float(usd_price or 0.0) * rate))
        # Round to nearest 1000 for a "pretty" number
        rounded = int(Decimal(str(base_toman / 1000.0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 1000)
        if rounded <= 0 and base_toman > 0:
            rounded = 1000
        suggested_usd = float(Decimal(str(rounded / float(rate))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)) if rate else 0.0
        return {
            "base_toman": base_toman,
            "rounded_toman": rounded,
            "suggested_usd": suggested_usd,
        }

    return {
        "usd_to_toman_rate": rate,
        "input": _suggest(pricing_input),
        "output": _suggest(pricing_output),
    }


@router.post("/providers/import-csv")
async def import_providers_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    content = await file.read()
    try:
        decoded_content = content.decode("utf-8")
    except UnicodeDecodeError:
        decoded_content = content.decode("latin-1")
    
    stream = io.StringIO(decoded_content)
    reader = csv.DictReader(stream)
    
    results = {"success": 0, "failed": 0, "errors": []}
    providers_cache = {}
    
    for row_idx, row in enumerate(reader, start=1):
        try:
            provider_name = row.get("provider_name")
            if not provider_name:
                raise ValueError("Missing provider_name")
            
            provider_name_lower = provider_name.strip().lower()
            provider = providers_cache.get(provider_name_lower)
            
            if not provider:
                p_stmt = select(Provider).where(func.lower(Provider.name) == provider_name_lower)
                p_res = await db.execute(p_stmt)
                provider = p_res.scalar_one_or_none()
            
            if not provider:
                base_url = row.get("provider_base_url", "").strip()
                if not base_url:
                    raise ValueError(f"Missing provider_base_url for new provider '{provider_name}'")
                api_key = row.get("provider_api_key", "").strip()
                
                provider = Provider(
                    name=provider_name.strip(),
                    base_url=base_url,
                    api_key=api_key or None,
                    is_active=True
                )
                db.add(provider)
                await db.flush()
            
            providers_cache[provider_name_lower] = provider
            
            name = row.get("model_name", "").strip()
            if not name:
                raise ValueError("Missing model_name")

            model_data = {
                "name": name,
                "display_name": (row.get("display_name") or name).strip(),
                "provider_id": provider.id,
                "pricing_input": float(row.get("pricing_input") or 0.0),
                "pricing_output": float(row.get("pricing_output") or 0.0),
                "context_window": int(row.get("context_window") or 128000),
                "is_active": str(row.get("is_active", "true")).lower().strip() == "true",
                "capabilities": {"image_input": str(row.get("supports_image_input", "false")).lower().strip() == "true"}
            }
            
            model = DBModel(**model_data)
            db.add(model)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Row {row_idx}: {str(e)}")
    
    await _record_admin_action(
        db,
        action_type="import_providers_csv",
        target_type="multiple_providers",
        target_id=None,
        metadata={
            "success_count": results["success"],
            "failed_count": results["failed"],
            "filename": file.filename
        },
        reason="Admin imported providers via CSV"
    )

    await db.commit()
    return results

@router.post("/models/import-csv")
async def import_models_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    content = await file.read()
    try:
        decoded_content = content.decode("utf-8")
    except UnicodeDecodeError:
        decoded_content = content.decode("latin-1")
    
    stream = io.StringIO(decoded_content)
    reader = csv.DictReader(stream)
    
    results = {"success": 0, "failed": 0, "errors": []}
    
    for row_idx, row in enumerate(reader, start=1):
        try:
            provider_name = row.get("provider_name")
            if not provider_name:
                raise ValueError("Missing provider_name")
            
            # Find provider
            p_stmt = select(Provider).where(func.lower(Provider.name) == provider_name.strip().lower())
            p_res = await db.execute(p_stmt)
            provider = p_res.scalar_one_or_none()
            
            if not provider:
                raise ValueError(f"Provider '{provider_name}' not found")
            
            # Prepare model data
            name = row.get("name", "").strip()
            if not name:
                raise ValueError("Missing model name")

            model_data = {
                "name": name,
                "display_name": (row.get("display_name") or name).strip(),
                "provider_id": provider.id,
                "pricing_input": float(row.get("pricing_input") or 0.0),
                "pricing_output": float(row.get("pricing_output") or 0.0),
                "context_window": int(row.get("context_window") or 128000),
                "is_active": str(row.get("is_active", "true")).lower().strip() == "true",
                "capabilities": {"image_input": str(row.get("supports_image_input", "false")).lower().strip() == "true"}
            }
            
            model = DBModel(**model_data)
            db.add(model)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Row {row_idx}: {str(e)}")
    
    await _record_admin_action(
        db,
        action_type="import_models_csv",
        target_type="multiple_models",
        target_id=None,
        metadata={
            "success_count": results["success"],
            "failed_count": results["failed"],
            "filename": file.filename
        },
        reason="Admin imported models via CSV"
    )

    await db.commit()
    return results


# ---- Tools ----
def _builtin_implementation_changes(tool: Tool, payload: dict) -> bool:
    protected_fields = {"kind", "implementation_key", "implementation_config"}
    for field in protected_fields & set(payload.keys()):
        if payload[field] != getattr(tool, field):
            return True
    return False


@router.get("/tools", response_model=list[ToolOut])
async def list_tools(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    await ensure_builtin_tools(db)
    result = await db.execute(select(Tool).order_by(Tool.name))
    return result.scalars().all()


@router.post("/tools/sync-builtins", response_model=list[ToolOut])
async def sync_builtin_tools(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    await ensure_builtin_tools(db)
    result = await db.execute(select(Tool).where(Tool.name.in_(list(BUILTIN_TOOLS.keys()))).order_by(Tool.name))
    tools = result.scalars().all()
    
    await _record_admin_action(
        db,
        action_type="tool_sync_builtins",
        target_type="multiple_tools",
        target_id=None,
        reason="Admin synced builtin tools"
    )
    await db.commit()
    
    return tools


@router.post("/tools", response_model=ToolOut, status_code=201)
async def create_tool(data: ToolCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    tool = Tool(**data.model_dump())
    db.add(tool)
    await db.flush()
    await _record_admin_action(
        db,
        action_type="tool_create",
        target_type="tool",
        target_id=tool.id,
        after_json=_serialize_model_row(tool),
        reason=f"Admin created tool: {tool.name}"
    )
    await db.commit()
    await db.refresh(tool)
    return tool


@router.patch("/tools/{tool_id}", response_model=ToolOut)
async def update_tool(tool_id: int, data: ToolUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(404, "Tool not found")
    payload = data.model_dump(exclude_unset=True)
    if tool.is_builtin and _builtin_implementation_changes(tool, payload):
        raise HTTPException(400, "Cannot change builtin tool implementation")
    before_json = _serialize_model_row(tool)
    for key, value in payload.items():
        setattr(tool, key, value)
    
    await _record_admin_action(
        db,
        action_type="tool_update",
        target_type="tool",
        target_id=tool_id,
        before_json=before_json,
        after_json=_serialize_model_row(tool),
        reason=f"Admin updated tool: {tool.name}"
    )
    
    await db.commit()
    await db.refresh(tool)
    return tool


@router.delete("/tools/{tool_id}")
async def delete_tool(tool_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(404, "Tool not found")
    if tool.is_builtin:
        raise HTTPException(400, "Builtin tools cannot be deleted")
    await _record_admin_action(
        db,
        action_type="tool_delete",
        target_type="tool",
        target_id=tool_id,
        before_json=_serialize_model_row(tool),
        reason=f"Admin deleted tool: {tool.name}"
    )
    
    await db.delete(tool)
    await db.commit()
    return {"ok": True}


@router.get("/tool-bindings", response_model=list[ToolBindingOut])
async def list_tool_bindings(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(ToolBinding).options(selectinload(ToolBinding.tool)).order_by(ToolBinding.scope_type, ToolBinding.id))
    return result.scalars().all()


@router.post("/tool-bindings", response_model=ToolBindingOut, status_code=201)
async def create_tool_binding(data: ToolBindingCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    _validate_binding_scope(data.scope_type, data.scope_id)
    tool_result = await db.execute(select(Tool).where(Tool.id == data.tool_id))
    tool = tool_result.scalar_one_or_none()
    if not tool:
        raise HTTPException(404, "Tool not found")
    if data.scope_type == "project":
        project_result = await db.execute(select(Project.id).where(Project.id == data.scope_id))
        if project_result.scalar_one_or_none() is None:
            raise HTTPException(404, "Project not found")
    if data.scope_type == "chat":
        chat_result = await db.execute(select(Chat.id).where(Chat.id == data.scope_id))
        if chat_result.scalar_one_or_none() is None:
            raise HTTPException(404, "Chat not found")
    binding = ToolBinding(**data.model_dump())
    db.add(binding)
    await db.flush()
    await _record_admin_action(
        db,
        action_type="tool_binding_create",
        target_type="tool_binding",
        target_id=binding.id,
        after_json=_serialize_model_row(binding),
        reason=f"Admin created tool binding for tool: {tool.name}"
    )
    await db.commit()
    result = await db.execute(select(ToolBinding).options(selectinload(ToolBinding.tool)).where(ToolBinding.id == binding.id))
    return result.scalar_one_or_none()


@router.patch("/tool-bindings/{binding_id}", response_model=ToolBindingOut)
async def update_tool_binding(binding_id: int, data: ToolBindingUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(ToolBinding).options(selectinload(ToolBinding.tool)).where(ToolBinding.id == binding_id))
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(404, "Tool binding not found")
    payload = data.model_dump(exclude_unset=True)
    scope_type = payload.get("scope_type", binding.scope_type)
    scope_id = payload.get("scope_id", binding.scope_id)
    _validate_binding_scope(scope_type, scope_id)
    if scope_type == "project" and scope_id is not None:
        project_result = await db.execute(select(Project.id).where(Project.id == scope_id))
        if project_result.scalar_one_or_none() is None:
            raise HTTPException(404, "Project not found")
    if scope_type == "chat" and scope_id is not None:
        chat_result = await db.execute(select(Chat.id).where(Chat.id == scope_id))
        if chat_result.scalar_one_or_none() is None:
            raise HTTPException(404, "Chat not found")
    before_json = _serialize_model_row(binding)
    for key, value in payload.items():
        setattr(binding, key, value)
    
    await _record_admin_action(
        db,
        action_type="tool_binding_update",
        target_type="tool_binding",
        target_id=binding_id,
        before_json=before_json,
        after_json=_serialize_model_row(binding),
        reason=f"Admin updated tool binding for tool: {binding.tool.name if binding.tool else 'Unknown'}"
    )
    
    await db.commit()
    await db.refresh(binding, attribute_names=["tool"])
    return binding


@router.delete("/tool-bindings/{binding_id}")
async def delete_tool_binding(binding_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(ToolBinding).where(ToolBinding.id == binding_id))
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(404, "Tool binding not found")
    await _record_admin_action(
        db,
        action_type="tool_binding_delete",
        target_type="tool_binding",
        target_id=binding_id,
        before_json=_serialize_model_row(binding),
        reason="Admin deleted tool binding"
    )
    
    await db.delete(binding)
    await db.commit()
    return {"ok": True}


@router.get("/tool-calls", response_model=list[ToolCallOut])
async def list_tool_calls(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(ToolCall).options(selectinload(ToolCall.tool)).order_by(ToolCall.created_at.desc()).limit(200))
    return result.scalars().all()


# ---- Web Search Provider ----
@router.get("/web-search-config", response_model=WebSearchConfigOut)
async def get_web_search_config(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    config = await _get_or_create_web_search_config(db)
    return _web_search_out(config)


@router.patch("/web-search-config", response_model=WebSearchConfigOut)
async def update_web_search_config(
    data: WebSearchConfigUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    config = await _get_or_create_web_search_config(db)
    before = _web_search_snapshot(config)
    payload = data.model_dump(exclude_unset=True)

    if "api_key" in payload:
        api_key = str(payload.pop("api_key") or "").strip()
        if api_key:
            config.api_key = api_key

    if "base_url" in payload:
        payload["base_url"] = str(payload["base_url"] or "").strip() or "https://api.exa.ai/search"
    if "name" in payload:
        payload["name"] = str(payload["name"] or "").strip() or "default"
    if "max_results" in payload:
        max_results = int(payload["max_results"] or 0)
        if max_results < 1 or max_results > 10:
            raise HTTPException(400, "max_results must be between 1 and 10")
        payload["max_results"] = max_results

    for key, value in payload.items():
        setattr(config, key, value)

    after = _web_search_snapshot(config)
    await _record_admin_action(
        db,
        action_type="web_search_config_update",
        target_type="web_search_config",
        target_id=config.id,
        before_json=before,
        after_json=after,
        reason="admin web search provider update",
    )
    await db.commit()
    await db.refresh(config)
    return _web_search_out(config)


@router.get("/transcription-config", response_model=TranscriptionConfigOut)
async def get_transcription_config(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    config = await _get_or_create_transcription_config(db)
    return _transcription_out(config)


@router.patch("/transcription-config", response_model=TranscriptionConfigOut)
async def update_transcription_config(
    data: TranscriptionConfigUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    config = await _get_or_create_transcription_config(db)
    before = _transcription_snapshot(config)
    payload = data.model_dump(exclude_unset=True)

    if "api_key" in payload:
        api_key = str(payload.pop("api_key") or "").strip()
        if api_key:
            config.api_key = api_key

    if "base_url" in payload:
        payload["base_url"] = str(payload["base_url"] or "").strip() or "https://generativelanguage.googleapis.com/v1beta"
    if "name" in payload:
        payload["name"] = str(payload["name"] or "").strip() or "default"
    if "model" in payload:
        model_value = str(payload["model"] or "").strip()
        if not model_value:
            raise HTTPException(400, "model is required")
        payload["model"] = model_value
    for price_key in ("pricing_input", "pricing_output"):
        if price_key in payload:
            try:
                price = float(payload[price_key] or 0.0)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{price_key} must be a number")
            if price < 0:
                raise HTTPException(400, f"{price_key} must be >= 0")
            payload[price_key] = price

    for key, value in payload.items():
        setattr(config, key, value)

    after = _transcription_snapshot(config)
    await _record_admin_action(
        db,
        action_type="transcription_config_update",
        target_type="transcription_config",
        target_id=config.id,
        before_json=before,
        after_json=after,
        reason="admin transcription config update",
    )
    await db.commit()
    await db.refresh(config)
    return _transcription_out(config)


# ---- Stats ----
@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    providers_count = (await db.execute(select(func.count(Provider.id)))).scalar()
    models_count = (await db.execute(select(func.count(DBModel.id)))).scalar()
    projects_count = (await db.execute(select(func.count(Project.id)))).scalar()
    chats_count = (await db.execute(select(func.count(Chat.id)))).scalar()
    messages_count = (await db.execute(select(func.count(Message.id)))).scalar()
    users_count = (await db.execute(select(func.count(UserPreference.id)))).scalar()
    tools_count = (await db.execute(select(func.count(Tool.id)))).scalar()
    tool_bindings_count = (await db.execute(select(func.count(ToolBinding.id)))).scalar()
    tool_calls_count = (await db.execute(select(func.count(ToolCall.id)))).scalar()
    return {
        "providers": providers_count,
        "models": models_count,
        "projects": projects_count,
        "chats": chats_count,
        "messages": messages_count,
        "users": users_count,
        "tools": tools_count,
        "tool_bindings": tool_bindings_count,
        "tool_calls": tool_calls_count,
    }


# ---- System Prompts ----
@router.get("/prompts", response_model=list[SystemPromptOut])
async def list_prompts(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(SystemPrompt))
    return result.scalars().all()


@router.post("/prompts", response_model=SystemPromptOut, status_code=201)
async def create_prompt(data: SystemPromptCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    payload = _normalize_prompt_payload(data.model_dump())
    prompt = SystemPrompt(**payload)
    db.add(prompt)
    await db.flush()
    await _record_admin_action(
        db,
        action_type="prompt_create",
        target_type="system_prompt",
        target_id=prompt.id,
        after_json=_serialize_model_row(prompt),
        reason=f"Admin created system prompt: {prompt.name}"
    )
    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.patch("/prompts/{prompt_id}", response_model=SystemPromptOut)
async def update_prompt(prompt_id: int, data: SystemPromptUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    payload = _normalize_prompt_payload(data.model_dump(exclude_unset=True))
    before_json = _serialize_model_row(prompt)
    for key, value in payload.items():
        setattr(prompt, key, value)
    
    await _record_admin_action(
        db,
        action_type="prompt_update",
        target_type="system_prompt",
        target_id=prompt_id,
        before_json=before_json,
        after_json=_serialize_model_row(prompt),
        reason=f"Admin updated system prompt: {prompt.name}"
    )
    
    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(prompt_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    await _record_admin_action(
        db,
        action_type="prompt_delete",
        target_type="system_prompt",
        target_id=prompt_id,
        before_json=_serialize_model_row(prompt),
        reason=f"Admin deleted system prompt: {prompt.name}"
    )
    
    await db.delete(prompt)
    await db.commit()
    return {"ok": True}


class PromptPreviewRequest(BaseModel):
    content: str


@router.post("/prompts/preview")
async def preview_prompt(data: PromptPreviewRequest, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    resolved = await PromptService.resolve_prompt(data.content, db)
    return {"resolved": resolved}


# ---- Embedding Config ----
@router.get("/embedding", response_model=list[EmbeddingConfigOut])
async def list_embedding_configs(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(EmbeddingConfig))
    return result.scalars().all()


@router.post("/embedding", response_model=EmbeddingConfigOut, status_code=201)
async def create_embedding_config(data: EmbeddingConfigCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    emb = EmbeddingConfig(**data.model_dump())
    db.add(emb)
    await db.flush()
    await _record_admin_action(
        db,
        action_type="embedding_config_create",
        target_type="embedding_config",
        target_id=emb.id,
        after_json=_serialize_model_row(emb),
        reason=f"Admin created embedding config: {emb.model}"
    )
    await db.commit()
    await db.refresh(emb)
    return emb


@router.patch("/embedding/{emb_id}", response_model=EmbeddingConfigOut)
async def update_embedding_config(emb_id: int, data: EmbeddingConfigUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(EmbeddingConfig).where(EmbeddingConfig.id == emb_id))
    emb = result.scalar_one_or_none()
    if not emb:
        raise HTTPException(404, "Embedding config not found")
    before_json = _serialize_model_row(emb)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(emb, key, value)
    
    await _record_admin_action(
        db,
        action_type="embedding_config_update",
        target_type="embedding_config",
        target_id=emb_id,
        before_json=before_json,
        after_json=_serialize_model_row(emb),
        reason=f"Admin updated embedding config: {emb.model}"
    )
    
    await db.commit()
    await db.refresh(emb)
    return emb


# ---- Users ----
@router.get("/promo-codes", response_model=list[PromoCodeOut])
async def list_promo_codes(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(PromoCode).order_by(PromoCode.created_at.desc(), PromoCode.id.desc()))
    return result.scalars().all()


@router.post("/promo-codes", response_model=PromoCodeOut, status_code=201)
async def create_promo_code(data: PromoCodeCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    payload = _normalize_promo_code_payload(data.model_dump())
    existing = (await db.execute(select(PromoCode).where(PromoCode.code == payload["code"]))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "promo code already exists")

    promo_code = PromoCode(**payload)
    db.add(promo_code)
    await db.flush()
    await _record_admin_action(
        db,
        action_type="promo_code_create",
        target_type="promo_code",
        target_id=promo_code.id,
        after_json=_promo_code_admin_snapshot(promo_code),
        reason="create promo code",
    )
    await db.commit()
    await db.refresh(promo_code)
    return promo_code


@router.patch("/promo-codes/{promo_code_id}", response_model=PromoCodeOut)
async def update_promo_code(
    promo_code_id: int,
    data: PromoCodeUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    promo_code = (await db.execute(select(PromoCode).where(PromoCode.id == promo_code_id))).scalar_one_or_none()
    if promo_code is None:
        raise HTTPException(404, "Promo code not found")

    payload = _normalize_promo_code_payload(data.model_dump(exclude_unset=True))
    if not payload:
        return promo_code

    if "code" in payload and payload["code"] != promo_code.code:
        existing = (await db.execute(select(PromoCode).where(PromoCode.code == payload["code"]))).scalar_one_or_none()
        if existing and existing.id != promo_code.id:
            raise HTTPException(400, "promo code already exists")

    before = _promo_code_admin_snapshot(promo_code)
    for key, value in payload.items():
        setattr(promo_code, key, value)
    await _record_admin_action(
        db,
        action_type="promo_code_update",
        target_type="promo_code",
        target_id=promo_code.id,
        before_json=before,
        after_json=_promo_code_admin_snapshot(promo_code),
        reason="update promo code",
    )
    await db.commit()
    await db.refresh(promo_code)
    return promo_code


@router.delete("/promo-codes/{promo_code_id}")
async def deactivate_promo_code(promo_code_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    promo_code = (await db.execute(select(PromoCode).where(PromoCode.id == promo_code_id))).scalar_one_or_none()
    if promo_code is None:
        raise HTTPException(404, "Promo code not found")
    before = _promo_code_admin_snapshot(promo_code)
    promo_code.is_active = False
    await _record_admin_action(
        db,
        action_type="promo_code_deactivate",
        target_type="promo_code",
        target_id=promo_code.id,
        before_json=before,
        after_json=_promo_code_admin_snapshot(promo_code),
        reason="deactivate promo code",
    )
    await db.commit()
    return {"ok": True, "status": "inactive"}


@router.get("/promo-code-redemptions", response_model=list[PromoCodeRedemptionOut])
async def list_promo_code_redemptions(
    promo_code_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    query = select(PromoCodeRedemption).order_by(PromoCodeRedemption.created_at.desc(), PromoCodeRedemption.id.desc()).limit(limit)
    if promo_code_id is not None:
        query = query.where(PromoCodeRedemption.promo_code_id == promo_code_id)
    if user_id is not None:
        query = query.where(PromoCodeRedemption.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/usage-stats/timeseries")
async def get_usage_timeseries(
    days: int = Query(1, ge=1, le=30),
    db: AsyncSession = Depends(get_session)
):
    from datetime import datetime, timedelta, timezone
    start_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # Simple query to get input/output tokens and request count grouped by hour
    # For SQLite, we use strftime
    group_expr = func.strftime("%Y-%m-%d %H:00:00", UsageEvent.created_at)

    query = (
        select(
            group_expr.label("time_bucket"),
            func.sum(UsageEvent.input_tokens).label("total_input"),
            func.sum(UsageEvent.output_tokens).label("total_output"),
            func.count(UsageEvent.id).label("request_count")
        )
        .where(UsageEvent.created_at >= start_date)
        .group_by("time_bucket")
        .order_by("time_bucket")
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "time": row.time_bucket,
            "input_tokens": row.total_input or 0,
            "output_tokens": row.total_output or 0,
            "requests": row.request_count or 0
        }
        for row in rows
    ]


@router.get("/users", response_model=List[UserPreferenceOut])
async def list_users(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(
        select(UserPreference).options(selectinload(UserPreference.billing_account))
    )
    users = result.scalars().all()
    out = []
    for user in users:
        account = user.billing_account
        gift = int(account.gift_balance_toman or 0) if account else 0
        paid = int(account.paid_balance_toman or 0) if account else 0
        data = {
            "id": user.id,
            "telegram_user_id": user.telegram_user_id,
            "first_name": user.first_name,
            "username": user.username,
            "preferred_name": user.preferred_name,
            "phone_number": user.phone_number,
            "account_status": user.account_status,
            "credit_balance_usd": float(user.credit_balance_usd or 0.0),
            "is_admin": bool(user.is_admin),
            "is_pro": bool(user.is_pro),
            "total_charged_usd": float(user.total_charged_usd or 0.0),
            "learning_preferences_status": user.learning_preferences_status,
            "learning_preferences_summary": user.learning_preferences_summary,
            "learning_preferences_prompt": user.learning_preferences_prompt,
            "learning_preferences_profile_json": user.learning_preferences_profile_json,
            "learning_preferences_completed_at": user.learning_preferences_completed_at,
            "created_at": user.created_at,
            "gift_balance_toman": gift,
            "paid_balance_toman": paid,
            "total_balance_toman": gift + paid,
        }
        out.append(data)
    return out


@router.patch("/users/{user_id}", response_model=UserPreferenceOut)
async def update_user(user_id: int, data: UserPreferenceUpdate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    payload = data.model_dump(exclude_unset=True)
    for credit_key in ("credit_balance_usd", "credit_balance", "credit"):
        if credit_key in payload:
            raise HTTPException(400, "Use /admin/users/{user_id}/credit-adjustments for balance changes")

    for phone_key in ("phone_number", "phone"):
        if phone_key in payload:
            user.phone_number = payload.pop(phone_key)
            break

    before = _user_admin_snapshot(user)
    for key, value in payload.items():
        setattr(user, key, value)
    after = _user_admin_snapshot(user)
    await _record_admin_action(
        db,
        action_type="user_update",
        target_type="user",
        target_id=user.id,
        before_json=before,
        after_json=after,
        reason="admin user patch",
    )

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    before = _user_admin_snapshot(user)
    user.account_status = "deleted"
    after = _user_admin_snapshot(user)
    await _record_admin_action(
        db,
        action_type="user_soft_delete",
        target_type="user",
        target_id=user.id,
        before_json=before,
        after_json=after,
        reason="soft delete via admin API",
    )
    await db.commit()
    return {"ok": True, "status": "deleted"}


@router.post("/users/{user_id}/credit-adjustments", response_model=TomanLedgerEntryOut, status_code=201)
async def adjust_user_credit(
    user_id: int,
    data: CreditAdjustmentCreate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    from app.services.toman_billing_service import get_or_create_billing_account

    result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if not data.reason.strip():
        raise HTTPException(400, "reason is required")
    if data.amount <= 0:
        raise HTTPException(400, "amount must be greater than zero")

    account = await get_or_create_billing_account(db, user)
    amount_toman = int(data.amount)
    if amount_toman <= 0:
        raise HTTPException(400, "amount is too small")

    if data.direction == "debit":
        available = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
        if available < amount_toman:
            raise HTTPException(400, "insufficient user toman credit for debit adjustment")

    idem = data.idempotency_key or f"admin-adjust:{user.id}:{data.direction}:{amount_toman}:{data.reason.strip()}"
    existing = (await db.execute(select(TomanLedgerEntry).where(TomanLedgerEntry.idempotency_key == idem))).scalar_one_or_none()
    if existing:
        return existing

    before = {
        "user": _user_admin_snapshot(user),
        "account": {
            "gift_balance_toman": account.gift_balance_toman,
            "paid_balance_toman": account.paid_balance_toman,
        },
    }

    if data.direction == "credit":
        account.paid_balance_toman = int(account.paid_balance_toman or 0) + amount_toman
        account.total_paid_topup_toman = int(account.total_paid_topup_toman or 0) + amount_toman
        gift_delta = 0
        paid_delta = amount_toman
    else:
        gift_spent = min(int(account.gift_balance_toman or 0), amount_toman)
        paid_spent = amount_toman - gift_spent
        account.gift_balance_toman = int(account.gift_balance_toman or 0) - gift_spent
        account.paid_balance_toman = int(account.paid_balance_toman or 0) - paid_spent
        account.total_gift_spent_toman = int(account.total_gift_spent_toman or 0) + gift_spent
        account.total_paid_spent_toman = int(account.total_paid_spent_toman or 0) + paid_spent
        gift_delta = -gift_spent
        paid_delta = -paid_spent

    account.version = int(account.version or 0) + 1

    action = await _record_admin_action(
        db,
        action_type="credit_adjustment",
        target_type="user",
        target_id=user.id,
        before_json=before,
        reason=data.reason.strip(),
        metadata={"direction": data.direction, "amount_toman": amount_toman},
    )

    entry = TomanLedgerEntry(
        user_id=user.id,
        billing_account_id=account.id,
        amount_toman=amount_toman if data.direction == "credit" else -amount_toman,
        gift_delta_toman=gift_delta,
        paid_delta_toman=paid_delta,
        gift_balance_after_toman=account.gift_balance_toman,
        paid_balance_after_toman=account.paid_balance_toman,
        entry_type="admin_adjustment",
        status="posted",
        reason=data.reason.strip(),
        admin_action_id=action.id,
        idempotency_key=idem,
        metadata_json={"admin_endpoint": "credit-adjustments", "direction": data.direction},
    )
    db.add(entry)
    action.after_json = {
        "user": _user_admin_snapshot(user),
        "account": {
            "gift_balance_toman": account.gift_balance_toman,
            "paid_balance_toman": account.paid_balance_toman,
        },
        "ledger_entry_id": None,
    }
    await db.commit()
    await db.refresh(entry)

    # Notify user
    if user.telegram_user_id:
        from app.services.notification_service import send_telegram_notification
        direction_msg = "افزایش" if data.direction == "credit" else "کاهش"
        msg = f"💰 {direction_msg} اعتبار کیف پول توسط مدیریت:\n" \
              f"مقدار: {amount_toman:,} تومان\n" \
              f"دلیل: {data.reason.strip()}"
        await send_telegram_notification(user.telegram_user_id, msg)

    action.after_json = {**(action.after_json or {}), "ledger_entry_id": entry.id}
    await db.commit()
    return entry


@router.post("/users/{user_id}/promo-code-redemptions", response_model=PromoCodeRedemptionOut, status_code=201)
async def redeem_promo_code_for_user_admin(
    user_id: int,
    data: PromoCodeRedemptionCreate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    user = (await db.execute(select(UserPreference).where(UserPreference.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")

    try:
        redemption = await redeem_promo_code_for_user(
            db,
            user=user,
            code=data.code,
            charge_amount_usd=float(data.charge_amount or 0.0) if (data.currency or "USD") == "USD" else 0.0,
            charge_amount_toman=int(data.charge_amount_toman or 0) if (data.currency or "USD") == "TOMAN" else 0,
            source="admin_panel",
        )
    except PromoCodeRedemptionError as exc:
        raise HTTPException(400, str(exc))

    await _record_admin_action(
        db,
        action_type="promo_code_redeem",
        target_type="user",
        target_id=user.id,
        reason=f"redeem promo code {normalize_promo_code(data.code)}",
        metadata={
            "promo_code_id": redemption.promo_code_id,
            "redemption_id": redemption.id,
            "charge_amount_usd": redemption.charge_amount_usd,
            "bonus_amount_usd": redemption.bonus_amount_usd,
            "total_credit_usd": redemption.total_credit_usd,
        },
    )
    await db.commit()
    await db.refresh(redemption)
    return redemption


@router.get("/users/{user_id}/wallet", response_model=WalletOut)
async def get_user_wallet(user_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    wallet = await _ensure_wallet(db, user)
    await db.commit()
    await db.refresh(wallet)
    return wallet


@router.get("/users/{user_id}/toman-billing-summary", response_model=UserTomanBillingSummaryOut)
async def get_user_toman_billing_summary(
    user_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    user = (await db.execute(select(UserPreference).where(UserPreference.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    account = (
        await db.execute(select(UserBillingAccount).where(UserBillingAccount.user_id == user_id))
    ).scalar_one_or_none()
    ledger_entries = (
        await db.execute(
            select(TomanLedgerEntry)
            .where(TomanLedgerEntry.user_id == user_id)
            .order_by(TomanLedgerEntry.created_at.desc(), TomanLedgerEntry.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    if account is None:
        return {
            "user_id": user_id,
            "ledger_entries": ledger_entries,
        }
    gift_balance = int(account.gift_balance_toman or 0)
    paid_balance = int(account.paid_balance_toman or 0)
    return {
        "user_id": user_id,
        "gift_balance_toman": gift_balance,
        "paid_balance_toman": paid_balance,
        "total_balance_toman": gift_balance + paid_balance,
        "total_gift_granted_toman": int(account.total_gift_granted_toman or 0),
        "total_gift_spent_toman": int(account.total_gift_spent_toman or 0),
        "total_paid_topup_toman": int(account.total_paid_topup_toman or 0),
        "total_paid_spent_toman": int(account.total_paid_spent_toman or 0),
        "total_subscription_paid_toman": int(account.total_subscription_paid_toman or 0),
        "first_topup_discount_used": bool(account.first_topup_discount_used),
        "ledger_entries": ledger_entries,
    }


@router.post("/users/{user_id}/suspend", response_model=UserPreferenceOut)
async def suspend_user(user_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    before = _user_admin_snapshot(user)
    user.account_status = "suspended"
    after = _user_admin_snapshot(user)
    await _record_admin_action(db, action_type="user_suspend", target_type="user", target_id=user.id, before_json=before, after_json=after)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/reactivate", response_model=UserPreferenceOut)
async def reactivate_user(user_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    before = _user_admin_snapshot(user)
    user.account_status = "active"
    after = _user_admin_snapshot(user)
    await _record_admin_action(db, action_type="user_reactivate", target_type="user", target_id=user.id, before_json=before, after_json=after)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/toggle-pro", response_model=UserPreferenceOut)
async def toggle_user_pro(user_id: int, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    before = _user_admin_snapshot(user)
    user.is_pro = not user.is_pro
    after = _user_admin_snapshot(user)
    await _record_admin_action(db, action_type="user_toggle_pro", target_type="user", target_id=user.id, before_json=before, after_json=after)
    await db.commit()
    await db.refresh(user)

    # Notify user
    if user.telegram_user_id:
        from app.services.notification_service import send_telegram_notification
        status_msg = "فعال" if user.is_pro else "غیرفعال"
        msg = f"✨ وضعیت کاربری ویژه (Pro) شما توسط مدیریت {status_msg} شد."
        await send_telegram_notification(user.telegram_user_id, msg)

    return user


@router.get("/users/{user_id}/credit-ledger", response_model=list[CreditLedgerEntryOut])
async def list_user_credit_ledger(
    user_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    user_result = await db.execute(select(UserPreference.id).where(UserPreference.id == user_id))
    if user_result.scalar_one_or_none() is None:
        raise HTTPException(404, "User not found")

    result = await db.execute(
        select(CreditLedgerEntry)
        .where(CreditLedgerEntry.user_id == user_id)
        .order_by(CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/users/{user_id}/usage-events", response_model=list[UsageEventOut])
async def list_user_usage_events(
    user_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    user_result = await db.execute(select(UserPreference.id).where(UserPreference.id == user_id))
    if user_result.scalar_one_or_none() is None:
        raise HTTPException(404, "User not found")

    result = await db.execute(
        select(UsageEvent)
        .where(UsageEvent.user_id == user_id)
        .order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/credit-ledger", response_model=list[CreditLedgerEntryOut])
async def list_credit_ledger(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    result = await db.execute(
        select(CreditLedgerEntry)
        .order_by(CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/feedback", response_model=list[FeedbackEntryOut])
async def list_feedback_entries(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    result = await db.execute(
        select(FeedbackEntry)
        .order_by(FeedbackEntry.created_at.desc(), FeedbackEntry.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/usage-events", response_model=list[UsageEventOut])
async def list_usage_events(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    result = await db.execute(
        select(UsageEvent)
        .order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/admin-actions", response_model=list[AdminActionOut])
async def list_admin_actions(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    result = await db.execute(
        select(AdminAction)
        .order_by(AdminAction.created_at.desc(), AdminAction.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ---- Telegram Group Billing ----
@router.get("/telegram-group-billing/groups", response_model=list[TelegramGroupOutSchema])
async def list_telegram_group_billing_groups(
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    group_model, _, _, _ = _load_group_billing_models()
    query = select(group_model).limit(limit)
    order_column = _order_column_for(group_model)
    if order_column is not None:
        query = query.order_by(order_column)
    result = await db.execute(query)
    return [_serialize_model_row(row) for row in result.scalars().all()]


@router.get("/telegram-group-billing/groups/{group_id}", response_model=TelegramGroupOutSchema)
async def get_telegram_group_billing_group(
    group_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    group_model, _, _, _ = _load_group_billing_models()
    result = await db.execute(select(group_model).where(group_model.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Telegram billing group not found")
    return _serialize_model_row(group)


@router.patch("/telegram-group-billing/groups/{group_id}", response_model=TelegramGroupOutSchema)
async def patch_telegram_group_billing_group(
    group_id: int,
    data: TelegramGroupUpdateSchema,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    group_model, _, _, _ = _load_group_billing_models()
    result = await db.execute(select(group_model).where(group_model.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(404, "Telegram billing group not found")

    payload = data.model_dump(exclude_unset=True)
    import logging
    logger = logging.getLogger(__name__)
    logger.info("PATCH group billing: id=%s payload=%s", group_id, payload)
    
    if not payload:
        raise HTTPException(400, "No settings were provided")

    before = _serialize_model_row(group)
    updated = False

    if "trigger_phrases_json" in payload or "trigger_phrases" in payload:
        trigger_value = payload.get("trigger_phrases_json", payload.get("trigger_phrases"))
        trigger_phrases = _normalize_trigger_phrases(trigger_value)
        logger.info("Normalized triggers: %s", trigger_phrases)
        trigger_key = _resolve_attr_name(group, ["trigger_phrases_json", "trigger_phrases"])
        if trigger_key is None:
            raise HTTPException(400, "Group model does not support trigger phrases")
        setattr(group, trigger_key, trigger_phrases)
        updated = True

    enabled_key = _resolve_attr_name(group, ["is_enabled", "enabled", "is_active"])
    status_key = _resolve_attr_name(group, ["status"])
    if "is_enabled" in payload or "enabled" in payload:
        enabled_value = bool(payload.get("is_enabled", payload.get("enabled")))
        if enabled_key is not None:
            setattr(group, enabled_key, enabled_value)
        elif status_key is not None:
            setattr(group, status_key, "active" if enabled_value else "inactive")
        else:
            raise HTTPException(400, "Group model does not support enabled/disabled state")
        updated = True

    if "min_active_members" in payload or "minimum_active_members" in payload:
        min_members = payload.get("min_active_members", payload.get("minimum_active_members"))
        try:
            min_members = int(min_members)
        except (TypeError, ValueError):
            raise HTTPException(400, "min_active_members must be an integer")
        if min_members < 1:
            raise HTTPException(400, "min_active_members must be >= 1")
        min_members_key = _resolve_attr_name(group, ["min_active_members", "minimum_active_members"])
        if min_members_key is None:
            raise HTTPException(400, "Group model does not support min_active_members")
        setattr(group, min_members_key, min_members)
        updated = True

    if not updated:
        raise HTTPException(400, "No supported group billing settings were provided")

    after = _serialize_model_row(group)
    await _record_admin_action(
        db,
        action_type="telegram_group_billing_group_update",
        target_type="telegram_group_billing_group",
        target_id=group_id,
        before_json=before,
        after_json=after,
        reason="admin telegram group billing settings update",
    )
    await db.commit()
    await db.refresh(group)
    return _serialize_model_row(group)


@router.get("/telegram-group-billing/groups/{group_id}/members", response_model=list[TelegramGroupMemberOutSchema])
async def list_telegram_group_billing_members(
    group_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    group_model, member_model, _, _ = _load_group_billing_models()
    group_exists = await db.execute(select(group_model.id).where(group_model.id == group_id))
    if group_exists.scalar_one_or_none() is None:
        raise HTTPException(404, "Telegram billing group not found")

    member_group_fk_name = _resolve_attr_name(member_model, ["group_id", "telegram_group_id", "telegram_billing_group_id"])
    if member_group_fk_name is None:
        raise HTTPException(500, "Member model does not expose a group foreign key")

    query = select(member_model).where(getattr(member_model, member_group_fk_name) == group_id)
    order_column = _order_column_for(member_model)
    if order_column is not None:
        query = query.order_by(order_column)
    result = await db.execute(query)
    return [_serialize_model_row(row) for row in result.scalars().all()]


@router.get("/telegram-group-billing/groups/{group_id}/usage-events", response_model=list[GroupUsageEventDetailOutSchema])
async def list_telegram_group_billing_usage_events(
    group_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    include_shares: bool = Query(default=True),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    group_model, _, usage_event_model, share_model = _load_group_billing_models()
    group_exists = await db.execute(select(group_model.id).where(group_model.id == group_id))
    if group_exists.scalar_one_or_none() is None:
        raise HTTPException(404, "Telegram billing group not found")

    usage_group_fk_name = _resolve_attr_name(
        usage_event_model,
        ["group_id", "telegram_group_id", "telegram_billing_group_id"],
    )
    if usage_group_fk_name is None:
        raise HTTPException(500, "Usage event model does not expose a group foreign key")

    query = (
        select(usage_event_model)
        .where(getattr(usage_event_model, usage_group_fk_name) == group_id)
        .limit(limit)
    )
    order_column = _order_column_for(usage_event_model)
    if order_column is not None:
        query = query.order_by(order_column)
    event_result = await db.execute(query)
    usage_events = event_result.scalars().all()

    response_rows = [_serialize_model_row(row) for row in usage_events]
    if not include_shares or not response_rows:
        for row in response_rows:
            row["shares"] = []
        return response_rows

    if share_model is None:
        for row in response_rows:
            row["shares"] = []
        return response_rows

    event_ids = [int(row["id"]) for row in response_rows if row.get("id") is not None]
    if not event_ids:
        for row in response_rows:
            row["shares"] = []
        return response_rows

    share_event_fk_name = _resolve_attr_name(share_model, ["group_usage_event_id", "usage_event_id", "event_id"])
    if share_event_fk_name is None:
        for row in response_rows:
            row["shares"] = []
        return response_rows

    share_query = select(share_model).where(getattr(share_model, share_event_fk_name).in_(event_ids))
    share_order_column = _order_column_for(share_model)
    if share_order_column is not None:
        share_query = share_query.order_by(share_order_column)
    share_result = await db.execute(share_query)
    shares = share_result.scalars().all()

    shares_by_event_id: dict[int, list[dict]] = {event_id: [] for event_id in event_ids}
    for share in shares:
        share_payload = _serialize_model_row(share)
        parent_id = share_payload.get(share_event_fk_name)
        if parent_id is None:
            continue
        shares_by_event_id.setdefault(int(parent_id), []).append(share_payload)

    for row in response_rows:
        event_id = row.get("id")
        row["shares"] = shares_by_event_id.get(int(event_id), []) if event_id is not None else []
    return response_rows


@router.get("/errors", response_model=List[ErrorLogResponse])
async def list_error_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    result = await db.execute(
        select(ErrorLog)
        .order_by(ErrorLog.timestamp.desc(), ErrorLog.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.patch("/errors/{error_id}/resolve")
async def resolve_error_log(
    error_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin),
):
    result = await db.execute(select(ErrorLog).filter(ErrorLog.id == error_id))
    error_log = result.scalar_one_or_none()
    if not error_log:
        raise HTTPException(status_code=404, detail="Error log not found")
    error_log.resolved = True
    
    await _record_admin_action(
        db,
        action_type="error_resolve",
        target_type="error_log",
        target_id=error_id,
        metadata={"error_message": error_log.error_message[:200]},
        reason="Admin resolved error log"
    )
    
    await db.commit()
    return {"status": "success"}


@router.get("/start-scenarios", response_model=List[BotStartScenarioSchema])
async def get_start_scenarios(db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    result = await db.execute(select(BotStartScenario).order_by(BotStartScenario.order))
    return result.scalars().all()


@router.post("/start-scenarios", response_model=BotStartScenarioSchema)
async def create_start_scenario(data: BotStartScenarioCreate, db: AsyncSession = Depends(get_session), _=Depends(verify_admin)):
    scenario = BotStartScenario(**data.model_dump())
    db.add(scenario)
    await db.flush()
    
    await _record_admin_action(
        db,
        action_type="create_start_scenario",
        target_type="bot_start_scenario",
        target_id=scenario.id,
        after_json=_serialize_model_row(scenario),
        reason=f"Admin created bot start scenario: {scenario.label}"
    )
    
    await db.commit()
    await db.refresh(scenario)
    return scenario


@router.put("/start-scenarios/{scenario_id}", response_model=BotStartScenarioSchema)
async def update_start_scenario(
    scenario_id: int,
    data: BotStartScenarioUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await db.execute(select(BotStartScenario).where(BotStartScenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(404, "Bot start scenario not found")

    before_json = _serialize_model_row(scenario)
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(scenario, key, value)

    await _record_admin_action(
        db,
        action_type="update_start_scenario",
        target_type="bot_start_scenario",
        target_id=scenario_id,
        before_json=before_json,
        after_json=_serialize_model_row(scenario),
        reason=f"Admin updated bot start scenario: {scenario.label}"
    )

    await db.commit()
    await db.refresh(scenario)
    return scenario


@router.delete("/start-scenarios/{scenario_id}")
async def delete_start_scenario(
    scenario_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await db.execute(select(BotStartScenario).where(BotStartScenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(404, "Bot start scenario not found")

    await _record_admin_action(
        db,
        action_type="delete_start_scenario",
        target_type="bot_start_scenario",
        target_id=scenario_id,
        before_json=_serialize_model_row(scenario),
        reason=f"Admin deleted bot start scenario: {scenario.label}"
    )

    await db.delete(scenario)
    await db.commit()
    return {"ok": True}


# ══════════════════════════════════════
# PROMOTIONAL LINKS
# ══════════════════════════════════════

import secrets

OFFER_START_PREFIX = "offer_"


def _format_toman(amount: int) -> str:
    return f"{int(amount or 0):,}"


@router.get("/promotional-links", response_model=list[PromotionalLinkOut])
async def list_promotional_links(
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await db.execute(
        select(PromotionalLink).order_by(PromotionalLink.created_at.desc())
    )
    links = result.scalars().all()

    out = []
    for link in links:
        clicks_res = await db.execute(
            select(func.count(PromotionalLinkClick.id)).where(
                PromotionalLinkClick.promotional_link_id == link.id
            )
        )
        total_clicks = clicks_res.scalar() or 0

        redemptions_res = await db.execute(
            select(func.count(PromotionalLinkClick.id)).where(
                PromotionalLinkClick.promotional_link_id == link.id,
                PromotionalLinkClick.redemption_status == "redeemed"
            )
        )
        total_redemptions = redemptions_res.scalar() or 0

        link_out = PromotionalLinkOut.model_validate(link)
        link_out.total_clicks = total_clicks
        link_out.total_redemptions = total_redemptions
        out.append(link_out)

    return out


@router.post("/promotional-links", response_model=PromotionalLinkOut, status_code=201)
async def create_promotional_link(
    data: PromotionalLinkCreate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    if data.offer_type == "free_subscription" and not data.plan_id:
        raise HTTPException(400, "plan_id is required for free_subscription offers")

    code = secrets.token_urlsafe(12)
    while True:
        existing = await db.execute(
            select(PromotionalLink).where(PromotionalLink.code == code)
        )
        if not existing.scalar_one_or_none():
            break
        code = secrets.token_urlsafe(12)

    link = PromotionalLink(
        code=code,
        title=data.title,
        description=data.description,
        offer_type=data.offer_type,
        offer_value_toman=data.offer_value_toman,
        offer_duration_hours=data.offer_duration_hours,
        plan_id=data.plan_id,
        discount_percent=data.discount_percent,
        max_redemptions=data.max_redemptions,
        expires_at=data.expires_at,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    return PromotionalLinkOut.model_validate(link)


@router.patch("/promotional-links/{link_id}", response_model=PromotionalLinkOut)
async def update_promotional_link(
    link_id: int,
    data: PromotionalLinkUpdate,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await db.execute(
        select(PromotionalLink).where(PromotionalLink.id == link_id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Promotional link not found")

    payload = data.model_dump(exclude_unset=True)
    offer_type = payload.get("offer_type", link.offer_type)
    if offer_type == "free_subscription" and payload.get("plan_id") is None and link.plan_id is None:
        raise HTTPException(400, "plan_id is required for free_subscription offers")
    for key, value in payload.items():
        setattr(link, key, value)

    await db.commit()
    await db.refresh(link)
    return PromotionalLinkOut.model_validate(link)


@router.delete("/promotional-links/{link_id}")
async def deactivate_promotional_link(
    link_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await db.execute(
        select(PromotionalLink).where(PromotionalLink.id == link_id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Promotional link not found")

    link.is_active = False
    await db.commit()
    return {"ok": True}


@router.get("/promotional-links/{link_id}/stats", response_model=PromotionalLinkStats)
async def get_promotional_link_stats(
    link_id: int,
    db: AsyncSession = Depends(get_session),
    _=Depends(verify_admin)
):
    result = await db.execute(
        select(PromotionalLink).where(PromotionalLink.id == link_id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Promotional link not found")

    clicks_res = await db.execute(
        select(func.count(PromotionalLinkClick.id)).where(
            PromotionalLinkClick.promotional_link_id == link_id
        )
    )
    total_clicks = clicks_res.scalar() or 0

    redeemed_res = await db.execute(
        select(func.count(PromotionalLinkClick.id)).where(
            PromotionalLinkClick.promotional_link_id == link_id,
            PromotionalLinkClick.redemption_status == "redeemed"
        )
    )
    total_redemptions = redeemed_res.scalar() or 0

    failed_res = await db.execute(
        select(func.count(PromotionalLinkClick.id)).where(
            PromotionalLinkClick.promotional_link_id == link_id,
            PromotionalLinkClick.redemption_status == "failed"
        )
    )
    total_failed = failed_res.scalar() or 0

    already_used_res = await db.execute(
        select(func.count(PromotionalLinkClick.id)).where(
            PromotionalLinkClick.promotional_link_id == link_id,
            PromotionalLinkClick.redemption_status == "already_used"
        )
    )
    total_already_used = already_used_res.scalar() or 0

    conversion_rate = (total_redemptions / total_clicks * 100) if total_clicks > 0 else 0.0

    clicks_result = await db.execute(
        select(PromotionalLinkClick)
        .where(PromotionalLinkClick.promotional_link_id == link_id)
        .order_by(PromotionalLinkClick.clicked_at.desc())
        .limit(100)
    )
    clicks = clicks_result.scalars().all()

    return PromotionalLinkStats(
        total_clicks=total_clicks,
        total_redemptions=total_redemptions,
        total_failed=total_failed,
        total_already_used=total_already_used,
        conversion_rate=round(conversion_rate, 2),
        clicks=[PromotionalLinkClickOut.model_validate(c) for c in clicks]
    )
