"""
دکتر بز Bot — v4: DB-persisted state + clean messages + project mode
"""

import asyncio
import base64
import os
import sys

def _encode_image_to_base64(file_path: str) -> str:
    """Encode an image file to base64 string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
print(f"!!! SYS_PATH: {sys.path} !!!")
print(f"!!! LOADING BACKEND/APP/BOT.PY !!!")
print(f"!!! FILE PATH: {os.path.abspath(__file__)} !!!")
import json
import logging
import os
import random
import re
import secrets
import string
import time
import traceback
from typing import Any, Optional
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
import httpx
import redis.asyncio as aioredis
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Contact,
    LabeledPrice,
    CopyTextButton,
    WebAppInfo,
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, ConversationHandler, ContextTypes, PreCheckoutQueryHandler, filters,
)
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.database import engine, init_db, async_session
from app.models import (
    Chat,
    Document,
    Message,
    Model as DBModel,
    Provider,
    Project,
    ReferralCampaign,
    ReferralEvent,
    UserPreference,
    UserSubscription,
    SubscriptionPlan,
    CreditLedgerEntry,
    TomanLedgerEntry,
    UserBillingAccount,
    FeedbackEntry,
    SystemPrompt,
    EmbeddingConfig,
    TranscriptionConfig,
    Tool,
    ToolBinding,
    ToolCall,
    UploadedFile,
    TelegramUpdateLog,
    UsageEvent,
    Wallet,
    TelegramGroup,
    TelegramGroupMember,
    GroupUsageEvent,
    GroupUsageShare,
    ErrorLog,
    BotStartScenario,
    AdminMessageButton,
    TrialConfig,
    PromotionalLink,
    PromotionalLinkClick,
)
from app.llm import (
    LLMProviderError,
    extract_reasoning_metadata,
    get_provider_for_model,
    get_default_model,
    generate_title,
    get_effective_system_prompt,
    get_system_prompt,
    get_emb_config,
    get_transcription_config,
    transcribe_audio,
    request_chat_completion,
    resolve_model_for_completion,
    run_pdf_generator_tool,
    get_chat_tools,
    execute_tool_call,
    ensure_builtin_tools,
    model_supports_image_input,
    messages_include_image_input,
    merge_reasoning_metadata,
    suggest_models_for_input_capability,
)
from app.rag import search_documents, index_document as rag_index_document, _read_file
from app.services.rag_service import background_index_document
from app.services.spreadsheet_analysis import SpreadsheetFile, SpreadsheetPreprocessResult, build_spreadsheet_preprocessing_context
from app.config import (
    BALE_API_BASE_URL,
    BALE_FILE_BASE_URL,
    BALE_WALLET_PROVIDER_TOKEN,
    BOT_PLATFORM,
    BOT_TOKEN,
    NOBITEX_HTTP_TIMEOUT_SECONDS,
    NOBITEX_MARKET_STATS_URL,
    REDIS_URL,
)
from app.services.account_service import get_user_by_phone, normalize_phone_number, apply_starter_credit
from app.services.promo_code_service import PromoCodeRedemptionError, normalize_promo_code, redeem_promo_code_for_user
from app.services.tool_delivery import files_to_deliver_from_python, parse_tool_output
from app.services.group_billing_service import (
    detect_group_trigger,
    estimate_split_and_strict_precheck,
    list_active_billing_members,
    split_cost_minor_with_remainder_rule,
)
from app.services.project_sharing import (
    PROJECT_SHARE_START_PREFIX,
    copy_project_for_user,
    ensure_project_share_token,
    get_group_public_project,
    get_project_by_share_token,
    list_group_public_projects,
    list_visible_projects,
    user_can_access_project,
)
from app.services.codex_runtime import calculate_codex_billable_usage, is_codex_subscription_provider
from app.tips_logic import handle_tip_callback, maybe_send_tip
from app.tips_integration import run_scheduled_tips
from app.persian_time import format_persian


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _get_emb_config(db: AsyncSession):
    """Get active embedding config from DB."""
    return await get_emb_config(db)


async def _get_or_create_transcription_config(db: AsyncSession) -> TranscriptionConfig:
    config = await get_transcription_config(db)
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


async def _search_with_config(project_id: int | None, query: str, emb_config=None, n_results: int = 5, chat_id: int | None = None) -> list[dict]:
    """Search documents using embedding config from DB."""
    api_key = emb_config.api_key if emb_config else None
    model = emb_config.model if emb_config else None
    provider = emb_config.provider if emb_config else "google"
    base_url = emb_config.base_url if emb_config else None
    return await asyncio.to_thread(search_documents, project_id, query, n_results=n_results, api_key=api_key, model=model, provider=provider, base_url=base_url, chat_id=chat_id)


def _rag_lookup_scope(project_id: int | None, chat_id: int | None) -> tuple[int | None, int | None]:
    if project_id:
        return project_id, None
    if chat_id:
        return None, chat_id
    return None, None


def _append_recent_uploads_context(system_content: str, upload_context: dict | None) -> str:
    if not upload_context:
        return system_content

    additions: list[str] = []
    texts = upload_context.get("texts") if isinstance(upload_context, dict) else None
    if texts:
        additions.append("# Recently Uploaded Files Content:")
        for item in texts:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            filename, file_text = item[0], item[1]
            additions.append(f"--- File: {filename} ---\n{str(file_text)[:5000]}")

    file_refs = upload_context.get("files") if isinstance(upload_context, dict) else None
    if file_refs:
        additions.append("# Recently Uploaded Files:")
        for ref in file_refs:
            if not isinstance(ref, dict):
                continue
            filename = ref.get("filename") or "file"
            uploaded_id = ref.get("id")
            mode = "indexed/RAG" if ref.get("rag") else "direct"
            id_text = f" (ID={uploaded_id})" if uploaded_id is not None else ""
            additions.append(f"- {filename}{id_text}: {mode}")

    if not additions:
        return system_content
    return f"{system_content}\n\n" + "\n\n".join(additions)


async def _build_spreadsheet_preprocessing_context(
    db: AsyncSession,
    *,
    user: UserPreference,
    user_text: str,
    chat_id: int | None,
) -> SpreadsheetPreprocessResult | None:
    cutoff = _utcnow() - timedelta(hours=6)
    query = (
        select(UploadedFile)
        .where(
            UploadedFile.user_id == user.id,
            UploadedFile.storage_path.is_not(None),
            UploadedFile.file_type.in_(["csv", "xlsx", "xlsm"]),
        )
        .order_by(UploadedFile.created_at.desc())
        .limit(12)
    )
    rows = (await db.execute(query)).scalars().all()
    files: list[SpreadsheetFile] = []
    seen_filenames: set[str] = set()
    for row in rows:
        created_at = row.created_at
        if created_at and created_at < cutoff and row.chat_id != chat_id:
            continue
        path = row.storage_path or ""
        if not path or not os.path.isfile(path):
            continue
        filename = row.filename or os.path.basename(path)
        filename_key = filename.strip().lower()
        if filename_key in seen_filenames:
            continue
        seen_filenames.add(filename_key)
        files.append(SpreadsheetFile(filename, path))

    if not files:
        return None
    return await asyncio.to_thread(build_spreadsheet_preprocessing_context, files, user_text)


def _user_requested_pdf(text: str) -> bool:
    normalized = (text or "").lower()
    return any(token in normalized for token in ("pdf", "پی دی اف", "پی‌دی‌اف", "پی دی‌اف"))

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

UPLOAD_DIR = "./uploads"
GENERATED_PDF_DIR = os.path.abspath(os.path.join(UPLOAD_DIR, "generated_pdfs"))
GENERATED_PDF_TTL_SECONDS = 24 * 60 * 60

MATH_BLOCK_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
MATH_INLINE_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", re.DOTALL)
SMALLTALK_TEXT_RE = re.compile(
    r"^\s*(سلام|درود|hi|hello|hey|ممنون|مرسی|تشکر|thanks|thank you|خداحافظ|bye)\b",
    flags=re.IGNORECASE,
)

ONBOARDING_PENDING_STATUSES = {"pending_onboarding", "pending_profile", "pending_name", "incomplete"}
BLOCKED_ACCOUNT_STATUSES = {"suspended", "deactivated", "deleted"}
CHAT_OUTPUT_TOKEN_ESTIMATE = 900
GEMINI_AUDIO_TOKENS_PER_SECOND = 32
VOICE_TRANSCRIPTION_PROMPT = "Convert the following audio to text. Return ONLY the text of the speech in its original language. If no speech is present, return an empty string. Absolutely no side comments."
MIN_RATING_REPLY_CHARS = 220
RATING_REQUEST_PROBABILITY = 0.3
GROUP_OPTIN_START_PREFIX = "groupoptin_"
CANCEL_TEXT = "❌ لغو"
GROUP_DEFAULT_TRIGGER_PHRASES = [
    "hey doctor boz",
    "hey boz",
    "hi doctor boz",
    "هی دکتر بز",
]
GROUP_MIN_ACTIVE_MEMBERS_DEFAULT = 2
GROUP_ALLOWED_CHAT_TYPES = set() # {"group", "supergroup"}
DOCUMENT_AUDIO_EXTENSIONS = {"m4a", "ogg", "mp3", "wav", "aac", "flac", "webm", "opus"}
_GROUP_TABLES_READY = False
DEFAULT_TOPUP_USD_AMOUNT = Decimal("5")
MIN_TOPUP_USD_AMOUNT = Decimal("1")
MAX_TOPUP_USD_AMOUNT = Decimal("5000")
TOPUP_USD_DECIMALS = Decimal("0.01")
TOPUP_PAYLOAD_PREFIX = "topup"
SUBSCRIPTION_PAYLOAD_PREFIX = "sub"
TOMAN_TOPUP_PAYLOAD_PREFIX = "ttop"
TOPUP_PROMO_SKIP_TEXT = "⏭️ کد ندارم"
MAX_TOPUP_PROMO_CODE_LEN = 32
_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
PHONE_TEXT_RE = re.compile(r"^[\d۰-۹+\-\s()]{7,24}$")


def _is_bale_platform() -> bool:
    return (BOT_PLATFORM or "").strip().lower() == "bale"


async def _download_telegram_file(context: ContextTypes.DEFAULT_TYPE, file_id: str, dest_path: str):
    """Download a file from Telegram or Bale, handling platform-specific quirks."""
    if _is_bale_platform():
        # FULL MANUAL DOWNLOAD FOR BALE with RETRIES
        last_err = None
        last_curl_error = ""
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(60.0, connect=10.0),
                    http2=True,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "*/*",
                    }
                ) as client:
                    token = BOT_TOKEN
                    get_file_url = f"{BALE_API_BASE_URL.rstrip('/')}/bot{token}/getFile"
                    resp = await client.get(get_file_url, params={"file_id": file_id})
                    resp.raise_for_status()
                    file_info = resp.json()
                    logger.info(f"Bale getFile info: {file_info}")
                    if not file_info.get("ok"):
                        raise ValueError(f"Bale getFile failed: {file_info.get('description')}")

                    res = file_info.get("result")
                    if not res or "file_path" not in res:
                        raise ValueError(f"Bale getFile response missing file_path: {file_info}")
                        
                    rel_path = res["file_path"]
                    urls_to_try = []
                    if rel_path.startswith("http"):
                        urls_to_try = [rel_path]
                    else:
                        # Try both /file/bot and /bot prefixes
                        clean_rel_path = rel_path.lstrip('/')
                        base_bale = BALE_API_BASE_URL.rstrip('/')
                        urls_to_try = [
                            f"{base_bale}/file/bot{token}/{clean_rel_path}",
                            f"{base_bale}/bot{token}/{clean_rel_path}",
                            f"{base_bale}/{clean_rel_path}"
                        ]

                    success = False
                    for download_url in urls_to_try:
                        try:
                            logger.info(f"Downloading from: {download_url} via curl")
                            import subprocess
                            # Use curl with a reasonable timeout, run in thread to avoid blocking event loop
                            result = await asyncio.to_thread(
                                subprocess.run,
                                ["curl", "-L", "-s", "-f", "--connect-timeout", "20", "--max-time", "600", "-A", "Mozilla/5.0", "-o", dest_path, download_url],
                                capture_output=True, text=True
                            )
                            if result.returncode == 0:
                                # Verify file exists and is not empty
                                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                                    success = True
                                    logger.info(f"Successfully downloaded via curl from {download_url}")
                                    break
                                else:
                                    logger.warning(f"curl succeeded but file is empty or missing: {dest_path}")
                            else:
                                last_curl_error = result.stderr or f"Exit code {result.returncode}"
                                logger.warning(f"curl failed for {download_url} with code {result.returncode}: {last_curl_error}")
                                # Try next URL
                        except Exception as e:
                            logger.error(f"Error during curl download from {download_url}: {e}")
                    
                    if success:
                        return # Success!
            except Exception as e:
                last_err = e
                logger.warning(f"Download attempt {attempt+1} failed: {str(e)}")
                if attempt < 1:
                    await asyncio.sleep(1)

        # If manual failed, try PTB standard as last resort
        try:
            logger.info("Manual download failed, trying PTB standard download...")
            file = await context.bot.get_file(file_id)
            await file.download_to_drive(dest_path)
            return
        except Exception as e:
            logger.error(f"PTB fallback download also failed: {e}")
            raise last_err or ValueError(f"All download attempts failed. Last curl error: {last_curl_error}")
    else:
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(dest_path)

def _normalize_math_for_telegram(text: str) -> str:
    if not text:
        return text

    if _is_bale_platform():
        def repl_block_bale(match: re.Match) -> str:
            expr = " ".join(match.group(1).split())
            return f"\n ```[فرمول ریاضی]{expr}``` \n"

        def repl_inline_bale(match: re.Match) -> str:
            expr = " ".join(match.group(1).split())
            return f" *{expr}* "

        text = MATH_BLOCK_RE.sub(repl_block_bale, text)
        text = MATH_INLINE_RE.sub(repl_inline_bale, text)
        return text

    def repl_block(match: re.Match) -> str:
        expr = " ".join(match.group(1).split())
        return f"\n<pre>{expr}</pre>\n"

    def repl_inline(match: re.Match) -> str:
        expr = " ".join(match.group(1).split())
        return f"<code>{expr}</code>"

    text = MATH_BLOCK_RE.sub(repl_block, text)
    text = MATH_INLINE_RE.sub(repl_inline, text)
    return text


def _html_escape_non_tags(text: str) -> str:
    if _is_bale_platform():
        return text  # Bale doesn't parse HTML, so don't escape it.

    placeholders: dict[str, str] = {}

    def keep(match: re.Match) -> str:
        key = f"__TG_TAG_{len(placeholders)}__"
        placeholders[key] = match.group(0)
        return key

    allowed_tags = re.compile(r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|tg-spoiler)>", re.IGNORECASE)
    text = allowed_tags.sub(keep, text)
    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


def _normalize_bullets(text: str) -> str:
    lines = text.splitlines()
    normalized: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("* ") or stripped.startswith("- "):
            normalized.append(f"{indent}• {stripped[2:]}")
        else:
            normalized.append(line)
    return "\n".join(normalized)


def _telegram_format(text: str) -> str:
    if not text:
        return ""
    text = text.replace("<think>", "💭 ").replace("</think>", "")
    text = text.replace("\\#", "#").replace("\\*", "*")
    text = _normalize_math_for_telegram(text)
    if _is_bale_platform():
        # Convert HTML tags to Markdown (LLMs sometimes output HTML directly)
        text = re.sub(r"<(?:b|strong)>(.*?)</(?:b|strong)>", r" *\1* ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<(?:i|em)>(.*?)</(?:i|em)>", r" _\1_ ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<(?:u|s|del|strike)>(.*?)</(?:u|s|del|strike)>", r" \1 ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<code>(.*?)</code>", r" \1 ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</?p>", "\n", text, flags=re.IGNORECASE)
        
        # Bale-specific Markdown (requires spaces around symbols)
        text = re.sub(r"\*\*(.*?)\*\*", r" *\1* ", text, flags=re.DOTALL)
        text = re.sub(r"__(.*?)__", r" _\1_ ", text, flags=re.DOTALL)
        text = re.sub(r"~~(.*?)~~", r" \1 ", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r" \1 ", text)
        text = _normalize_bullets(text)
        return text

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text, flags=re.DOTALL)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = _normalize_bullets(text)
    text = _html_escape_non_tags(text)
    return text


def _telegram_parse_mode():
    return ParseMode.MARKDOWN if _is_bale_platform() else ParseMode.HTML


async def _send_or_edit_formatted(message_obj, text: str, reply_markup=None):
    # Hardware-like stop check: if recently requested, silence all output
    uid = getattr(message_obj.chat, "id", 0)
    if uid and _is_stopping(uid):
        return None

    formatted = _telegram_format(text)
    try:
        return await message_obj.edit_text(formatted, parse_mode=_telegram_parse_mode(), reply_markup=reply_markup)
    except Exception as e:
        logger.warning("Telegram formatted edit failed: %s | text=%r | formatted=%r", e, text[:300], formatted[:300])
        try:
            return await message_obj.edit_text(text, reply_markup=reply_markup)
        except Exception:
            return None


async def _reply_formatted(update: Update, text: str, reply_markup=None):
    # Hardware-like stop check: if recently requested, silence all output
    uid = update.effective_user.id if update.effective_user else 0
    if uid and _is_stopping(uid):
        return None

    message_obj = update.message or (update.callback_query.message if update.callback_query else None)
    if not message_obj:
        return None
    formatted = _telegram_format(text)
    try:
        return await message_obj.reply_text(formatted, parse_mode=_telegram_parse_mode(), reply_markup=reply_markup)
    except Exception as e:
        logger.warning("Telegram formatted reply failed: %s | text=%r | formatted=%r", e, text[:300], formatted[:300])
        try:
            return await message_obj.reply_text(text, reply_markup=reply_markup)
        except Exception as e2:
            logger.error("Telegram raw reply failed: %s | text=%r", e2, text[:300])
            return None


def _tool_status_label(tool_name: str) -> str:
    mapping = {
        "calculator": "🧮 در حال اجرای ماشین‌حساب...",
        "web_search": "🌐 در حال جستجو در وب...",
        "pdf_generator": "📄 در حال ساخت PDF...",
        "send_file": "📤 در حال ارسال فایل...",
    }
    return mapping.get(tool_name, f"🛠️ در حال اجرای ابزار {tool_name}...")


def _cleanup_expired_generated_pdfs(*, now: datetime | None = None) -> int:
    if not os.path.isdir(GENERATED_PDF_DIR):
        return 0
    current_time = now or _utcnow()
    deleted_count = 0
    try:
        entries = os.listdir(GENERATED_PDF_DIR)
    except OSError:
        return 0
    for entry in entries:
        if not entry.lower().endswith(".pdf"):
            continue
        path = os.path.join(GENERATED_PDF_DIR, entry)
        if not os.path.isfile(path):
            continue
        try:
            modified_at = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
            if (current_time - modified_at).total_seconds() >= GENERATED_PDF_TTL_SECONDS:
                os.remove(path)
                deleted_count += 1
        except OSError:
            continue
    return deleted_count


def _resolve_generated_pdf_path(tool_result: dict) -> tuple[str, str] | None:
    storage_path_raw = tool_result.get("storage_path")
    if not isinstance(storage_path_raw, str) or not storage_path_raw.strip():
        return None
    abs_path = os.path.abspath(storage_path_raw.strip())
    generated_root = os.path.abspath(GENERATED_PDF_DIR)
    if not abs_path.startswith(f"{generated_root}{os.sep}"):
        return None
    if not os.path.isfile(abs_path):
        return None
    file_name = os.path.basename(abs_path)
    return abs_path, file_name


async def _maybe_upload_generated_file_to_chat(
    update: Update,
    *,
    tool_name: str | None,
    tool_result: dict | None,
) -> bool:
    if not isinstance(tool_result, dict) or tool_result.get("ok") is not True:
        return False
    
    storage_path_raw = tool_result.get("storage_path")
    if not isinstance(storage_path_raw, str) or not storage_path_raw.strip():
        return False

    abs_path = os.path.abspath(storage_path_raw.strip())
    
    if not os.path.isfile(abs_path):
        return False
        
    file_name = os.path.basename(abs_path)
    ext = os.path.splitext(file_name)[1].lower()
    
    icons = {
        ".pdf": "📄",
        ".docx": "📝",
        ".xlsx": "📊",
        ".pptx": "📽",
        ".csv": "📑",
        ".txt": "📃"
    }
    icon = icons.get(ext, "📁")
    type_label = ext[1:].upper() if ext else "File"
    
    warning = tool_result.get("warning")
    if isinstance(warning, str) and warning.strip():
        caption = f"{icon} فایل {type_label} آماده شد.\n⚠️ {warning.strip()}"
    else:
        caption = f"{icon} فایل {type_label} آماده شد."

    try:
        with open(abs_path, "rb") as file_obj:
            await update.message.reply_document(
                document=file_obj,
                filename=file_name,
                caption=caption,
            )
        _cleanup_expired_generated_pdfs()
        return True
    except Exception as exc:
        logger.warning("Failed to upload generated file to chat: %s", exc)
        return False


def _sanitize_tool_result_for_llm(tool_name: str | None, result: Any, *, uploaded_to_chat: bool) -> Any:
    if tool_name != "pdf_generator" or not isinstance(result, dict):
        return result
    sanitized = dict(result)
    if uploaded_to_chat:
        sanitized["delivered_in_chat"] = True
        sanitized["delivery_channel"] = "telegram_document"
        sanitized.pop("download_url", None)
        sanitized.pop("storage_path", None)
        sanitized.pop("pdf_base64", None)
    return sanitized


async def _send_generated_files(update: Update, generated_files: list[dict]):
    """Send files generated by Codex (images, documents) to the user via the bot."""
    if not generated_files:
        return

    bot = update.get_bot() if hasattr(update, "get_bot") else getattr(update, "_bot", None)
    if not bot:
        return

    chat_id = update.effective_chat.id
    for gf in generated_files:
        try:
            file_path = gf.get("path", "")
            filename = gf.get("filename", "file")
            file_type = gf.get("type", "document")

            if not file_path or not os.path.exists(file_path):
                continue

            if file_type == "image":
                with open(file_path, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f, caption=f"🖼️ {filename}")
            else:
                with open(file_path, "rb") as f:
                    await bot.send_document(chat_id=chat_id, document=f, filename=filename, caption=f"📄 {filename}")

            logger.info(f"Sent generated file to user: {filename}")
        except Exception as e:
            logger.warning(f"Failed to send generated file {gf.get('filename')}: {e}")


async def _send_final_response(update: Update, sent_msg, text: str, reply_markup=None, generated_files: list[dict] | None = None):
    if text:
        text = text.replace('\u200b', '').replace('\u200e', '').replace('\u200f', '').replace('\u200c', '').replace('\u200d', '')
        # Clean up any leftover status tags (like '⌛' or '⏳') and dots from the beginning of the text
        import re
        text = re.sub(r'^(?:[⌛⏳✍️🔄⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]|در حال پردازش|✅|⏳|\.)+[\s\n]*', '', text).strip()
    if not text or not text.strip():
        text = "✅ عملیات با موفقیت انجام شد."

    if len(text) <= 4096:
        try:
            if sent_msg:
                await _send_or_edit_formatted(sent_msg, text, reply_markup=reply_markup)
            else:
                await _reply_formatted(update, text, reply_markup=reply_markup)
        except Exception:
            pass
        return

    try:
        if sent_msg:
            await _send_or_edit_formatted(sent_msg, text[:4000] + "\n...", reply_markup=None)
        else:
            await _reply_formatted(update, text[:4000] + "\n...", reply_markup=None)
    except Exception:
        pass
    remaining = text[4000:]
    chunks = list(range(0, len(remaining), 4096))
    for idx, i in enumerate(chunks):
        is_last = idx == len(chunks) - 1
        markup = reply_markup if is_last else None
        await _reply_formatted(update, remaining[i:i + 4096], reply_markup=markup)

    if generated_files:
        await _send_generated_files(update, generated_files)


def _onboarding_kb(need_phone: bool = True) -> InlineKeyboardMarkup | None:
    if not need_phone:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 شماره تماس", callback_data="share_contact_request")],
    ])


def _cancel_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[CANCEL_TEXT]], resize_keyboard=True, one_time_keyboard=True)


def _topup_promo_reply_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [TOPUP_PROMO_SKIP_TEXT],
            [CANCEL_TEXT],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _contact_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📱 شماره منو بفرست", request_contact=True)],
            [CANCEL_TEXT],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _missing_phone(user: UserPreference) -> bool:
    return not bool((user.phone_number or "").strip())


def _missing_preferred_name(user: UserPreference) -> bool:
    return not bool((user.preferred_name or "").strip())


async def _prompt_onboarding(
    message_obj,
    first_name: str | None = None,
    *,
    need_phone: bool,
    need_name: bool,
):
    greeting_name = (first_name or "").strip()
    greeting = f"سلام {greeting_name} 👋\n\n" if greeting_name else "سلام 👋\n\n"
    if need_phone and need_name:
        body = "برای شروع لطفاً ثبت‌نام رو کامل کن.\nاول شماره‌ات رو بفرست (با دکمه یا تایپ شماره)، بعد اسمت رو ثبت می‌کنیم."
    elif need_phone:
        body = "برای تکمیل حساب، لطفاً شماره‌ات رو بفرست یا همینجا تایپ کن."
    elif need_name:
        body = "اسم دلخواهت رو بگو تا با همون صدات کنم."
    else:
        body = "ثبت‌نامت کامله."
    await message_obj.reply_text(
        f"{greeting}{body}",
        reply_markup=_onboarding_kb(need_phone=need_phone),
    )


def _user_onboarding_completed(user: UserPreference) -> bool:
    if user.is_admin:
        return True
    
    # We no longer require phone or name by default to allow users to start chatting immediately.
    # Users can still provide them later in the Account section.
    
    status = (user.account_status or "").strip().lower()
    if status in BLOCKED_ACCOUNT_STATUSES:
        return False
    
    # All other statuses (including pending_onboarding) are considered "completed" 
    # for the purpose of allowing them to proceed to the main menu/chat.
    return True


def _mark_onboarding_pending(user: UserPreference):
    if user.is_admin:
        return
    current = (user.account_status or "").strip().lower()
    if current in BLOCKED_ACCOUNT_STATUSES:
        return
    if current not in ONBOARDING_PENDING_STATUSES:
        user.account_status = "pending_onboarding"


async def _log_referral_event(db: AsyncSession, user: UserPreference, event_type: str, amount_usd: float = None):
    if user.referral_campaign_id:
        event = ReferralEvent(
            campaign_id=user.referral_campaign_id,
            user_id=user.id,
            event_type=event_type,
            amount_usd=amount_usd
        )
        db.add(event)
        await db.commit()


def _mark_onboarding_complete(user: UserPreference):
    if user.is_admin:
        return
    current = (user.account_status or "").strip().lower()
    if current in BLOCKED_ACCOUNT_STATUSES:
        return
    user.account_status = "active"


def _parse_usage_token(value: object) -> int:
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


def _extract_usage_tokens(usage: dict | None) -> tuple[int, int]:
    if not isinstance(usage, dict):
        return 0, 0
    input_tokens = _parse_usage_token(usage.get("prompt_tokens"))
    if input_tokens == 0:
        input_tokens = _parse_usage_token(usage.get("input_tokens"))
    if input_tokens == 0:
        input_tokens = _parse_usage_token(usage.get("prompt_token_count"))
    if input_tokens == 0:
        input_tokens = _parse_usage_token(usage.get("promptTokenCount"))
    output_tokens = _parse_usage_token(usage.get("completion_tokens"))
    if output_tokens == 0:
        output_tokens = _parse_usage_token(usage.get("output_tokens"))
    if output_tokens == 0:
        output_tokens = _parse_usage_token(usage.get("candidates_token_count"))
    if output_tokens == 0:
        output_tokens = _parse_usage_token(usage.get("candidatesTokenCount"))
    if output_tokens == 0:
        total_tokens = _parse_usage_token(usage.get("total_tokens"))
        if total_tokens == 0:
            total_tokens = _parse_usage_token(usage.get("totalTokenCount"))
        if total_tokens > input_tokens:
            output_tokens = total_tokens - input_tokens
    return input_tokens, output_tokens


def _sum_usage_tokens(usages: list[dict | None]) -> tuple[int, int]:
    input_total = 0
    output_total = 0
    for usage in usages:
        inp, out = _extract_usage_tokens(usage)
        input_total += inp
        output_total += out
    return input_total, output_total


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 1
    return max(1, (len(text) + 3) // 4)


def _estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        role = str(msg.get("role") or "")
        total += max(2, len(role))
        content = msg.get("content")
        if isinstance(content, str):
            total += _estimate_text_tokens(content)
            continue
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += _estimate_text_tokens(str(part.get("text") or ""))
                elif isinstance(part, dict) and part.get("type") == "image_url":
                    total += 250
                else:
                    total += _estimate_text_tokens(str(part))
            continue
        total += _estimate_text_tokens(str(content))
    return max(total, 1)


def _calculate_standard_cost_usd(model: DBModel, input_tokens: int, output_tokens: int) -> float:
    price_in = float(model.pricing_input or 0.0)
    price_out = float(model.pricing_output or 0.0)
    return max(0.0, ((input_tokens / 1_000_000.0) * price_in) + ((output_tokens / 1_000_000.0) * price_out))


@dataclass(frozen=True)
class ChatUsageQuoteUsd:
    global_api_cost_usd: float
    billable_cost_usd: float
    markup_percent: float
    pricing_snapshot: dict


async def _get_chat_cost_usd(db: AsyncSession, user_id: int, model: DBModel, chat_id: int, input_tokens: int, output_tokens: int) -> float:
    standard_cost = _calculate_standard_cost_usd(model, input_tokens, output_tokens)
    from app.services.subscription_service import evaluate_usage_cost
    final_cost, _ = await evaluate_usage_cost(db, user_id, model.id, chat_id, standard_cost, input_tokens, output_tokens)
    return final_cost


async def _get_chat_quote_usd(db: AsyncSession, model: DBModel, input_tokens: int, output_tokens: int) -> ChatUsageQuoteUsd:
    from app.services.toman_billing_service import DEFAULT_API_MARKUP_PERCENT, get_or_create_subscription_config

    config = await get_or_create_subscription_config(db)
    try:
        markup_percent = max(0.0, float(config.api_markup_percent))
    except (TypeError, ValueError):
        markup_percent = DEFAULT_API_MARKUP_PERCENT
    global_cost = _calculate_standard_cost_usd(model, input_tokens, output_tokens)
    billable_cost = global_cost * (1 + (markup_percent / 100.0))
    return ChatUsageQuoteUsd(
        global_api_cost_usd=global_cost,
        billable_cost_usd=billable_cost,
        markup_percent=markup_percent,
        pricing_snapshot={
            "model_id": getattr(model, "id", None),
            "model_name": getattr(model, "name", None),
            "pricing_input_usd_per_1m": float(getattr(model, "pricing_input", 0.0) or 0.0),
            "pricing_output_usd_per_1m": float(getattr(model, "pricing_output", 0.0) or 0.0),
        },
    )


async def _get_chat_quote_toman(db: AsyncSession, model: DBModel, input_tokens: int, output_tokens: int):
    from app.services.toman_billing_service import quote_chat_usage_toman

    return await quote_chat_usage_toman(db, model=model, input_tokens=input_tokens, output_tokens=output_tokens)


def _format_toman(amount: int | float | None) -> str:
    return f"{int(amount or 0):,} تومان"


async def _toman_balance(db: AsyncSession, user: UserPreference) -> int:
    from app.services.toman_billing_service import get_or_create_billing_account

    account = await get_or_create_billing_account(db, user)
    return int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)


async def _has_toman_credit_for_cost(
    db: AsyncSession, 
    user: UserPreference, 
    model: DBModel, 
    input_tokens: int, 
    output_tokens: int
) -> tuple[bool, str, UserSubscription | None]:
    if getattr(user, "is_admin", False):
        return True, "admin", None
    
    from app.services.toman_billing_service import check_chat_usage_permission_toman
    res = await check_chat_usage_permission_toman(
        db,
        user=user,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens
    )
    return res.ok, res.reason or "insufficient_toman_credit", res.user_sub


def _limit_reached_text(reason: str, user_sub: UserSubscription | None) -> str:
    if reason == "cooldown_limit_reached":
        wait_time = ""
        if user_sub and user_sub.cooldown_ends_at:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            delta = user_sub.cooldown_ends_at - now
            minutes = max(1, int(delta.total_seconds() / 60))
            wait_time = f" حدود {minutes} دقیقه دیگر."
        return f"🚨 لیمیت مصرف دوره‌ای شما به پایان رسیده است.{wait_time}\nمی‌توانید صبر کنید یا با شارژ حساب (PAYG) ادامه دهید."
    elif reason == "cooldown_payg_available":
        wait_time = ""
        if user_sub and user_sub.cooldown_ends_at:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            delta = user_sub.cooldown_ends_at - now
            minutes = max(1, int(delta.total_seconds() / 60))
            wait_time = f" حدود {minutes} دقیقه دیگر."
        return f"⚠️ لیمیت مصرف دوره‌ای شما به پایان رسیده است.{wait_time}\nمی‌توانید صبر کنید یا از موجودی کیف پول خود استفاده کنید."
    elif reason == "weekly_limit_reached":
        return "🚨 لیمیت مصرف هفتگی شما به پایان رسیده است.\nمی‌توانید تا ریست شدن هفته صبر کنید یا با شارژ حساب (PAYG) ادامه دهید."
    elif reason == "weekly_limit_payg_available":
        return "⚠️ لیمیت مصرف هفتگی شما به پایان رسیده است.\nمی‌توانید صبر کنید یا از موجودی کیف پول خود استفاده کنید."
    return "🚨 لیمیت اشتراک شما به پایان رسیده است."


def _limit_reached_kb(reason: str = "") -> InlineKeyboardMarkup:
    if reason in ("cooldown_payg_available", "weekly_limit_payg_available"):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 استفاده از موجودی", callback_data="payg_confirm")],
            [InlineKeyboardButton("⏳ صبر می‌کنم", callback_data="limit_wait")],
            [InlineKeyboardButton("➕ شارژ اعتبار", callback_data="toman_topup_start")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تلاش مجدد", callback_data="retry_last_prompt")],
        [InlineKeyboardButton("➕ شارژ اعتبار", callback_data="toman_topup_start")]
    ])


def _insufficient_toman_credit_text(*, needed_toman: int, balance_toman: int, action_label: str) -> str:
    return (
        f"❌ اعتبار کافی نیست برای {action_label}.\n"
        f"اعتبار فعلی: {_format_toman(balance_toman)}\n"
        f"حداقل اعتبار لازم: {_format_toman(needed_toman)}"
    )


def _toman_usage_metadata(quote, *, input_tokens: int, output_tokens: int) -> dict:
    return {
        "global_api_cost_usd": quote.global_api_cost_usd,
        "base_cost_toman": quote.base_cost_toman,
        "billable_cost_toman": quote.billable_cost_toman,
        "usd_to_toman_rate": quote.usd_to_toman_rate,
        "api_markup_percent": quote.markup_percent,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "pricing_snapshot": quote.pricing_snapshot,
    }


def _usd_usage_metadata(quote: ChatUsageQuoteUsd, *, input_tokens: int, output_tokens: int) -> dict:
    return {
        "global_api_cost_usd": quote.global_api_cost_usd,
        "billable_cost_usd": quote.billable_cost_usd,
        "api_markup_percent": quote.markup_percent,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "pricing_snapshot": quote.pricing_snapshot,
    }



def _usd_to_minor(amount_usd: float) -> int:
    return int(round(max(0.0, float(amount_usd or 0.0)) * 1_000_000))


def _signed_usd_to_minor(amount_usd: float) -> int:
    return int(round(float(amount_usd or 0.0) * 1_000_000))


def _minor_to_usd(amount_minor: int) -> float:
    return float(amount_minor or 0) / 1_000_000.0


def _decimal_to_plain(value: Decimal, places: Decimal = TOPUP_USD_DECIMALS) -> str:
    quantized = value.quantize(places, rounding=ROUND_HALF_UP)
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _parse_topup_usd_amount(text: str | None) -> Decimal | None:
    raw = (text or "").strip()
    if not raw:
        return None
    normalized = raw.translate(_DIGIT_TRANSLATION).lower()
    normalized = normalized.replace("٫", ".").replace("٬", "").replace(",", "")
    normalized = normalized.replace("$", "").replace("usd", "").replace("usdt", "")
    normalized = normalized.replace("دلار", "")
    normalized = re.sub(r"\s+", "", normalized)
    if not normalized:
        return None
    try:
        amount = Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None
    amount = amount.quantize(TOPUP_USD_DECIMALS, rounding=ROUND_HALF_UP)
    if amount < MIN_TOPUP_USD_AMOUNT or amount > MAX_TOPUP_USD_AMOUNT:
        return None
    return amount


def _parse_toman_amount(text: str | None) -> int | None:
    raw = (text or "").strip()
    if not raw:
        return None
    normalized = raw.translate(_DIGIT_TRANSLATION).lower()
    normalized = normalized.replace("٬", "").replace(",", "")
    normalized = normalized.replace("تومان", "").replace("تومن", "").replace("irt", "")
    normalized = re.sub(r"\s+", "", normalized)
    if not normalized or not normalized.isdigit():
        return None
    amount = int(normalized)
    if amount <= 0 or amount > 100_000_000:
        return None
    return amount


def _parse_topup_promo_code(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    normalized = raw.translate(_DIGIT_TRANSLATION).strip()
    lowered = re.sub(r"\s+", "", normalized.lower())
    if normalized == TOPUP_PROMO_SKIP_TEXT or lowered in {"skip", "ندارم", "بدونکد", "nopromo"}:
        return None
    code = normalize_promo_code(normalized)
    if not code:
        return None
    if len(code) > MAX_TOPUP_PROMO_CODE_LEN:
        return ""
    if "|" in code:
        return ""
    return code


def _promo_error_to_fa(message: str) -> str:
    mapping = {
        "code is required": "کد وارد نشده است.",
        "promo code is invalid or inactive": "این کد معتبر نیست یا غیرفعال شده است.",
        "promo code has expired": "این کد منقضی شده است.",
        "promo code redemption limit reached": "ظرفیت استفاده از این کد تمام شده است.",
        "you have already used this promo code": "این کد را قبلاً استفاده کرده‌ای.",
        "promo code bonus is zero for this charge amount": "برای این مبلغ، بونس این کد صفر است.",
        "total credit amount is invalid": "اعتبار قابل اعمال این کد معتبر نیست.",
    }
    text = (message or "").strip()
    if text.startswith("minimum charge for this code is $"):
        minimum = text.removeprefix("minimum charge for this code is $").strip()
        return f"حداقل مبلغ لازم برای این کد ${minimum} است."
    if text.startswith("minimum charge for this code is "):
        minimum = text.removeprefix("minimum charge for this code is ").replace(" تومان", "").strip()
        return f"حداقل مبلغ لازم برای این کد {minimum} تومان است."
    return mapping.get(text, text or "اعمال کوپن ناموفق بود.")


def _build_topup_payload(
    *,
    user_id: int,
    usd_amount: Decimal,
    total_rial: int,
    usdt_price_rial: int,
    promo_code: str | None = None,
) -> str:
    now_unix = int(datetime.now(timezone.utc).timestamp())
    safe_promo_code = normalize_promo_code(promo_code)
    if "|" in safe_promo_code:
        raise ValueError("invalid promo code for payload")
    payload = "|".join(
        [
            TOPUP_PAYLOAD_PREFIX,
            str(int(user_id)),
            _decimal_to_plain(usd_amount),
            str(int(total_rial)),
            str(int(usdt_price_rial)),
            str(now_unix),
            safe_promo_code,
        ]
    )
    if len(payload.encode("utf-8")) > 120:
        raise ValueError("topup payload is too long")
    return payload


def _parse_topup_payload(payload: str | None) -> dict | None:
    raw = (payload or "").strip()
    if not raw:
        return None
    parts = raw.split("|")
    if len(parts) not in {6, 7} or parts[0] != TOPUP_PAYLOAD_PREFIX:
        return None
    try:
        user_id = int(parts[1])
        usd_amount = Decimal(parts[2]).quantize(TOPUP_USD_DECIMALS, rounding=ROUND_HALF_UP)
        total_rial = int(parts[3])
        usdt_price_rial = int(parts[4])
        created_at = int(parts[5])
    except (InvalidOperation, ValueError):
        return None
    promo_code = normalize_promo_code(parts[6] if len(parts) == 7 else "")
    if len(promo_code) > MAX_TOPUP_PROMO_CODE_LEN:
        return None
    if user_id <= 0 or total_rial <= 0 or usdt_price_rial <= 0 or created_at <= 0:
        return None
    if usd_amount < MIN_TOPUP_USD_AMOUNT or usd_amount > MAX_TOPUP_USD_AMOUNT:
        return None
    return {
        "user_id": user_id,
        "usd_amount": usd_amount,
        "total_rial": total_rial,
        "usdt_price_rial": usdt_price_rial,
        "created_at": created_at,
        "promo_code": promo_code or None,
    }


def _build_subscription_payload(
    *,
    user_id: int,
    plan_id: int,
    wallet_payment_toman: int,
    total_rial: int,
) -> str:
    now_unix = int(datetime.now(timezone.utc).timestamp())
    payload = "|".join(
        [
            SUBSCRIPTION_PAYLOAD_PREFIX,
            str(int(user_id)),
            str(int(plan_id)),
            str(max(0, int(wallet_payment_toman or 0))),
            str(int(total_rial)),
            str(now_unix),
        ]
    )
    if len(payload.encode("utf-8")) > 120:
        raise ValueError("subscription payload is too long")
    return payload


def _parse_subscription_payload(payload: str | None) -> dict | None:
    raw = (payload or "").strip()
    if not raw:
        return None
    parts = raw.split("|")
    if len(parts) != 6 or parts[0] != SUBSCRIPTION_PAYLOAD_PREFIX:
        return None
    try:
        user_id = int(parts[1])
        plan_id = int(parts[2])
        wallet_payment_toman = int(parts[3])
        total_rial = int(parts[4])
        created_at = int(parts[5])
    except ValueError:
        return None
    if user_id <= 0 or plan_id <= 0 or wallet_payment_toman < 0 or total_rial <= 0 or created_at <= 0:
        return None
    return {
        "user_id": user_id,
        "plan_id": plan_id,
        "wallet_payment_toman": wallet_payment_toman,
        "total_rial": total_rial,
        "created_at": created_at,
    }


def _build_toman_topup_payload(
    *,
    user_id: int,
    credit_amount_toman: int,
    payment_due_toman: int,
    total_rial: int,
) -> str:
    now_unix = int(datetime.now(timezone.utc).timestamp())
    payload = "|".join(
        [
            TOMAN_TOPUP_PAYLOAD_PREFIX,
            str(int(user_id)),
            str(max(0, int(credit_amount_toman or 0))),
            str(max(0, int(payment_due_toman or 0))),
            str(int(total_rial)),
            str(now_unix),
        ]
    )
    if len(payload.encode("utf-8")) > 120:
        raise ValueError("toman topup payload is too long")
    return payload


def _parse_toman_topup_payload(payload: str | None) -> dict | None:
    raw = (payload or "").strip()
    if not raw:
        return None
    parts = raw.split("|")
    if len(parts) != 6 or parts[0] != TOMAN_TOPUP_PAYLOAD_PREFIX:
        return None
    try:
        user_id = int(parts[1])
        credit_amount_toman = int(parts[2])
        payment_due_toman = int(parts[3])
        total_rial = int(parts[4])
        created_at = int(parts[5])
    except ValueError:
        return None
    if user_id <= 0 or credit_amount_toman <= 0 or payment_due_toman <= 0 or total_rial <= 0 or created_at <= 0:
        return None
    return {
        "user_id": user_id,
        "credit_amount_toman": credit_amount_toman,
        "payment_due_toman": payment_due_toman,
        "total_rial": total_rial,
        "created_at": created_at,
    }


def _parse_payment_payload(payload: str | None) -> dict | None:
    topup = _parse_topup_payload(payload)
    if topup is not None:
        return {"type": "topup", "topup": topup}
    subscription = _parse_subscription_payload(payload)
    if subscription is not None:
        return {"type": "subscription", "subscription": subscription}
    toman_topup = _parse_toman_topup_payload(payload)
    if toman_topup is not None:
        return {"type": "toman_topup", "toman_topup": toman_topup}
    return None


def _extract_nobitex_usdt_stat(stats_payload: dict) -> dict | None:
    stats = stats_payload.get("stats")
    if not isinstance(stats, dict):
        return None
    for key in ("usdt-rls", "usdt-irt", "USDT-RLS", "USDT-IRT"):
        value = stats.get(key)
        if isinstance(value, dict):
            return value
    for key, value in stats.items():
        if not isinstance(value, dict):
            continue
        norm = str(key).strip().lower().replace("_", "-")
        if "usdt" in norm and ("-rls" in norm or "-irt" in norm):
            return value
    return None


def _extract_positive_rial_price(stat: dict) -> int | None:
    for field in ("latest", "bestSell", "mark", "bestBuy"):
        raw = stat.get(field)
        if raw is None:
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            continue
        if value > 0:
            return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return None


async def _fetch_nobitex_usdt_price_rial() -> int:
    async with httpx.AsyncClient(timeout=NOBITEX_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(
            NOBITEX_MARKET_STATS_URL,
            params={"srcCurrency": "usdt", "dstCurrency": "rls"},
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise ValueError("nobitex stats response is not ok")
    stat = _extract_nobitex_usdt_stat(payload)
    if not stat:
        raise ValueError("usdt stats not found in nobitex response")
    price = _extract_positive_rial_price(stat)
    if not price:
        raise ValueError("usdt rial price is missing in nobitex response")
    return int(price)


def _usd_to_rial(usd_amount: Decimal, usdt_price_rial: int) -> int:
    total = (usd_amount * Decimal(int(usdt_price_rial))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(1, int(total))


def _rial_to_toman(rial_amount: int) -> int:
    toman = Decimal(int(rial_amount)) / Decimal("10")
    return int(toman.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _toman_to_usd_decimal(toman_amount: int, usdt_price_rial: int) -> Decimal:
    if usdt_price_rial <= 0:
        raise ValueError("usdt rial price must be positive")
    usd = (Decimal(int(toman_amount or 0)) * Decimal("10")) / Decimal(int(usdt_price_rial))
    return usd.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


async def _send_bale_topup_invoice(
    *,
    bot,
    db: AsyncSession,
    user: UserPreference,
    chat_id: int,
    user_id: int,
    usd_amount: Decimal,
    promo_code: str | None = None,
) -> dict:
    if not BALE_WALLET_PROVIDER_TOKEN:
        raise ValueError("BALE_WALLET_PROVIDER_TOKEN is not set")
    from app.services.toman_billing_service import quote_toman_topup_payment

    usdt_price_rial = await _fetch_nobitex_usdt_price_rial()
    credit_rial = _usd_to_rial(usd_amount, usdt_price_rial)
    credit_toman = _rial_to_toman(credit_rial)
    quote = await quote_toman_topup_payment(db, user=user, credit_amount_toman=credit_toman)
    total_rial = max(1, int(quote.payment_due_toman) * 10)
    payload = _build_topup_payload(
        user_id=user_id,
        usd_amount=usd_amount,
        total_rial=total_rial,
        usdt_price_rial=usdt_price_rial,
        promo_code=promo_code,
    )
    usd_label = _decimal_to_plain(usd_amount)
    total_toman = _rial_to_toman(total_rial)
    discount_line = f" | تخفیف: {quote.discount_toman:,} تومان" if quote.discount_toman else ""
    description = (
        f"شارژ {usd_label} دلار | نرخ هر USDT: {usdt_price_rial:,} ریال | "
        f"جمع تقریبی: {total_toman:,} تومان{discount_line}"
    )[:255]
    await bot.send_invoice(
        chat_id=chat_id,
        title="شارژ حساب دکتر بز",
        description=description,
        payload=payload,
        provider_token=BALE_WALLET_PROVIDER_TOKEN,
        currency="IRR",
        prices=[LabeledPrice(label="شارژ حساب", amount=total_rial)],
    )
    return {
        "usd_amount": usd_amount,
        "usdt_price_rial": usdt_price_rial,
        "total_rial": total_rial,
        "total_toman": total_toman,
        "credit_toman": credit_toman,
        "normal_payment_toman": quote.normal_payment_toman,
        "discount_toman": quote.discount_toman,
        "payload": payload,
        "promo_code": normalize_promo_code(promo_code) or None,
    }


async def _send_bale_subscription_invoice(
    *,
    bot,
    chat_id: int,
    user_id: int,
    plan_id: int,
    plan_name: str,
    payable_toman: int,
    wallet_payment_toman: int = 0,
) -> dict:
    if not BALE_WALLET_PROVIDER_TOKEN:
        raise ValueError("BALE_WALLET_PROVIDER_TOKEN is not set")
    total_toman = max(0, int(payable_toman or 0))
    if total_toman <= 0:
        raise ValueError("subscription payable amount must be positive")
    total_rial = total_toman * 10
    payload = _build_subscription_payload(
        user_id=user_id,
        plan_id=plan_id,
        wallet_payment_toman=max(0, int(wallet_payment_toman or 0)),
        total_rial=total_rial,
    )
    wallet_line = f" | پرداخت از کیف پول: {int(wallet_payment_toman or 0):,} تومان" if wallet_payment_toman else ""
    description = f"خرید اشتراک {plan_name} | مبلغ پرداخت آنلاین: {total_toman:,} تومان{wallet_line}"[:255]
    await bot.send_invoice(
        chat_id=chat_id,
        title=f"خرید اشتراک {plan_name}",
        description=description,
        payload=payload,
        provider_token=BALE_WALLET_PROVIDER_TOKEN,
        currency="IRR",
        prices=[LabeledPrice(label=f"اشتراک {plan_name}", amount=total_rial)],
    )
    return {
        "plan_id": int(plan_id),
        "plan_name": plan_name,
        "wallet_payment_toman": max(0, int(wallet_payment_toman or 0)),
        "total_rial": total_rial,
        "total_toman": total_toman,
        "payload": payload,
    }


async def _send_bale_toman_topup_invoice(
    *,
    bot,
    chat_id: int,
    user_id: int,
    credit_amount_toman: int,
    payment_due_toman: int,
) -> dict:
    if not BALE_WALLET_PROVIDER_TOKEN:
        raise ValueError("BALE_WALLET_PROVIDER_TOKEN is not set")
    credit_amount = max(0, int(credit_amount_toman or 0))
    payment_due = max(0, int(payment_due_toman or 0))
    if credit_amount <= 0 or payment_due <= 0:
        raise ValueError("toman topup amount must be positive")
    total_rial = payment_due * 10
    payload = _build_toman_topup_payload(
        user_id=user_id,
        credit_amount_toman=credit_amount,
        payment_due_toman=payment_due,
        total_rial=total_rial,
    )
    description = f"شارژ کیف پول اشتراک: {credit_amount:,} تومان | مبلغ پرداخت: {payment_due:,} تومان"[:255]
    await bot.send_invoice(
        chat_id=chat_id,
        title="شارژ اعتبار دکتر بز",
        description=description,
        payload=payload,
        provider_token=BALE_WALLET_PROVIDER_TOKEN,
        currency="IRR",
        prices=[LabeledPrice(label="شارژ اعتبار", amount=total_rial)],
    )
    return {
        "credit_amount_toman": credit_amount,
        "payment_due_toman": payment_due,
        "total_rial": total_rial,
        "total_toman": payment_due,
        "payload": payload,
    }


async def notify_user_payment_result(
    user_telegram_id: int,
    *,
    approved: bool,
    amount_toman: int,
    payment_type: str = "topup",
    admin_note: str | None = None,
):
    """Send a notification to a user about payment approval/rejection via the main bot."""
    if not BOT_TOKEN:
        return

    api_base = BALE_API_BASE_URL if _is_bale_platform() else "https://api.telegram.org/bot"
    if _is_bale_platform():
        url = f"{api_base}bot{BOT_TOKEN}/sendMessage"
    else:
        url = f"{api_base}{BOT_TOKEN}/sendMessage"

    if approved:
        if payment_type == "subscription":
            text = (
                "✅ پرداخت اشتراک شما تأیید شد!\n\n"
                f"مبلغ: {_format_toman(amount_toman)}\n"
                "اشتراک شما فعال شد و می‌توانید از تمام قابلیت‌ها استفاده کنید."
            )
        else:
            text = (
                "✅ واریزی شما تأیید شد!\n\n"
                f"مبلغ: {_format_toman(amount_toman)}\n"
                "اعتبار به کیف پول شما اضافه شد."
            )
    else:
        text = (
            "❌ پرداخت شما رد شد.\n\n"
            f"مبلغ: {_format_toman(amount_toman)}"
        )
        if admin_note:
            text += f"\n📝 یادداشت پشتیبانی: {admin_note}"
        text += "\n\nدر صورت نیاز با پشتیبانی تماس بگیرید."

    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(url, json={
                "chat_id": user_telegram_id,
                "text": text,
                "parse_mode": "Markdown",
            })
    except Exception:
        logger.exception("failed to send payment notification to user %s", user_telegram_id)


async def _apply_topup_credit(
    db: AsyncSession,
    *,
    user: UserPreference,
    usd_amount: Decimal,
    idempotency_key: str,
    metadata: dict | None = None,
) -> tuple[bool, float]:
    existing = (
        await db.execute(
            select(CreditLedgerEntry).where(CreditLedgerEntry.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.refresh(user)
        return False, _credit_balance(user)

    credit_usd = float(usd_amount)
    credit_minor = _usd_to_minor(credit_usd)
    if credit_minor <= 0:
        raise ValueError("topup amount must be positive")

    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalars().first()
    if wallet is None:
        opening_minor = _signed_usd_to_minor(float(user.credit_balance_usd or 0.0))
        wallet = Wallet(
            user_id=user.id,
            currency="USD",
            balance_minor=opening_minor,
            available_minor=opening_minor,
            held_minor=0,
            allow_negative=False,
            version=0,
        )
        db.add(wallet)
        await db.flush()

    wallet.balance_minor += credit_minor
    wallet.available_minor += credit_minor
    wallet.version = int(wallet.version or 0) + 1
    user.credit_balance_usd = _minor_to_usd(wallet.available_minor)
    
    # Pro Status tracking
    user.total_charged_usd = (user.total_charged_usd or 0.0) + float(usd_amount)
    if user.total_charged_usd >= 1.0:
        user.is_pro = True

    entry = CreditLedgerEntry(
        user_id=user.id,
        wallet_id=wallet.id,
        amount_delta_usd=credit_usd,
        amount_minor=credit_minor,
        balance_after_minor=wallet.balance_minor,
        available_after_minor=wallet.available_minor,
        held_after_minor=wallet.held_minor,
        currency=wallet.currency,
        direction="credit",
        entry_type="wallet_topup",
        status="posted",
        reason="bale wallet topup",
        idempotency_key=idempotency_key,
        metadata_json=metadata or {},
    )
    db.add(entry)

    if user.referral_campaign_id:
        ref_event = ReferralEvent(
            campaign_id=user.referral_campaign_id,
            user_id=user.id,
            event_type="purchase",
            amount_usd=float(usd_amount)
        )
        db.add(ref_event)

    await db.commit()
    await db.refresh(user)
    return True, _credit_balance(user)


async def _credit_subscription_gift_usd(
    db: AsyncSession,
    *,
    user: UserPreference,
    gift_toman: int,
    idempotency_key: str,
    metadata: dict | None = None,
) -> tuple[bool, float, Decimal]:
    """Deprecated: USD wallet no longer used. Gift is already credited in Toman by purchase_toman_subscription."""
    return True, 0.0, Decimal("0")


async def _debit_subscription_wallet_usd(
    db: AsyncSession,
    *,
    user: UserPreference,
    wallet_payment_toman: int,
    idempotency_key: str,
    metadata: dict | None = None,
) -> tuple[bool, float, Decimal]:
    """Debit Toman account for subscription wallet portion. Returns (ok, dummy_usd_balance, usd_debit)."""
    if wallet_payment_toman <= 0:
        return True, 0.0, Decimal("0")
    from app.services.toman_billing_service import charge_generic_usage_toman
    result = await charge_generic_usage_toman(
        db,
        user=user,
        cost_usd=0.0,
        entry_type="subscription_wallet_payment",
        reason="subscription payment from toman wallet",
        idempotency_key=idempotency_key,
        metadata={
            "wallet_payment_toman": int(wallet_payment_toman),
            **(metadata or {}),
        },
    )
    # We still return a Decimal(0) for USD debit to keep the calling signature compatible.
    return result.ok, 0.0, Decimal("0")


def _split_minor_equally(total_minor: int, members_count: int) -> list[int]:
    safe_count = max(1, int(members_count or 1))
    safe_total = max(0, int(total_minor or 0))
    base = safe_total // safe_count
    remainder = safe_total % safe_count
    shares = [base for _ in range(safe_count)]
    for idx in range(remainder):
        shares[idx] += 1
    return shares


def _normalize_group_trigger_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _default_group_trigger_phrases() -> list[str]:
    return [_normalize_group_trigger_phrase(item) for item in GROUP_DEFAULT_TRIGGER_PHRASES if item and str(item).strip()]


def _parse_group_trigger_phrases(value: object) -> list[str]:
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return _default_group_trigger_phrases()
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = [raw]
    elif isinstance(value, list):
        decoded = value
    else:
        decoded = []
    phrases = []
    for item in decoded:
        normalized = _normalize_group_trigger_phrase(str(item or ""))
        if normalized:
            phrases.append(normalized)
    if not phrases:
        return _default_group_trigger_phrases()
    unique_phrases: list[str] = []
    for phrase in phrases:
        if phrase not in unique_phrases:
            unique_phrases.append(phrase)
    return unique_phrases


def _extract_group_question(text_value: str, trigger_phrases: list[str]) -> tuple[str | None, str]:
    compact_text = re.sub(r"\s+", " ", str(text_value or "").strip())
    if not compact_text:
        return None, ""
    lowered = compact_text.lower()
    sorted_triggers = sorted((_normalize_group_trigger_phrase(item) for item in trigger_phrases), key=len, reverse=True)
    for trigger in sorted_triggers:
        if not trigger:
            continue
        pattern = re.compile(rf"^{re.escape(trigger)}(?:[\s:،,!?؟\-]+|$)", flags=re.IGNORECASE)
        match = pattern.match(lowered)
        if not match:
            continue
        question = compact_text[match.end():].strip()
        return trigger, question
    return None, ""


def _group_optin_keyboard(group_id: int, enabled: bool) -> InlineKeyboardMarkup:
    enable_text = "✅ فعال" if enabled else "فعال‌سازی پرداخت سهمی"
    disable_text = "⛔ غیرفعال‌سازی"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(enable_text, callback_data=f"groupopt_enable_{group_id}"),
                InlineKeyboardButton(disable_text, callback_data=f"groupopt_disable_{group_id}"),
            ],
            [InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"groupopt_refresh_{group_id}")],
            [InlineKeyboardButton("🔙 منوی اصلی", callback_data="cancel_main")],
        ]
    )


async def _ensure_group_tables(db: AsyncSession):
    del db
    global _GROUP_TABLES_READY
    _GROUP_TABLES_READY = True


def _row_to_group_dict(group: TelegramGroup) -> dict:
    payload = {
        "id": int(group.id),
        "telegram_chat_id": int(group.telegram_chat_id),
        "title": group.title,
        "chat_type": group.chat_type,
        "status": group.status,
        "trigger_phrases_json": group.trigger_phrases_json,
        "min_active_members": int(group.min_active_members or GROUP_MIN_ACTIVE_MEMBERS_DEFAULT),
        "app_chat_id": group.app_chat_id,
        "created_by_user_id": group.created_by_user_id,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }
    payload["trigger_phrases"] = _parse_group_trigger_phrases(payload.get("trigger_phrases_json"))
    return payload


async def _get_telegram_group_by_chat_id(db: AsyncSession, telegram_chat_id: int) -> dict | None:
    await _ensure_group_tables(db)
    row = (
        await db.execute(
            select(TelegramGroup).where(TelegramGroup.telegram_chat_id == int(telegram_chat_id))
        )
    ).scalar_one_or_none()
    if not row:
        return None
    return _row_to_group_dict(row)


async def _get_telegram_group_by_id(db: AsyncSession, group_id: int) -> dict | None:
    await _ensure_group_tables(db)
    row = (
        await db.execute(
            select(TelegramGroup).where(TelegramGroup.id == int(group_id))
        )
    ).scalar_one_or_none()
    if not row:
        return None
    return _row_to_group_dict(row)


async def _ensure_telegram_group_record(
    db: AsyncSession,
    *,
    telegram_chat_id: int,
    title: str | None,
    chat_type: str | None,
    created_by_user_id: int | None = None,
) -> tuple[dict, bool]:
    await _ensure_group_tables(db)
    existing = (
        await db.execute(
            select(TelegramGroup).where(TelegramGroup.telegram_chat_id == int(telegram_chat_id))
        )
    ).scalar_one_or_none()
    if existing:
        if title:
            existing.title = title
        if chat_type:
            existing.chat_type = chat_type
        if created_by_user_id and existing.created_by_user_id is None:
            existing.created_by_user_id = int(created_by_user_id)
        await db.flush()
        return _row_to_group_dict(existing), False

    group = TelegramGroup(
        telegram_chat_id=int(telegram_chat_id),
        title=title or "",
        chat_type=chat_type or "group",
        status="active",
        trigger_phrases_json=_default_group_trigger_phrases(),
        min_active_members=GROUP_MIN_ACTIVE_MEMBERS_DEFAULT,
        created_by_user_id=created_by_user_id,
    )
    db.add(group)
    await db.flush()
    return _row_to_group_dict(group), True


async def _set_telegram_group_status(db: AsyncSession, group_id: int, status: str):
    await _ensure_group_tables(db)
    group = await db.get(TelegramGroup, int(group_id))
    if group:
        group.status = status


async def _get_group_member_state(db: AsyncSession, group_id: int, user_id: int) -> dict | None:
    await _ensure_group_tables(db)
    row = (
        await db.execute(
            select(TelegramGroupMember).where(
                TelegramGroupMember.group_id == int(group_id),
                TelegramGroupMember.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not row:
        return None
    payload = {
        "id": row.id,
        "group_id": row.group_id,
        "user_id": row.user_id,
        "telegram_user_id": row.telegram_user_id,
        "status": row.status,
        "shared_billing_enabled": bool(row.shared_billing_enabled),
        "enabled_at": row.last_opt_in_at,
        "disabled_at": row.last_opt_out_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    return payload


async def _set_group_member_optin(
    db: AsyncSession,
    *,
    group_id: int,
    user: UserPreference,
    enabled: bool,
):
    await _ensure_group_tables(db)
    existing = (
        await db.execute(
            select(TelegramGroupMember).where(
                TelegramGroupMember.group_id == int(group_id),
                TelegramGroupMember.user_id == int(user.id),
            )
        )
    ).scalar_one_or_none()
    now_value = _utcnow()
    if existing:
        existing.telegram_user_id = int(user.telegram_user_id or 0) or None
        existing.status = "active"
        existing.shared_billing_enabled = bool(enabled)
        if enabled:
            existing.last_opt_in_at = now_value
            existing.last_opt_out_at = None
        else:
            existing.last_opt_out_at = now_value
        return
    db.add(
        TelegramGroupMember(
            group_id=int(group_id),
            user_id=int(user.id),
            telegram_user_id=int(user.telegram_user_id or 0) or None,
            status="active",
            shared_billing_enabled=bool(enabled),
            last_opt_in_at=now_value if enabled else None,
            last_opt_out_at=now_value if not enabled else None,
        )
    )


async def _list_active_group_payers(db: AsyncSession, group_id: int) -> list[UserPreference]:
    await _ensure_group_tables(db)
    members = await list_active_billing_members(db, group_id=int(group_id))
    return [member.user for member in members if member.user is not None]


async def _ensure_group_chat(db: AsyncSession, group_row: dict, model_id: int | None) -> Chat:
    app_chat_id = group_row.get("app_chat_id")
    if app_chat_id:
        chat = (await db.execute(select(Chat).where(Chat.id == int(app_chat_id)))).scalar_one_or_none()
        if chat:
            return chat
    chat_title = f"👥 {(group_row.get('title') or 'Telegram Group').strip()}"
    chat = Chat(title=chat_title[:200], model_id=model_id, project_id=None)
    db.add(chat)
    await db.flush()
    group = await db.get(TelegramGroup, int(group_row["id"]))
    if group:
        group.app_chat_id = int(chat.id)
    group_row["app_chat_id"] = chat.id
    return chat


async def _build_group_optin_deep_link(context: ContextTypes.DEFAULT_TYPE, group_id: int) -> str | None:
    username = context.bot.username
    if not username:
        try:
            me = await context.bot.get_me()
            username = me.username
        except Exception:
            username = None
    if not username:
        return None
    base = "https://ble.ir" if _is_bale_platform() else "https://t.me"
    return f"{base}/{username}?start={GROUP_OPTIN_START_PREFIX}{group_id}"


async def _build_project_share_deep_link(context: ContextTypes.DEFAULT_TYPE, token: str) -> str | None:
    username = context.bot.username
    if not username:
        try:
            me = await context.bot.get_me()
            username = me.username
        except Exception:
            username = None
    if not username:
        return None
    base = "https://ble.ir" if _is_bale_platform() else "https://t.me"
    return f"{base}/{username}?start={PROJECT_SHARE_START_PREFIX}{token}"


async def _send_project_share_callback_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    reply_markup=None,
    fallback_message=None,
):
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is None and fallback_message is not None:
        chat_id = getattr(fallback_message, "chat_id", None)
    if chat_id is not None:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            return
        except Exception:
            logger.exception("Could not send project share callback message via bot.send_message")

    if fallback_message is not None:
        try:
            await fallback_message.reply_text(text, reply_markup=reply_markup, do_quote=False)
        except Exception:
            logger.exception("Could not send project share callback fallback message")


async def _build_group_optin_panel_text(db: AsyncSession, *, group_id: int, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    group = await _get_telegram_group_by_id(db, group_id)
    if not group:
        return "❌ گروه پیدا نشد یا در دسترس نیست.", InlineKeyboardMarkup([])
    member_state = await _get_group_member_state(db, group_id, user_id)
    enabled = bool(member_state and member_state.get("shared_billing_enabled"))
    active_count = (
        await db.execute(
            select(func.count(TelegramGroupMember.id)).where(
                TelegramGroupMember.group_id == int(group_id),
                TelegramGroupMember.status == "active",
                TelegramGroupMember.shared_billing_enabled == True,
            )
        )
    ).scalar() or 0
    status_text = "✅ فعال" if enabled else "❌ غیرفعال"
    text_value = (
        f"👥 گروه: {group.get('title') or group.get('telegram_chat_id')}\n"
        f"وضعیت پرداخت سهمی شما: {status_text}\n"
        f"تعداد اعضای پرداخت‌کننده فعال: {int(active_count)}\n"
        f"حداقل اعضای فعال لازم: {group.get('min_active_members')}\n\n"
        "با فعال‌سازی، در درخواست‌های گروهی سهم مساوی از هزینه پاسخ از حساب شما کسر می‌شود."
    )
    return text_value, _group_optin_keyboard(group_id, enabled)


async def _telegram_user_is_group_member(context: ContextTypes.DEFAULT_TYPE, group: dict, user: UserPreference) -> bool:
    telegram_user_id = int(user.telegram_user_id or 0)
    telegram_chat_id = group.get("telegram_chat_id")
    if not telegram_user_id or not telegram_chat_id:
        return False
    try:
        member = await context.bot.get_chat_member(int(telegram_chat_id), telegram_user_id)
    except Exception as exc:
        logger.warning("Could not verify Telegram group membership: group=%s user=%s error=%s", telegram_chat_id, telegram_user_id, exc)
        return False
    status = (getattr(member, "status", "") or "").lower()
    return status not in {"left", "kicked"}


async def _create_group_usage_event_row(
    db: AsyncSession,
    *,
    group_id: int,
    usage_event_id: int | None,
    request_id: str,
    chat_id: int | None,
    message_id: int | None,
    telegram_message_id: int | None,
    triggered_by_user_id: int,
    provider_id: int | None,
    provider_name: str | None,
    model_id: int | None,
    model_name: str | None,
    estimated_cost_minor: int,
    split_member_count: int,
    metadata: dict | None = None,
) -> int:
    await _ensure_group_tables(db)
    existing = (
        await db.execute(select(GroupUsageEvent.id).where(GroupUsageEvent.request_id == request_id))
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    payload = metadata or {}
    payload.update(
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "provider_id": provider_id,
            "provider_name": provider_name,
            "model_id": model_id,
            "model_name": model_name,
        }
    )
    row = GroupUsageEvent(
        group_id=int(group_id),
        usage_event_id=usage_event_id,
        request_id=request_id,
        telegram_chat_id=chat_id,
        telegram_message_id=telegram_message_id,
        triggered_by_user_id=int(triggered_by_user_id),
        operation_type="chat_completion",
        estimated_cost_minor=int(estimated_cost_minor or 0),
        actual_cost_minor=0,
        split_member_count=int(split_member_count or 0),
        status="authorized",
        error=None,
        metadata_json=payload,
        completed_at=None,
    )
    db.add(row)
    await db.flush()
    return int(row.id)


async def _upsert_group_usage_share_estimate(
    db: AsyncSession,
    *,
    group_usage_event_id: int,
    user_id: int,
    estimated_share_minor: int,
):
    await _ensure_group_tables(db)
    existing = (
        await db.execute(
            select(GroupUsageShare).where(
                GroupUsageShare.group_usage_event_id == int(group_usage_event_id),
                GroupUsageShare.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.estimated_share_minor = int(estimated_share_minor or 0)
        existing.status = "authorized"
        existing.error = None
        return
    event = await db.get(GroupUsageEvent, int(group_usage_event_id))
    if event is None:
        return
    db.add(
        GroupUsageShare(
            group_usage_event_id=int(group_usage_event_id),
            group_id=int(event.group_id),
            user_id=int(user_id),
            estimated_share_minor=int(estimated_share_minor or 0),
            actual_share_minor=0,
            ledger_entry_id=None,
            status="authorized",
            error=None,
            metadata_json={},
        )
    )


async def _update_group_usage_share_result(
    db: AsyncSession,
    *,
    group_usage_event_id: int,
    user_id: int,
    actual_share_minor: int,
    status: str,
    ledger_entry_id: int | None = None,
    error: str | None = None,
):
    await _ensure_group_tables(db)
    share = (
        await db.execute(
            select(GroupUsageShare).where(
                GroupUsageShare.group_usage_event_id == int(group_usage_event_id),
                GroupUsageShare.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if not share:
        return
    share.actual_share_minor = int(actual_share_minor or 0)
    share.status = status
    share.ledger_entry_id = ledger_entry_id
    share.error = error
    if status in {"posted", "charged", "completed", "failed"}:
        share.completed_at = _utcnow()


async def _complete_group_usage_event_row(
    db: AsyncSession,
    *,
    group_usage_event_id: int,
    actual_cost_minor: int,
    status: str,
    error: str | None = None,
):
    await _ensure_group_tables(db)
    event = await db.get(GroupUsageEvent, int(group_usage_event_id))
    if not event:
        return
    event.actual_cost_minor = int(actual_cost_minor or 0)
    event.status = status
    event.error = error
    event.completed_at = _utcnow()


def _embedding_price_per_million(emb_config: EmbeddingConfig | None) -> float:
    if not emb_config:
        return 0.0
    for field_name in ("pricing_input", "price_per_million", "price_per_1m", "pricing_per_1m"):
        raw_value = getattr(emb_config, field_name, None)
        if raw_value is None:
            continue
        try:
            return max(0.0, float(raw_value))
        except (TypeError, ValueError):
            continue
    return 0.0


def _embedding_cost_usd(emb_config: EmbeddingConfig | None, estimated_tokens: int) -> float:
    unit_price = _embedding_price_per_million(emb_config)
    if unit_price <= 0.0 or estimated_tokens <= 0:
        return 0.0
    return (estimated_tokens / 1_000_000.0) * unit_price


def _estimate_audio_tokens(duration_seconds: int | None) -> int:
    duration = max(1, int(duration_seconds or 0))
    return duration * GEMINI_AUDIO_TOKENS_PER_SECOND


def _estimate_audio_duration_from_size(file_size_bytes: int | None) -> int:
    """Rough duration estimate (seconds) for uploaded audio docs without duration metadata."""
    size_bytes = max(0, int(file_size_bytes or 0))
    if size_bytes <= 0:
        return 30
    # ~32 kbps compressed audio -> ~4 KB/s
    return max(1, min(60 * 60, int(round(size_bytes / 4000))))


def _transcription_cost_usd(config: TranscriptionConfig | None, input_tokens: int, output_tokens: int) -> float:
    if not config:
        return 0.0
    try:
        price_in = max(0.0, float(config.pricing_input or 0.0))
    except (TypeError, ValueError):
        price_in = 0.0
    try:
        price_out = max(0.0, float(config.pricing_output or 0.0))
    except (TypeError, ValueError):
        price_out = 0.0
    return ((max(0, input_tokens) / 1_000_000.0) * price_in) + ((max(0, output_tokens) / 1_000_000.0) * price_out)


async def _embedding_cost_toman(db: AsyncSession, emb_config: EmbeddingConfig | None, estimated_tokens: int) -> int:
    from app.services.toman_billing_service import DEFAULT_API_MARKUP_PERCENT, DEFAULT_USD_TO_TOMAN_RATE, get_or_create_subscription_config
    usd_cost = _embedding_cost_usd(emb_config, estimated_tokens)
    if usd_cost <= 0:
        return 0
    try:
        config = await get_or_create_subscription_config(db)
        rate = int(config.usd_to_toman_rate) if config else DEFAULT_USD_TO_TOMAN_RATE
        markup = float(config.api_markup_percent) if config else DEFAULT_API_MARKUP_PERCENT
    except Exception:
        rate = DEFAULT_USD_TO_TOMAN_RATE
        markup = DEFAULT_API_MARKUP_PERCENT
    base_toman = int(round(usd_cost * rate))
    return int(round(base_toman * (1 + markup / 100.0)))


async def _transcription_cost_toman(db: AsyncSession, config: TranscriptionConfig | None, input_tokens: int, output_tokens: int) -> int:
    from app.services.toman_billing_service import DEFAULT_API_MARKUP_PERCENT, DEFAULT_USD_TO_TOMAN_RATE, get_or_create_subscription_config
    usd_cost = _transcription_cost_usd(config, input_tokens, output_tokens)
    if usd_cost <= 0:
        return 0
    try:
        sub_config = await get_or_create_subscription_config(db)
        rate = int(sub_config.usd_to_toman_rate) if sub_config else DEFAULT_USD_TO_TOMAN_RATE
        markup = float(sub_config.api_markup_percent) if sub_config else DEFAULT_API_MARKUP_PERCENT
    except Exception:
        rate = DEFAULT_USD_TO_TOMAN_RATE
        markup = DEFAULT_API_MARKUP_PERCENT
    base_toman = int(round(usd_cost * rate))
    return int(round(base_toman * (1 + markup / 100.0)))


def _voice_ack_text(transcript: str) -> str:
    return "🎙 شنیدم! دارم روش کار می‌کنم... ⏳"


def _credit_balance(user: UserPreference) -> float:
    return max(0.0, float(user.credit_balance_usd or 0.0))


def _insufficient_credit_text(*, needed: float, balance: float, action_label: str) -> str:
    return (
        f"❌ اعتبار کافی نیست برای {action_label}.\n"
        f"اعتبار فعلی: ${balance:.4f}\n"
        f"حداقل اعتبار لازم: ${needed:.4f}"
    )


def _insufficient_credit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("➕ شارژ اعتبار", callback_data="toman_topup_start")]]
    )


def _insufficient_toman_credit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("➕ شارژ اعتبار", callback_data="toman_topup_start")]]
    )


async def _get_pending_action_markup(db: AsyncSession, user: UserPreference) -> InlineKeyboardMarkup | None:
    if not user.pending_action_payload:
        return None
    try:
        ts_str = user.pending_action_payload.get("timestamp")
        if not ts_str:
            return None
        ts = datetime.fromisoformat(ts_str)
        if (_utcnow() - ts).total_seconds() > 86400:
            user.pending_action_payload = None
            await db.commit()
            return None
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("▶️ ادامه کار قبلی", callback_data="resume_pending_action")]]
        )
    except Exception:
        return None


def _has_credit_for_cost(user: UserPreference, estimated_cost: float) -> bool:
    if estimated_cost <= 0.0:
        return True
    return _credit_balance(user) + 1e-9 >= estimated_cost


async def _charge_credit(
    db: AsyncSession,
    *,
    user: UserPreference,
    amount_usd: float,
    entry_type: str,
    reason: str,
    metadata: dict | None = None,
    usage_event_id: int | None = None,
    idempotency_key: str | None = None,
) -> tuple[bool, float]:
    charge = max(0.0, float(amount_usd or 0.0))
    charge_minor = _usd_to_minor(charge)
    current_balance = _credit_balance(user)
    if charge <= 0.0:
        return True, current_balance
    if idempotency_key:
        existing = (
            await db.execute(select(CreditLedgerEntry).where(CreditLedgerEntry.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if existing:
            return True, _credit_balance(user)

    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == user.id))).scalars().first()
    if not wallet:
        opening_minor = _signed_usd_to_minor(float(user.credit_balance_usd or 0.0))
        wallet = Wallet(
            user_id=user.id,
            currency="USD",
            balance_minor=opening_minor,
            available_minor=opening_minor,
            held_minor=0,
        )
        db.add(wallet)
        await db.flush()

    if not wallet.allow_negative and wallet.available_minor < charge_minor:
        return False, _minor_to_usd(wallet.available_minor)

    wallet.balance_minor -= charge_minor
    wallet.available_minor -= charge_minor
    wallet.version = int(wallet.version or 0) + 1
    user.credit_balance_usd = _minor_to_usd(wallet.available_minor)
    db.add(
        CreditLedgerEntry(
            user_id=user.id,
            wallet_id=wallet.id,
            amount_delta_usd=-charge,
            amount_minor=charge_minor,
            balance_after_minor=wallet.balance_minor,
            available_after_minor=wallet.available_minor,
            held_after_minor=wallet.held_minor,
            currency=wallet.currency,
            direction="debit",
            entry_type=entry_type,
            status="posted",
            reason=reason,
            usage_event_id=usage_event_id,
            idempotency_key=idempotency_key,
            metadata_json=metadata or {},
        )
    )
    await db.commit()
    await db.refresh(user)
    return True, _credit_balance(user)


async def _create_usage_event(
    db: AsyncSession,
    *,
    user: UserPreference,
    chat_id: int | None,
    message_id: int | None,
    operation_type: str,
    uploaded_file_id: int | None = None,
    provider_name: str | None = None,
    provider_id: int | None = None,
    model: DBModel | None = None,
    estimated_cost_usd: float = 0.0,
    request_id: str | None = None,
    metadata: dict | None = None,
) -> UsageEvent:
    existing = None
    if request_id:
        existing = (await db.execute(select(UsageEvent).where(UsageEvent.request_id == request_id))).scalar_one_or_none()
    if existing:
        return existing
    pricing_snapshot = None
    if model:
        pricing_snapshot = {
            "source": "models",
            "pricing_input_usd_per_1m": float(model.pricing_input or 0.0),
            "pricing_output_usd_per_1m": float(model.pricing_output or 0.0),
        }
    usage = UsageEvent(
        user_id=user.id,
        chat_id=chat_id,
        message_id=message_id,
        uploaded_file_id=uploaded_file_id,
        operation_type=operation_type,
        channel="telegram",
        provider_id=provider_id,
        provider_name_snapshot=provider_name,
        model_id=model.id if model else None,
        model_name_snapshot=(model.display_name or model.name) if model else None,
        pricing_snapshot_json=pricing_snapshot,
        request_id=request_id,
        estimated_cost_minor=_usd_to_minor(estimated_cost_usd),
        status="estimated",
        metadata_json=metadata or {},
    )
    db.add(usage)
    await db.flush()
    return usage


async def _complete_usage_event(
    db: AsyncSession,
    usage: UsageEvent,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    actual_cost_usd: float = 0.0,
    usage_source: str = "provider_reported",
):
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.total_tokens = input_tokens + output_tokens
    usage.actual_cost_minor = _usd_to_minor(actual_cost_usd)
    usage.usage_source = usage_source
    usage.status = "completed"
    usage.completed_at = _utcnow()


async def _record_uploaded_file(
    db: AsyncSession,
    *,
    user: UserPreference,
    chat_id: int | None = None,
    project_id: int | None = None,
    telegram_file_id: str | None = None,
    telegram_file_unique_id: str | None = None,
    filename: str | None = None,
    mime_type: str | None = None,
    file_type: str | None = None,
    size_bytes: int = 0,
    storage_path: str | None = None,
    caption: str | None = None,
    status: str = "stored",
    metadata: dict | None = None,
) -> UploadedFile:
    record = UploadedFile(
        user_id=user.id,
        chat_id=chat_id,
        project_id=project_id,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        filename=filename,
        mime_type=mime_type,
        file_type=file_type,
        size_bytes=size_bytes or 0,
        storage_path=storage_path,
        caption=caption,
        status=status,
        metadata_json=metadata or {},
    )
    db.add(record)
    await db.flush()
    return record


def _telegram_update_type(update: Update) -> str:
    if update.callback_query:
        return "callback_query"
    if update.message and update.message.contact:
        return "contact"
    if update.message and update.message.document:
        return "document"
    if update.message and update.message.photo:
        return "photo"
    if update.message and update.message.voice:
        return "voice"
    if update.message and update.message.text:
        return "text"
    return "unknown"


async def _claim_update_once(update: Update, allow_reclaim: bool = False) -> bool:
    if update.update_id is None:
        return True
    async with async_session() as db:
        # Check if already exists
        existing = (
            await db.execute(select(TelegramUpdateLog).where(TelegramUpdateLog.update_id == update.update_id))
        ).scalar_one_or_none()
        
        if existing:
            if existing.status == "completed":
                return False
            
            if allow_reclaim:
                # If explicitly allowed (internal re-entry), just return True
                return True
            
            # If processing, only allow if it's old (stuck)
            from datetime import datetime, timezone, timedelta
            now = _utcnow()
            created_at = existing.created_at
            
            # Reduce timeout to 30 seconds for faster recovery
            if existing.status == "processing" and (now - created_at) > timedelta(minutes=15):
                logger.info(f"Update {update.update_id} was stuck in 'processing' for >15min. Re-claiming.")
                existing.status = "processing" 
                existing.created_at = now
                await db.commit()
                return True
            
            # logger.debug(f"Update {update.update_id} already in state '{existing.status}', ignoring.")
            return False

        log = TelegramUpdateLog(
            update_id=update.update_id,
            update_key=f"telegram:update:{update.update_id}",
            telegram_user_id=update.effective_user.id if update.effective_user else None,
            chat_id=update.effective_chat.id if update.effective_chat else None,
            update_type=_telegram_update_type(update),
            status="processing",
            metadata_json={},
        )
        db.add(log)
        try:
            await db.commit()
            return True
        except IntegrityError:
            await db.rollback()
            return False


async def _mark_update_completed(update: Update):
    if update.update_id is None:
        return
    await _mark_update_completed_by_id(update.update_id)


async def _mark_update_completed_by_id(update_id: int | None):
    if update_id is None:
        return
    async with async_session() as db:
        log = (
            await db.execute(select(TelegramUpdateLog).where(TelegramUpdateLog.update_id == update_id))
        ).scalar_one_or_none()
        if log:
            log.status = "completed"
            log.completed_at = _utcnow()
            await db.commit()


def _is_smalltalk(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return True
    if len(normalized) <= 18 and SMALLTALK_TEXT_RE.match(normalized):
        return True
    if len(normalized.split()) <= 3 and SMALLTALK_TEXT_RE.match(normalized):
        return True
    return False


def _should_request_rating(user_text: str, assistant_text: str) -> bool:
    if not assistant_text or len(assistant_text.strip()) < MIN_RATING_REPLY_CHARS:
        return False
    if _is_smalltalk(user_text):
        return False
    if _is_smalltalk(assistant_text):
        return False
    return random.random() < RATING_REQUEST_PROBABILITY


async def _maybe_request_rating(
    update: Update,
    db: AsyncSession,
    *,
    user_id: int,
    user_text: str,
    assistant_text: str,
    assistant_message_id: int,
):
    if not _should_request_rating(user_text, assistant_text):
        return
    recent_cutoff = _utcnow() - timedelta(hours=24)
    recent_feedback = (
        await db.execute(
            select(FeedbackEntry.id).where(
                or_(FeedbackEntry.user_id == user_id, FeedbackEntry.telegram_user_id == user_id),
                FeedbackEntry.created_at >= recent_cutoff,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if recent_feedback is not None:
        return
    rating_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("👍", callback_data=f"rate_{assistant_message_id}_up"),
        InlineKeyboardButton("👎", callback_data=f"rate_{assistant_message_id}_down"),
    ]])
    await update.message.reply_text("این پاسخ مفید بود؟", reply_markup=rating_kb)


async def _save_assistant_message_and_post_actions(
    update: Update,
    db: AsyncSession,
    *,
    uid: int,
    chat: Chat,
    model: DBModel,
    llm_messages: list[dict],
    assistant_text: str,
    user_text: str,
):
    if not assistant_text:
        return
    assistant_msg = Message(chat_id=chat.id, role="assistant", content=assistant_text)
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    if "چت جدید" in chat.title:
        try:
            title = await generate_title(db, model.id, llm_messages)
            chat.title = title
            await db.commit()
        except Exception:
            pass

    if uid != ADMIN_ID:
        await _maybe_request_rating(
            update,
            db,
            user_id=uid,
            user_text=user_text,
            assistant_text=assistant_text,
            assistant_message_id=assistant_msg.id,
        )

    # ── OpenWebUI Sync ──
    try:
        from app.openwebui_client import OpenWebUIClient
        owui = OpenWebUIClient()
        user_name = update.effective_user.first_name or str(uid)
        asyncio.create_task(
            owui.sync_user_message_and_response(
                telegram_user_id=uid,
                user_name=user_name,
                user_message=user_text,
                bot_response=assistant_text,
                model=model.name if model else "boz-gpt",
                chat_title=chat.title or "گفتگوی تلگرام",
            )
        )
    except Exception:
        pass  # Sync failure should not break the bot


async def _ensure_onboarding_or_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user: UserPreference,
) -> bool:
    status = (user.account_status or "").strip().lower()
    if status in BLOCKED_ACCOUNT_STATUSES:
        message_obj = update.message or (update.callback_query.message if update.callback_query else None)
        if message_obj:
            await message_obj.reply_text("حسابت فعلاً فعال نیست. برای بررسی با پشتیبانی تماس بگیر.")
        return False
    if _user_onboarding_completed(user):
        return True
    need_phone = _missing_phone(user)
    need_name = _missing_preferred_name(user)
    if need_name and not need_phone:
        _begin_mode(context, "asking_name")
    else:
        _reset_ephemeral_state(context, clear_pending=False)
        context.user_data.pop("asking_name", None)
    message_obj = update.message or (update.callback_query.message if update.callback_query else None)
    if message_obj:
        first_name = user.first_name or (update.effective_user.first_name if update.effective_user else "")
        await _prompt_onboarding(
            message_obj,
            first_name=first_name,
            need_phone=need_phone,
            need_name=need_name,
        )
    return False


def _account_entry_type_label(entry_type: str | None) -> str:
    mapping = {
        "chat_completion": "پاسخ چت",
        "voice_transcription": "تبدیل صوت",
        "rag_embedding": "ایندکس فایل",
        "admin_adjustment": "تنظیم ادمین",
        "opening_balance": "موجودی اولیه",
        "wallet_topup": "شارژ کیف پول",
        "promo_code_credit": "بونس کوپن",
        "subscription_gift_credit": "اعتبار هدیه اشتراک",
        "subscription_wallet_payment": "پرداخت اشتراک از کیف پول",
        "first_topup_discount_used": "تخفیف اولین شارژ",
        "chat_completion_usage": "پاسخ چت",
        "paid_topup_credit": "شارژ اعتبار",
        "subscription_payment": "خرید اشتراک",
    }
    key = (entry_type or "").strip().lower()
    return mapping.get(key, key or "تراکنش")


def _account_nav_kb(active: str = "home") -> InlineKeyboardMarkup:
    profile_label = "✅ پروفایل" if active == "profile" else "🧾 پروفایل"
    credit_label = "✅ کیف پول" if active == "credit" else "💳 کیف پول"
    tx_label = "✅ تراکنش‌ها" if active == "transactions" else "📜 تراکنش‌ها"
    home_label = "✅ خلاصه حساب" if active == "home" else "👤 خلاصه حساب"
    usage_label = "✅ گزارش مصرف" if active == "usage" else "📊 گزارش مصرف"
    referral_label = "✅ دعوت دوستان" if active == "referral" else "🎁 دعوت دوستان"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(home_label, callback_data="account_home"),
                InlineKeyboardButton(profile_label, callback_data="account_profile"),
            ],
            [
                InlineKeyboardButton(credit_label, callback_data="account_credit"),
                InlineKeyboardButton(usage_label, callback_data="account_usage"),
            ],
            [
                InlineKeyboardButton(tx_label, callback_data="account_transactions"),
                InlineKeyboardButton(referral_label, callback_data="account_referral"),
            ],
            [
                InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"account_refresh_{active}"),
            ],
        ]
    )


def _account_kb(section: str, ctx: dict | None = None) -> InlineKeyboardMarkup:
    nav_rows = _account_nav_kb(section).inline_keyboard
    rows = [list(row) for row in nav_rows]

    if section in {"home", "profile"}:
        phone_label = "📱 ثبت شماره" if (ctx or {}).get("phone") == "ثبت نشده" else "📱 تغییر شماره"
        rows.append(
            [
                InlineKeyboardButton("✏️ تغییر اسم", callback_data="account_set_name"),
                InlineKeyboardButton(phone_label, callback_data="share_contact_request"),
            ]
        )
    elif section == "credit":
        rows.append([InlineKeyboardButton("➕ شارژ اعتبار", callback_data="toman_topup_start")])
        rows.append([InlineKeyboardButton("🎁 کد تخفیف", callback_data="account_promo_start")])
    elif section == "referral":
        rows.append([InlineKeyboardButton("📋 کپی لینک دعوت", callback_data="account_referral_copy")])

    return InlineKeyboardMarkup(rows)


async def _load_account_context(db: AsyncSession, user: UserPreference, tx_limit: int = 8) -> dict:
    phone = (user.phone_number or "").strip() or "ثبت نشده"
    preferred_name = (user.preferred_name or "").strip() or "ثبت نشده"
    status = (user.account_status or "active").strip()
    from app.services.toman_billing_service import get_or_create_billing_account
    account = await get_or_create_billing_account(db, user)
    balance = int(account.gift_balance_toman or 0) + int(account.paid_balance_toman or 0)
    ledger_rows = (
        await db.execute(
            select(TomanLedgerEntry)
            .where(TomanLedgerEntry.user_id == user.id)
            .order_by(TomanLedgerEntry.created_at.desc(), TomanLedgerEntry.id.desc())
            .limit(tx_limit)
        )
    ).scalars().all()

    from app.models import UserSubscription
    sub = (await db.execute(
        select(UserSubscription)
        .options(selectinload(UserSubscription.plan))
        .where(UserSubscription.user_id == user.id, UserSubscription.status == "active", UserSubscription.expires_at > _utcnow())
        .order_by(UserSubscription.expires_at.desc())
    )).scalars().first()

    return {
        "phone": phone,
        "preferred_name": preferred_name,
        "status": status,
        "balance": balance,
        "ledger_rows": ledger_rows,
        "active_subscription": sub,
    }



def _learning_status_label_fa(payload: dict | None) -> str:
    data = payload if isinstance(payload, dict) else {}
    if data.get("completed"):
        return "تکمیل شده"
    if data.get("in_progress"):
        return "در حال انجام"
    if data.get("skipped"):
        return "رد شده"
    return "شروع نشده"


def _account_home_text(ctx: dict) -> str:
    ledger_rows = ctx["ledger_rows"]
    spent = 0
    added = 0
    for entry in ledger_rows:
        delta = int(entry.amount_toman or 0)
        if delta >= 0:
            added += delta
        else:
            spent += abs(delta)

    lines = [
        "👤 خلاصه حساب",
        "",
        f"نام: {ctx['preferred_name']}",
        f"شماره: {ctx['phone']}",
        f"وضعیت: {ctx['status']}",
        "",
        f"💳 اعتبار فعلی: {_format_toman(ctx['balance'])}",
        f"📈 مجموع واریزی اخیر: {_format_toman(added)}",
        f"📉 مجموع هزینه اخیر: {_format_toman(spent)}",
        f"🧠 ترجیحات یادگیری: {_learning_status_label_fa(ctx.get('learning_payload'))}",
    ]

    sub = ctx.get("active_subscription")
    if sub:
        lines.append(f"💎 اشتراک فعال: {sub.plan.name if sub.plan else 'نامعلوم'}")
        lines.append(f"📅 انقضا: {format_persian(sub.expires_at, '%Y-%m-%d %H:%M')}")
    else:
        lines.append("💎 اشتراک: غیرفعال")

    return "\n".join(lines)


async def _account_usage_text(db, user: UserPreference, ctx: dict) -> str:
    from app.models import UserSubscription
    from sqlalchemy.orm import selectinload
    from datetime import datetime, timezone
    from sqlalchemy import select

    now = _utcnow()
    sub_query = select(UserSubscription).options(selectinload(UserSubscription.plan)).where(
        UserSubscription.user_id == user.id,
        UserSubscription.status == "active",
        UserSubscription.expires_at > now
    ).order_by(UserSubscription.expires_at.desc())
    user_sub = (await db.execute(sub_query)).scalars().first()
    
    lines = ["📊 گزارش مصرف حساب", ""]
    
    if not user_sub:
         lines.append("شما در حال حاضر اشتراک فعالی ندارید.")
         return "\n".join(lines)
         
    plan = user_sub.plan
    lines.append(f"📦 بسته فعال: {plan.name}")
    
    if plan.plan_type == "tiered_cooldown":
        # Reset if expired
        if user_sub.cooldown_ends_at and now >= user_sub.cooldown_ends_at:
            user_sub.cooldown_spent_toman = 0
            user_sub.cooldown_ends_at = None
            await db.commit()
            await db.refresh(user_sub)

        spent = user_sub.cooldown_spent_toman or 0
        limit = plan.cooldown_limit_toman or 1
        pct = min(100, int(spent * 100 / limit))
        bar_len = 10
        filled = int(pct / 10)
        bar = "■" * filled + "□" * (bar_len - filled)
        
        lines.append(f"🔹 لیمیت دوره‌ای ({pct}%):")
        lines.append(f"`{bar}` {spent:,} / {limit:,} تومان")
        
        if user_sub.cooldown_ends_at and now < user_sub.cooldown_ends_at:
            if spent >= limit:
                diff = user_sub.cooldown_ends_at - now
                hours, remainder = divmod(diff.seconds, 3600)
                minutes = remainder // 60
                lines.append(f"⏳ حساب در وضعیت قفل!\nبازگشت به مصرف اشتراکی تا {hours} ساعت و {minutes} دقیقه دیگر.")
            else:
                diff = user_sub.cooldown_ends_at - now
                hours, remainder = divmod(diff.seconds, 3600)
                minutes = remainder // 60
                lines.append(f"✅ در حال استفاده از حجم اشتراک.\n(ریست بعدی: {hours} ساعت و {minutes} دقیقه دیگر)")
        else:
            lines.append("✅ در حال استفاده از حجم اشتراک.")
            
        w_spent = user_sub.weekly_spent_toman or 0
        w_limit = plan.weekly_limit_toman or 1
        w_pct = min(100, int(w_spent * 100 / w_limit))
        w_filled = int(w_pct / 10)
        w_bar = "■" * w_filled + "□" * (bar_len - w_filled)
        
        lines.append("")
        lines.append(f"🔹 مصرف هفتگی ({w_pct}%):")
        lines.append(f"`{w_bar}` {w_spent:,} / {w_limit:,} تومان")
    else:
        lines.append("این اشتراک ماهیانه عادی است.")
        
    return "\n".join(lines)


def _account_profile_text(user: UserPreference, ctx: dict) -> str:
    lines = [
        "🧾 پروفایل کاربر",
        "",
        f"نام نمایشی: {ctx['preferred_name']}",
        f"نام تلگرام: {(user.first_name or '').strip() or 'ثبت نشده'}",
        f"یوزرنیم: @{(user.username or '').strip()}" if (user.username or "").strip() else "یوزرنیم: ثبت نشده",
        f"شماره تماس: {ctx['phone']}",
        f"وضعیت حساب: {ctx['status']}",
        f"ترجیحات یادگیری: {_learning_status_label_fa(ctx.get('learning_payload'))}",
    ]
    return "\n".join(lines)


def _account_credit_text(ctx: dict) -> str:
    lines = [
        "💳 کیف پول",
        "",
        f"اعتبار قابل استفاده: {_format_toman(ctx['balance'])}",
        "",
        "برای مشاهده جزئیات برداشت/واریز، تب تراکنش‌ها را باز کن.",
        "🎁 کد تخفیف داری؟ از دکمه «کد تخفیف» استفاده کن.",
    ]
    return "\n".join(lines)


async def _account_referral_text(db: AsyncSession, user: UserPreference, context: ContextTypes.DEFAULT_TYPE) -> str:
    from app.models import ReferralCampaign, ReferralEvent, ReferralConfig

    campaign = None
    if user.referral_campaign_id:
        campaign = (await db.execute(select(ReferralCampaign).where(ReferralCampaign.id == user.referral_campaign_id))).scalar_one_or_none()

    if not campaign:
        bot_username = context.bot.username or "jgpti_bot"
        code = f"ref_u{user.id}_{user.telegram_user_id}"
        campaign = ReferralCampaign(
            code=code,
            description=f"Referral link for user {user.id}",
            created_by_user_id=user.id,
            is_active=True,
        )
        db.add(campaign)
        await db.flush()
        user.referral_campaign_id = campaign.id
        await db.commit()

    config = (await db.execute(select(ReferralConfig).where(ReferralConfig.name == "default"))).scalar_one_or_none()
    reward = int(config.reward_toman if config else 50000)

    bot_username = context.bot.username or "jgpti_bot"
    referral_link = f"https://t.me/{bot_username}?start={campaign.code}"

    events = (await db.execute(select(ReferralEvent).where(ReferralEvent.campaign_id == campaign.id))).scalars().all()
    total_invites = len(events)
    rewarded_count = sum(1 for e in events if e.event_type == "signup")

    lines = [
        "🎁 دعوت دوستان",
        "",
        "با دعوت دوستانتان، اعتبار رایگان دریافت کنید!",
        f"به ازای هر دعوت موفق: {_format_toman(reward)}",
        "",
        "🔗 لینک دعوت شما:",
        f"{referral_link}",
        "",
        f"📊 تعداد دعوت‌ها: {total_invites}",
        f"✅ دعوت‌های موفق: {rewarded_count}",
        "",
        "این لینک را برای دوستانتان بفرستید. وقتی از طریق لینک شما وارد شوند،",
        "هم شما و هم دوستتان اعتبار رایگان دریافت می‌کنید.",
    ]
    return "\n".join(lines)


def _account_transactions_text(ctx: dict) -> str:
    ledger_rows = ctx["ledger_rows"]
    lines = [
        "📜 آخرین تراکنش‌ها",
        "",
    ]
    if not ledger_rows:
        lines.append("تراکنشی ثبت نشده.")
        return "\n".join(lines)

    for entry in ledger_rows:
        delta = int(entry.amount_toman or 0)
        sign = "+" if delta >= 0 else ""
        reason = (entry.reason or "").strip()
        reason_label = reason if reason else _account_entry_type_label(entry.entry_type)
        created = format_persian(entry.created_at, "%m/%d %H:%M") if entry.created_at else "-"
        lines.append(f"{created} | {sign}{delta:,} تومان | {reason_label}")
    return "\n".join(lines)


def _account_learning_text(ctx: dict) -> str:
    payload = ctx.get("learning_payload") if isinstance(ctx.get("learning_payload"), dict) else {}
    status_label = _learning_status_label_fa(payload)
    answers_count = int(payload.get("questions_answered") or 0)
    target_count = int(payload.get("target_questions") or 4)
    lines = [
        "🧠 تنظیم سبک یادگیری",
        "",
        f"وضعیت: {status_label}",
        f"پیشرفت: {answers_count}/{target_count} پاسخ",
    ]

    if payload.get("completed"):
        summary = (payload.get("summary") or "").strip()
        if summary:
            lines.extend(["", "خلاصه پروفایل:", summary])
        else:
            lines.extend(["", "پروفایل یادگیری ثبت شده."])
        lines.extend(
            [
                "",
                "این خلاصه به‌صورت خودکار به کانتکست هر درخواست آینده اضافه می‌شود.",
                "این خروجی از تحلیل کل گفت‌وگوی onboarding توسط AI ساخته می‌شود.",
                "برای بازطراحی پروفایل، «بازطراحی ترجیحات» را بزن.",
            ]
        )
        return "\n".join(lines)

    if payload.get("in_progress"):
        next_q = (payload.get("next_question") or "").strip()
        lines.extend(["", "فرآیند فعال است. مثل چت عادی، پاسخ بعدی را با متن بفرست."])
        if next_q:
            lines.extend(["", f"سوال فعلی:\n{next_q}"])
        lines.extend(["", f"بعد از {target_count} پاسخ، سشن به‌صورت خودکار نهایی می‌شود."])
        lines.extend(["", f"برای توقف، «رد فعلاً» یا دکمه «{CANCEL_TEXT}» را بزن."])
        return "\n".join(lines)

    if payload.get("skipped"):
        lines.extend(["", "این مرحله قبلاً رد شده. هر زمان خواستی می‌تونی دوباره شروع کنی."])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "در این بخش یک گفت‌وگوی کوتاه و طبیعی انجام می‌شود تا سبک یادگیریت مشخص شود.",
            "پس از پایان، یک AI تحلیل‌گر همین گفت‌وگو را بررسی می‌کند و تنظیمات شخصی‌سازی می‌سازد.",
            "خروجی تحلیل در ابتدای درخواست‌های بعدی به مدل اضافه می‌شود.",
            "برای شروع، «شروع تنظیمات» را بزن.",
        ]
    )
    return "\n".join(lines)


async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "برای ارتباط با پشتیبانی، لطفاً به آیدی زیر پیام دهید:\n\n@drbozsupport"
    )


async def cmd_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _claim_update_once(update):
        return
    try:
        uid = update.effective_user.id
        async with async_session() as db:
            user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            if not await _ensure_onboarding_or_prompt(update, context, user=user):
                return
            ctx = await _load_account_context(db, user, tx_limit=8)
        await update.message.reply_text(_account_home_text(ctx), reply_markup=_account_kb("home", ctx))
    finally:
        await _mark_update_completed(update)


# Global cache for subscription feature toggle
_SUB_FEATURE_ENABLED_CACHE = True

async def _is_sub_feature_enabled(db: AsyncSession) -> bool:
    global _SUB_FEATURE_ENABLED_CACHE
    from app.models import SubscriptionConfig
    try:
        res = await db.execute(select(SubscriptionConfig))
        cfg = res.scalars().first()
        enabled = cfg.is_enabled if cfg else True
        _SUB_FEATURE_ENABLED_CACHE = enabled
        return enabled
    except Exception as e:
        logger.warning(f"Failed to check subscription toggle: {e}")
        return _SUB_FEATURE_ENABLED_CACHE

async def _get_active_subscription_plans(db: AsyncSession):
    from app.models import SubscriptionPlan
    res = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_active == True))
    return res.scalars().all()

async def cmd_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    async with async_session() as db:
        if not await _is_sub_feature_enabled(db):
            msg = "این ویژگی در حال حاضر غیرفعال است."
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            else:
                await update.message.reply_text(msg)
            return
        from app.models import UserSubscription

        user = await get_user(db, update.effective_user.id, update.effective_user.first_name or "", update.effective_user.username or "")
        active_sub = (
            await db.execute(
                select(UserSubscription)
                .options(selectinload(UserSubscription.plan))
                .where(
                    UserSubscription.user_id == user.id,
                    UserSubscription.status == "active",
                    UserSubscription.expires_at > _utcnow(),
                )
                .order_by(UserSubscription.expires_at.desc())
            )
        ).scalars().first()
        if active_sub:
            plan_name = active_sub.plan.name if active_sub.plan else "نامعلوم"
            msg = (
                "💎 اشتراک فعال دارید.\n"
                f"پلن: {plan_name}\n"
                f"انقضا: {format_persian(active_sub.expires_at, '%Y-%m-%d %H:%M')}"
            )
            if update.callback_query:
                await update.callback_query.message.reply_text(msg)
                await update.callback_query.answer()
            else:
                await update.message.reply_text(msg)
            return
            
        plans = await _get_active_subscription_plans(db)

        if not plans:
            msg = "در حال حاضر هیچ اشتراکی فعال نیست."
            if update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            else:
                await update.message.reply_text(msg)
            return
            
        text = "💎 اشتراک‌های ویژه:\n\n"
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from app.services.toman_billing_service import get_or_create_subscription_config

        config = await get_or_create_subscription_config(db)
        keyboard = []
        for p in plans:
            _plan_price = getattr(p, "monthly_price_toman", None)
            price_toman = int(_plan_price) if _plan_price is not None else int(config.monthly_price_toman or 0)
            _plan_gift = getattr(p, "gift_credit_toman", None)
            gift_toman = int(_plan_gift) if _plan_gift is not None else int(config.gift_credit_toman or 0)
            text += f"▪️ {p.name} - {_format_toman(price_toman)} / ماه، اعتبار هدیه {_format_toman(gift_toman)}\n"
            keyboard.append([InlineKeyboardButton(f"خرید {p.name} ({_format_toman(price_toman)})", callback_data=f"buy_plan_{p.id}")])
            
        markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(text, reply_markup=markup)
            await update.callback_query.answer()
        else:
            await update.message.reply_text(text, reply_markup=markup)

async def cmd_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redirect USD topup to Toman topup."""
    await cmd_toman_topup(update, context)


async def cmd_toman_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return

    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass
        await update.callback_query.message.reply_text(
            "💵 مبلغ اعتباری که می‌خواهی به کیف پول اشتراک اضافه شود را به تومان وارد کن.\n"
            "مثال: 300000\n"
            "اگر اولین شارژ بعد از اشتراک باشد، تخفیف طبق تنظیمات ادمین روی مبلغ پرداختی اعمال می‌شود.",
            reply_markup=_cancel_reply_kb(),
        )
    else:
        await update.message.reply_text(
            "💵 مبلغ اعتباری که می‌خواهی به کیف پول اشتراک اضافه شود را به تومان وارد کن.\n"
            "مثال: 300000\n"
            "اگر اولین شارژ بعد از اشتراک باشد، تخفیف طبق تنظیمات ادمین روی مبلغ پرداختی اعمال می‌شود.",
            reply_markup=_cancel_reply_kb(),
        )
    _begin_mode(context, "awaiting_toman_topup_amount")


async def _handle_topup_method_bale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0

    if not _is_bale_platform():
        msg = (
            "⚠️ درگاه پرداخت بله فقط در پیام‌رسان بله فعال است.\n"
            "لطفاً از روش کارت به کارت استفاده کنید."
        )
        await update.callback_query.answer(msg, show_alert=True)
        return

    if not BALE_WALLET_PROVIDER_TOKEN:
        msg = "⚠️ توکن پرداخت بله تنظیم نشده است. لطفاً از روش کارت به کارت استفاده کنید."
        await update.callback_query.answer(msg, show_alert=True)
        return

    quote_data = context.user_data.get("pending_toman_topup_quote")
    if not quote_data:
        await update.callback_query.answer("❌ خطا: اطلاعات پیش‌فاکتور پیدا نشد. لطفاً دوباره شروع کنید.", show_alert=True)
        return

    phone_rule_text = (
        "📱 *نکته مهم درباره درگاه بله:*\n"
        "شماره تلفنی که با آن در بله ثبت‌نام کرده‌اید باید با شماره کارت بانکی که می‌خواهید با آن پرداخت کنید یکی باشد.\n"
        "این محدودیت از طرف *پیام‌رسان بله* است و دست ما نیست. متأسفانه قوانین آن‌ها اینطور است.\n"
        "اگر شماره کارتتان با شماره تلفن بله‌تان یکی نیست، لطفاً از روش *کارت به کارت* استفاده کنید."
    )

    await update.callback_query.message.reply_text(phone_rule_text, parse_mode="Markdown")

    try:
        invoice_info = await _send_bale_toman_topup_invoice(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            user_id=uid,
            credit_amount_toman=quote_data["credit_amount_toman"],
            payment_due_toman=quote_data["payment_due_toman"],
        )
    except Exception as exc:
        logger.exception("failed to send bale toman topup invoice")
        await update.callback_query.message.reply_text(
            "❌ ارسال فاکتور پرداخت انجام نشد.\n"
            f"خطا: {str(exc)}"
        )
        return

    _reset_ephemeral_state(context, clear_pending=True)
    discount_line = f"تخفیف اعمال‌شده: {_format_toman(quote_data['discount_toman'])}\n" if quote_data.get("discount_toman") else ""
    await update.callback_query.message.reply_text(
        "✅ فاکتور پرداخت ارسال شد.\n"
        f"اعتبار درخواستی: {_format_toman(invoice_info['credit_amount_toman'])}\n"
        f"{discount_line}"
        f"مبلغ نهایی پرداخت: {_format_toman(invoice_info['total_toman'])}\n"
        "بعد از پرداخت موفق، اعتبار تومانی حسابت خودکار اضافه می‌شود.",
        reply_markup=main_kb(uid == ADMIN_ID),
    )


async def _handle_topup_method_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else 0

    quote_data = context.user_data.get("pending_toman_topup_quote")
    if not quote_data:
        await update.callback_query.answer("❌ خطا: اطلاعات پیش‌فاکتور پیدا نشد. لطفاً دوباره شروع کنید.", show_alert=True)
        return

    try:
        await update.callback_query.message.delete()
    except Exception:
        pass

    async with async_session() as db:
        from app.models import PaymentMethod
        from sqlalchemy import select
        methods = (
            await db.execute(
                select(PaymentMethod).where(PaymentMethod.is_active == True).order_by(PaymentMethod.sort_order, PaymentMethod.id)
            )
        ).scalars().all()

    if not methods:
        await update.callback_query.message.reply_text(
            "⚠️ در حال حاضر شماره کارتی برای پرداخت ثبت نشده است.\n"
            "لطفاً بعداً مجدداً تلاش کنید یا به پشتیبانی پیام دهید."
        )
        return

    invoice_summary = (
        f"📋 *مبلغ قابل پرداخت: {_format_toman(quote_data['payment_due_toman'])}*\n"
        f"💰 اعتبار دریافتی: {_format_toman(quote_data['credit_amount_toman'])}\n"
    )
    if quote_data.get("discount_toman"):
        invoice_summary += f"🎁 تخفیف اعمال‌شده: {_format_toman(quote_data['discount_toman'])}\n"
    invoice_summary += "\n"

    cards_text = invoice_summary + "💳 *شماره کارت‌های مقصد:*\n\n"
    kb_rows = []
    for m in methods:
        cards_text += f"🏦 *{m.bank_name}*\n"
        cards_text += f"شماره کارت: `{m.card_number}`\n"
        cards_text += f"صاحب کارت: {m.cardholder_name}\n"
        if m.description:
            cards_text += f"📝 {m.description}\n"
        cards_text += "\n"
        kb_rows.append([InlineKeyboardButton(f"📋 کپی {m.card_number}", copy_text=CopyTextButton(text=m.card_number))])

    cards_text += (
        "⏱ *زمان تأیید:* معمولاً ۵ تا ۱۰ دقیقه بعد از ارسال رسید\n"
        "(به جز ساعات نیمه‌شب که ممکن است بیشتر طول بکشد)\n\n"
        "لطفاً دقیقاً همان مبلغ پیش‌فاکتور را واریز کنید و سپس *تصویر رسید* را ارسال کنید:"
    )

    reply_kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None

    _begin_mode(context, "awaiting_card_receipt")
    context.user_data["pending_card_amount_toman"] = quote_data["payment_due_toman"]

    await update.callback_query.message.reply_text(cards_text, parse_mode="Markdown", reply_markup=reply_kb)


async def _handle_card_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    photo = update.message.photo[-1] if update.message.photo else None
    if not photo:
        await update.message.reply_text("❌ لطفاً تصویر رسید را به صورت عکس ارسال کنید.")
        return

    amount_toman = context.user_data.get("pending_card_amount_toman")
    if not amount_toman:
        context.user_data.pop("awaiting_card_receipt", None)
        await update.message.reply_text("❌ خطا: مبلغ پرداخت مشخص نیست. لطفاً دوباره از ابتدا شروع کنید.")
        return

    description = update.message.caption or ""

    progress_msg = await update.message.reply_text("⏳ در حال دریافت تصویر رسید...")

    try:
        await _download_telegram_file(context, photo.file_id, f"./uploads/receipts/{photo.file_unique_id}.jpg")
    except Exception as e:
        logger.exception("failed to download receipt photo")
        await progress_msg.edit_text("❌ مشکلی در دریافت تصویر رسید پیش آمد. لطفاً دوباره تلاش کنید.")
        return

    receipt_path = f"uploads/receipts/{photo.file_unique_id}.jpg"

    async with async_session() as db:
        from app.models import PaymentRequest
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")

        request = PaymentRequest(
            user_id=user.id,
            amount_toman=int(amount_toman),
            receipt_image_path=receipt_path,
            description=description if description else None,
            status="pending",
            payment_type="topup",
        )
        db.add(request)
        await db.commit()

    _reset_ephemeral_state(context, clear_pending=True)

    try:
        from app.transactions_bot import send_new_payment_notification
        asyncio.create_task(send_new_payment_notification(request.id))
    except Exception:
        pass

    await progress_msg.edit_text(
        f"✅ درخواست پرداخت شما با موفقیت ثبت شد.\n\n"
        f"مبلغ: {_format_toman(int(amount_toman))} تومان\n"
        f"وضعیت: در انتظار بررسی\n\n"
        "⏱ تأیید معمولاً ۵ تا ۱۰ دقیقه طول می‌کشد (به جز نیمه‌شب).\n"
        "پس از تأیید، اعتبار به کیف پول شما اضافه می‌شود.",
        reply_markup=main_kb(uid == ADMIN_ID),
    )


async def _handle_subscription_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    photo = update.message.photo[-1] if update.message.photo else None
    if not photo:
        await update.message.reply_text("❌ لطفاً تصویر رسید را به صورت عکس ارسال کنید.")
        return

    plan_id = context.user_data.get("pending_subscription_plan_id")
    amount_toman = context.user_data.get("pending_subscription_amount_toman")
    if not plan_id or not amount_toman:
        context.user_data.pop("awaiting_subscription_card_receipt", None)
        await update.message.reply_text("❌ خطا: اطلاعات پرداخت مشخص نیست. لطفاً دوباره از ابتدا شروع کنید.")
        return

    description = update.message.caption or ""

    progress_msg = await update.message.reply_text("⏳ در حال دریافت تصویر رسید...")

    try:
        await _download_telegram_file(context, photo.file_id, f"./uploads/receipts/{photo.file_unique_id}.jpg")
    except Exception as e:
        logger.exception("failed to download subscription receipt photo")
        await progress_msg.edit_text("❌ مشکلی در دریافت تصویر رسید پیش آمد. لطفاً دوباره تلاش کنید.")
        return

    receipt_path = f"uploads/receipts/{photo.file_unique_id}.jpg"

    async with async_session() as db:
        from app.models import PaymentRequest
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")

        request = PaymentRequest(
            user_id=user.id,
            amount_toman=int(amount_toman),
            receipt_image_path=receipt_path,
            description=description if description else None,
            status="pending",
            payment_type="subscription",
            plan_id=int(plan_id),
        )
        db.add(request)
        await db.commit()

    _reset_ephemeral_state(context, clear_pending=True)

    try:
        from app.transactions_bot import send_new_payment_notification
        asyncio.create_task(send_new_payment_notification(request.id))
    except Exception:
        pass

    await progress_msg.edit_text(
        f"✅ درخواست پرداخت اشتراک شما با موفقیت ثبت شد.\n\n"
        f"مبلغ: {_format_toman(int(amount_toman))} تومان\n"
        f"وضعیت: در انتظار بررسی\n\n"
        "⏱ تأیید معمولاً ۵ تا ۱۰ دقیقه طول می‌کشد (به جز نیمه‌شب).\n"
        "پس از تأیید توسط ادمین، اشتراک شما فعال می‌شود.",
        reply_markup=main_kb(uid == ADMIN_ID),
    )


async def _handle_card_receipt_as_document(update: Update, context: ContextTypes.DEFAULT_TYPE, doc) -> None:
    uid = update.effective_user.id
    amount_toman = context.user_data.get("pending_card_amount_toman")
    if not amount_toman:
        context.user_data.pop("awaiting_card_receipt", None)
        await update.message.reply_text("❌ خطا: مبلغ پرداخت مشخص نیست. لطفاً دوباره از ابتدا شروع کنید.")
        return

    description = update.message.caption or ""
    progress_msg = await update.message.reply_text("⏳ در حال دریافت فایل رسید...")

    try:
        receipt_path = f"uploads/receipts/{doc.file_unique_id}.{doc.file_name.rsplit('.', 1)[-1] if '.' in doc.file_name else 'jpg'}"
        await _download_telegram_file(context, doc.file_id, f"./{receipt_path}")
    except Exception as e:
        logger.exception("failed to download receipt document")
        await progress_msg.edit_text("❌ مشکلی در دریافت فایل رسید پیش آمد. لطفاً دوباره تلاش کنید.")
        return

    async with async_session() as db:
        from app.models import PaymentRequest
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        request = PaymentRequest(
            user_id=user.id,
            amount_toman=int(amount_toman),
            receipt_image_path=receipt_path,
            description=description if description else None,
            status="pending",
            payment_type="topup",
        )
        db.add(request)
        await db.commit()

    _reset_ephemeral_state(context, clear_pending=True)
    await progress_msg.edit_text(
        f"✅ درخواست پرداخت شما با موفقیت ثبت شد.\n\n"
        f"مبلغ: {_format_toman(int(amount_toman))} تومان\n"
        f"وضعیت: در انتظار بررسی\n\n"
        "⏱ تأیید معمولاً ۵ تا ۱۰ دقیقه طول می‌کشد (به جز نیمه‌شب).\n"
        "پس از تأیید، اعتبار به کیف پول شما اضافه می‌شود.",
        reply_markup=main_kb(uid == ADMIN_ID),
    )


async def _handle_subscription_receipt_as_document(update: Update, context: ContextTypes.DEFAULT_TYPE, doc) -> None:
    uid = update.effective_user.id
    plan_id = context.user_data.get("pending_subscription_plan_id")
    amount_toman = context.user_data.get("pending_subscription_amount_toman")
    if not plan_id or not amount_toman:
        context.user_data.pop("awaiting_subscription_card_receipt", None)
        await update.message.reply_text("❌ خطا: اطلاعات پرداخت مشخص نیست. لطفاً دوباره از ابتدا شروع کنید.")
        return

    description = update.message.caption or ""
    progress_msg = await update.message.reply_text("⏳ در حال دریافت فایل رسید...")

    try:
        receipt_path = f"uploads/receipts/{doc.file_unique_id}.{doc.file_name.rsplit('.', 1)[-1] if '.' in doc.file_name else 'jpg'}"
        await _download_telegram_file(context, doc.file_id, f"./{receipt_path}")
    except Exception as e:
        logger.exception("failed to download subscription receipt document")
        await progress_msg.edit_text("❌ مشکلی در دریافت فایل رسید پیش آمد. لطفاً دوباره تلاش کنید.")
        return

    async with async_session() as db:
        from app.models import PaymentRequest
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        request = PaymentRequest(
            user_id=user.id,
            amount_toman=int(amount_toman),
            receipt_image_path=receipt_path,
            description=description if description else None,
            status="pending",
            payment_type="subscription",
            plan_id=int(plan_id),
        )
        db.add(request)
        await db.commit()

    _reset_ephemeral_state(context, clear_pending=True)
    await progress_msg.edit_text(
        f"✅ درخواست پرداخت اشتراک شما با موفقیت ثبت شد.\n\n"
        f"مبلغ: {_format_toman(int(amount_toman))} تومان\n"
        f"وضعیت: در انتظار بررسی\n\n"
        "⏱ تأیید معمولاً ۵ تا ۱۰ دقیقه طول می‌کشد (به جز نیمه‌شب).\n"
        "پس از تأیید توسط ادمین، اشتراک شما فعال می‌شود.",
        reply_markup=main_kb(uid == ADMIN_ID),
    )


async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    del context
    query = update.pre_checkout_query
    if query is None:
        return
    payment_payload = _parse_payment_payload(query.invoice_payload)
    payload = payment_payload.get(payment_payload["type"]) if payment_payload else None
    if payload is None:
        await query.answer(ok=False, error_message="درخواست پرداخت نامعتبر است.")
        return
    if int(query.total_amount or 0) != int(payload["total_rial"]):
        await query.answer(ok=False, error_message="مبلغ پرداخت با فاکتور هماهنگ نیست.")
        return
    from_user = query.from_user.id if query.from_user else None
    if from_user is None or int(from_user) != int(payload["user_id"]):
        await query.answer(ok=False, error_message="این فاکتور مخصوص حساب شما نیست.")
        return
    await query.answer(ok=True)


async def _handle_successful_subscription_payment(update: Update, payload: dict, payment) -> None:
    message = update.message
    if message is None:
        return
    uid = update.effective_user.id if update.effective_user else None
    if uid is None:
        await message.reply_text("⚠️ کاربر پرداخت‌کننده شناسایی نشد.")
        return
    charge_id = (
        (payment.telegram_payment_charge_id or "").strip()
        or (payment.provider_payment_charge_id or "").strip()
        or f"sub:{uid}:{payload['plan_id']}:{int(payment.total_amount or 0)}:{int(datetime.now(timezone.utc).timestamp())}"
    )
    idempotency_key = f"subscription:bale:{charge_id}"
    async with async_session() as db:
        from app.models import SubscriptionPlan, TomanLedgerEntry, UserSubscription
        from app.services.toman_billing_service import purchase_toman_subscription

        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        plan = (
            await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == int(payload["plan_id"])))
        ).scalar_one_or_none()
        if not plan:
            await message.reply_text("⚠️ پرداخت ثبت شد ولی پلن اشتراک پیدا نشد. لطفاً به پشتیبانی پیام بده.")
            return
        active_sub = (
            await db.execute(
                select(UserSubscription.id).where(
                    UserSubscription.user_id == user.id,
                    UserSubscription.status == "active",
                    UserSubscription.expires_at > _utcnow(),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if active_sub is not None:
            existing_payment = (
                await db.execute(select(TomanLedgerEntry.id).where(TomanLedgerEntry.idempotency_key == f"{idempotency_key}:payment").limit(1))
            ).scalar_one_or_none()
            existing_gift = (
                await db.execute(select(TomanLedgerEntry.id).where(TomanLedgerEntry.idempotency_key == idempotency_key).limit(1))
            ).scalar_one_or_none()
            if existing_payment is None and existing_gift is None:
                await message.reply_text(
                    "ℹ️ پرداخت ثبت شد ولی این حساب از قبل اشتراک فعال دارد.\n"
                    "برای بررسی این پرداخت لطفاً به پشتیبانی پیام بده."
                )
                return
        wallet_payment = int(payload.get("wallet_payment_toman") or 0)
        wallet_debit_usd = Decimal("0")
        if wallet_payment > 0:
            wallet_ok, _, wallet_debit_usd = await _debit_subscription_wallet_usd(
                db,
                user=user,
                wallet_payment_toman=wallet_payment,
                idempotency_key=f"{idempotency_key}:wallet-usd",
                metadata={
                    "plan_id": plan.id,
                    "payment_platform": "bale",
                    "total_amount_rial": int(payment.total_amount or 0),
                },
            )
            if not wallet_ok:
                await message.reply_text(
                    "⚠️ پرداخت آنلاین ثبت شد ولی کسر سهم کیف پول انجام نشد.\n"
                    "احتمالاً موجودی کیف پول همزمان تغییر کرده است. لطفاً به پشتیبانی پیام بده."
                )
                return
        result = await purchase_toman_subscription(
            db,
            user=user,
            plan=plan,
            idempotency_key=idempotency_key,
            payment_confirmed=True,
            wallet_payment_toman=0,
            grant_gift_toman_balance=False,
        )
        if not result.ok:
            await message.reply_text(
                "⚠️ پرداخت آنلاین ثبت شد ولی فعال‌سازی اشتراک کامل نشد.\n"
                f"علت: {result.reason or 'unknown'}\n"
                "لطفاً به پشتیبانی پیام بده."
            )
            return

        gift_credit = result.gift_credit_toman
        online_payment_toman = _rial_to_toman(int(payload["total_rial"]))
        toman_balance = await _toman_balance(db, user)
        await message.reply_text(
            "✅ پرداخت اشتراک با موفقیت انجام شد.\n"
            f"پلن: {plan.name}\n"
            f"پرداخت آنلاین: {_format_toman(online_payment_toman)}\n"
            f"پرداخت از کیف پول: {_format_toman(wallet_payment)}\n"
            f"اعتبار هدیه: {_format_toman(gift_credit)}\n"
            f"اعتبار تومانی جدید: {_format_toman(toman_balance)}",
            reply_markup=await _get_pending_action_markup(db, user),
        )
    await _mark_update_completed(update)


async def _handle_successful_toman_topup_payment(update: Update, payload: dict, payment) -> None:
    message = update.message
    if message is None:
        return
    uid = update.effective_user.id if update.effective_user else None
    if uid is None:
        await message.reply_text("⚠️ کاربر پرداخت‌کننده شناسایی نشد.")
        return
    charge_id = (
        (payment.telegram_payment_charge_id or "").strip()
        or (payment.provider_payment_charge_id or "").strip()
        or f"ttop:{uid}:{payload['credit_amount_toman']}:{int(payment.total_amount or 0)}:{int(datetime.now(timezone.utc).timestamp())}"
    )
    idempotency_key = f"toman_topup:bale:{charge_id}"
    async with async_session() as db:
        from app.services.toman_billing_service import apply_toman_topup, quote_toman_topup_payment

        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        quote = await quote_toman_topup_payment(db, user=user, credit_amount_toman=int(payload["credit_amount_toman"]))
        if int(quote.payment_due_toman) != int(payload["payment_due_toman"]):
            await message.reply_text(
                "⚠️ پرداخت ثبت شد ولی شرایط تخفیف شارژ تغییر کرده و اعتبار خودکار اضافه نشد.\n"
                "لطفاً به پشتیبانی پیام بده."
            )
            return
        result = await apply_toman_topup(
            db,
            user=user,
            credit_amount_toman=int(payload["credit_amount_toman"]),
            idempotency_key=idempotency_key,
            metadata={
                "payment_platform": "bale",
                "payment_currency": payment.currency,
                "invoice_payload": payment.invoice_payload,
                "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                "provider_payment_charge_id": payment.provider_payment_charge_id,
                "total_amount_rial": int(payment.total_amount or 0),
                "payment_due_toman": int(payload["payment_due_toman"]),
            },
        )
        if not result.ok:
            await message.reply_text("⚠️ پرداخت ثبت شد ولی شارژ اعتبار کامل نشد. لطفاً به پشتیبانی پیام بده.")
            return
        total_balance = int(result.account.gift_balance_toman or 0) + int(result.account.paid_balance_toman or 0)
        discount_line = f"\nتخفیف اعمال‌شده: {_format_toman(result.quote.discount_toman)}" if result.quote.discount_toman else ""
        await message.reply_text(
            "✅ شارژ اعتبار با موفقیت انجام شد.\n"
            f"اعتبار اضافه‌شده: {_format_toman(result.quote.credit_amount_toman)}\n"
            f"مبلغ پرداختی: {_format_toman(result.quote.payment_due_toman)}"
            f"{discount_line}\n"
            f"موجودی تومانی جدید: {_format_toman(total_balance)}",
            reply_markup=await _get_pending_action_markup(db, user),
        )
    await _mark_update_completed(update)


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None or message.successful_payment is None:
        return
    payment = message.successful_payment
    payment_payload = _parse_payment_payload(payment.invoice_payload)
    payload = payment_payload.get(payment_payload["type"]) if payment_payload else None
    if payload is None:
        await message.reply_text("⚠️ پرداخت ثبت شد ولی payload معتبر نبود. لطفاً به پشتیبانی پیام بده.")
        return
    if int(payment.total_amount or 0) != int(payload["total_rial"]):
        await message.reply_text("⚠️ پرداخت ثبت شد ولی مبلغ تراکنش با payload همخوانی نداشت.")
        return
    uid = update.effective_user.id if update.effective_user else None
    if uid is None or int(uid) != int(payload["user_id"]):
        await message.reply_text("⚠️ این رسید مربوط به حساب دیگری است.")
        return
    if payment_payload["type"] == "subscription":
        await _handle_successful_subscription_payment(update, payment_payload["subscription"], payment)
        return
    if payment_payload["type"] == "toman_topup":
        await _handle_successful_toman_topup_payment(update, payment_payload["toman_topup"], payment)
        return

    # USD wallet topups are no longer supported; everything is Toman now.
    await update.message.reply_text(
        "⚠️ شارژ دلاری دیگر پشتیبانی نمی‌شود.\n"
        "لطفاً از دستور /toman_topup برای شارژ به تومان استفاده کنید."
    )
    await _mark_update_completed(update)
    return


async def _check_and_send_math_tip(bot, chat_id: int, text: str, db: AsyncSession, user_id: int):
    if not bot:
        return
    import re
    if not re.search(r'(\$|\\\[|\\begin\{)', text):
        return
    from app.models import UserPreference
    from sqlalchemy import select
    import asyncio
    
    result = await db.execute(select(UserPreference).filter_by(telegram_user_id=user_id))
    pref = result.scalar_one_or_none()
    
    if pref and not getattr(pref, 'tip_pdf_math_dismissed', False):
        tip_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("متوجه شدم", callback_data="tip_math_temp"),
                InlineKeyboardButton("دیگر نشان نده", callback_data="tip_math_perm")
            ]
        ])
        try:
            tip_msg = await bot.send_message(
                chat_id=chat_id,
                text="💡 نکته (TIPS): چون این پیام دارای فرمول ریاضی است، برای خوانایی بهتر می‌توانید با زدن دکمه «تبدیل به PDF» در پیام بالا، آن را به فایل تبدیل کنید.",
                reply_markup=tip_kb
            )
            
            async def delete_later():
                await asyncio.sleep(30)
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=tip_msg.message_id)
                except Exception:
                    pass
            
            asyncio.create_task(delete_later())
        except Exception:
            pass


async def _run_tool_aware_completion(
    update: Update,
    db: AsyncSession,
    *,
    user: UserPreference,
    user_message: Message,
    chat: Chat,
    provider,
    model,
    llm_messages: list[dict],
    proj_label: str = "",
    allow_tools: bool = True,
    uploaded_file_id: int | None = None,
    status_message_obj=None,
    routing: dict | None = None,
    payg_consent: bool = False,
) -> str:
    # Token estimation and credit check (Toman)
    estimated_in_tokens = _estimate_messages_tokens(llm_messages)
    estimated_quote = await _get_chat_quote_toman(db, model, estimated_in_tokens, CHAT_OUTPUT_TOKEN_ESTIMATE)
    estimated_cost_toman = estimated_quote.billable_cost_toman
    
    ok, reason, user_sub = await _has_toman_credit_for_cost(db, user, model, estimated_in_tokens, CHAT_OUTPUT_TOKEN_ESTIMATE)
    is_limit_reached = reason in ["cooldown_limit_reached", "weekly_limit_reached", "cooldown_payg_available", "weekly_limit_payg_available"]
    if payg_consent:
        is_limit_reached = False
    if not ok or is_limit_reached:
        current_balance = await _toman_balance(db, user)
        user.pending_action_payload = {
            "action_type": "chat_completion",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "user_message_id": user_message.id,
                "chat_id": chat.id,
                "provider_name": getattr(provider, "name", ""),
                "model_name": getattr(model, "name", "") if hasattr(model, "name") else model,
                "llm_messages": llm_messages,
                "proj_label": proj_label,
                "allow_tools": allow_tools,
                "uploaded_file_id": uploaded_file_id,
            }
        }
        await db.commit()
        
        if is_limit_reached:
            text = _limit_reached_text(reason, user_sub)
            kb = _limit_reached_kb(reason)
        else:
            text = _insufficient_toman_credit_text(
                needed_toman=estimated_cost_toman,
                balance_toman=current_balance,
                action_label="تولید پاسخ",
            )
            kb = _insufficient_toman_credit_kb()

        await update.message.reply_text(text, reply_markup=kb)
        return ""

    estimated_cost_usd = estimated_quote.global_api_cost_usd
    usage_event = await _create_usage_event(
        db,
        user=user,
        chat_id=chat.id,
        message_id=user_message.id,
        operation_type="chat_completion",
        uploaded_file_id=uploaded_file_id,
        provider_name=provider.name,
        provider_id=getattr(provider, "id", None),
        model=model,
        estimated_cost_usd=estimated_cost_usd,
        request_id=f"telegram:{update.update_id}:chat:{chat.id}:message:{user_message.id}",
        metadata={
            "tool_aware": bool(allow_tools),
            "estimated_toman_billing": _toman_usage_metadata(estimated_quote, input_tokens=estimated_in_tokens, output_tokens=CHAT_OUTPUT_TOKEN_ESTIMATE),
        },
    )
    usage_event.status = "authorized"
    await db.flush()

    sent_msg = status_message_obj
    if sent_msg is None:
        sent_msg = await update.message.reply_text(f"⏳{proj_label}")
    elif proj_label:
        await _send_or_edit_formatted(sent_msg, f"⏳{proj_label}")
    tool_specs = await get_chat_tools(db, chat) if allow_tools else []
    usage_logs: list[dict | None] = []
    initial_reasoning = None
    followup_reasoning = None
    
    # Detect if any message has image input for error handling
    has_image_input = messages_include_image_input(llm_messages)

    telegram_chat_id = update.effective_chat.id
    task = None
    spinner_task_handle = None
    typing_task = None

    async def _typing_loop():
        while True:
            try:
                # Use update.get_bot() or context.bot if available. 
                # In this scope, we can use update.message.bot if update.message exists.
                bot = update.get_bot() if hasattr(update, "get_bot") else getattr(update, "_bot", None)
                if bot:
                    await bot.send_chat_action(chat_id=telegram_chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4.5)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5.0)

    try:
        from app.agent_routes import event_generator
        typing_task = asyncio.create_task(_typing_loop())
        
        # Prepare the message from the last llm_message (user message)
        user_text = llm_messages[-1].get("content", "") if llm_messages else ""
        thread_id = f"chat_{chat.id}"
        
        full_reply = ""
        tool_calls_count = 0
        
        task = _register_user_task(telegram_chat_id)

        # Extract system content from llm_messages if present
        system_content = next((m["content"] for m in llm_messages if m["role"] == "system"), None)
        if not system_content:
            system_content = "You are a helpful AI assistant."
            
        gen = event_generator(
            user_text,
            thread_id,
            provider,
            model,
            chat_id=chat.id,
            message_id=user_message.id,
            system_prompt=system_content,
            user_id=user.id,
            project_id=user.current_project_id,
        )
        
        last_edit_time = time.time()
        
        status_labels = {
            "web_search": ("🔍", "جستجو در وب"),
            "run_python": ("🐍", "اجرای کد پایتون"),
            "pdf_generator": ("📄", "تولید فایل PDF"),
            "send_file": ("📤", "ارسال فایل"),
            "image_generation": ("🎨", "تولید تصویر"),
            "search_documents": ("📂", "جستجو در پایگاه دانش"),
            "tool": ("🛠", "استفاده از ابزار")
        }
        
        execution_steps = []

        current_spinner_frame = "🔄"

        def _get_display_text(spinner_frame=None):
            nonlocal current_spinner_frame
            if spinner_frame:
                current_spinner_frame = spinner_frame
            
            lines = []
            # Only show "در حال پردازش" if we don't have a reply yet and no execution steps
            if not full_reply and not execution_steps:
                lines.append(f"{current_spinner_frame} در حال پردازش...")
            
            for step in execution_steps:
                icon, label = step["icon"], step["label"]
                if step["status"] == "completed":
                    lines.append(f"✅ {icon} {label}")
                else:
                    lines.append(f"⏳ {icon} {label}")
            
            status_text = "\n.\n".join(lines)
            if status_text and full_reply:
                return f"{status_text}\n\n{full_reply}"
            elif status_text:
                return status_text
            return full_reply or "⏳"
        
        async def _spinner_updater():
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            i = 0
            while True:
                await asyncio.sleep(1.2)
                try:
                    await _send_or_edit_formatted(sent_msg, _get_display_text(frames[i % len(frames)]))
                    i += 1
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        spinner_task_handle = asyncio.create_task(_spinner_updater())
        
        async for event in gen:
            raw_data = event.get("data")
            if not raw_data:
                continue
            try:
                data = json.loads(raw_data)
            except Exception:
                continue

            evt_type = data.get("type")
            if evt_type == "content":
                chunk_text = data.get("content", "")
                full_reply += chunk_text

                # Throttle updates to avoid hitting rate limits
                current_time = time.time()
                if current_time - last_edit_time > 1.5:
                    try:
                        await _send_or_edit_formatted(sent_msg, _get_display_text() + " ✍️")
                        last_edit_time = current_time
                    except Exception:
                        pass
            elif evt_type == "tool_start":
                tool_calls_count += 1
                tool_name = data.get("tool", "tool")
                icon, label = status_labels.get(tool_name, ("🛠", tool_name))
                
                # Deduplicate: only add if no "running" step for this tool exists
                if not any(s["label"] == label and s["status"] == "running" for s in execution_steps):
                    execution_steps.append({"label": label, "icon": icon, "status": "running"})
                    try:
                        await _send_or_edit_formatted(sent_msg, _get_display_text())
                    except Exception:
                        pass
            elif evt_type == "tool_end":
                # Mark the last running step of this type as completed
                tool_name = data.get("tool")
                _, label = status_labels.get(tool_name, ("🛠", tool_name))
                for step in reversed(execution_steps):
                    if step["label"] == label and step["status"] == "running":
                        step["status"] = "completed"
                        break

                try:
                    await _send_or_edit_formatted(sent_msg, _get_display_text())
                except Exception:
                    pass

                tool_name = data.get("tool")
                tool_output = data.get("output")
                if tool_name in ("pdf_generator", "send_file") and tool_output:
                    try:
                        res_dict = json.loads(tool_output)
                        await _maybe_upload_generated_file_to_chat(update, tool_name=tool_name, tool_result=res_dict)
                    except Exception:
                        pass
                elif tool_name == "image_generator" and tool_output:
                    try:
                        res_dict = json.loads(tool_output)
                        if res_dict.get("ok") and res_dict.get("saved_image_paths"):
                            for path in res_dict["saved_image_paths"]:
                                if os.path.isfile(path):
                                    with open(path, "rb") as f:
                                        await update.message.reply_photo(photo=f)
                    except Exception as e:
                        logger.warning(f"Failed to upload generated image: {e}")
                elif tool_name == "run_python" and tool_output:
                    try:
                        res_dict = parse_tool_output(tool_output)
                        files_to_send = files_to_deliver_from_python(res_dict)
                        if files_to_send:
                            logger.info("Delivering run_python files to chat: %s", files_to_send)
                            for path in files_to_send:
                                if os.path.isfile(path):
                                    ext = __import__('os').path.splitext(path)[1].lower()
                                    with open(path, "rb") as f:
                                        if ext in [".png", ".jpg", ".jpeg", ".webp"]:
                                            await update.message.reply_photo(photo=f)
                                        else:
                                            await update.message.reply_document(document=f)
                    except Exception as exc:
                        logger.warning("Failed to deliver run_python files to chat: %s", exc)
            elif evt_type == "usage":
                usage_logs.append(data.get("usage"))
            elif evt_type == "error":
                raise Exception(data.get("error"))
            elif evt_type == "done":
                pass
    
        if task:
            _unregister_user_task(telegram_chat_id, task)
            
    except asyncio.CancelledError:
        uid = update.effective_user.id if update.effective_user else 0
        if task:
            _unregister_user_task(telegram_chat_id, task)
        raise
    except Exception as exc:
        uid = update.effective_user.id if update.effective_user else 0
        if task:
            _unregister_user_task(telegram_chat_id, task)
        usage_event.status = "failed"
        usage_event.error = str(exc)
        usage_event.completed_at = _utcnow()
        await db.commit()
        if has_image_input and "unsupported_image_input" in str(exc):
            await _send_image_capability_error(update, db, model=model, message_obj=sent_msg)
            return ""
        if "Active Codex subscription with a capacity pool is required" in str(exc):
            await _send_subscription_required_error(update, db, message_obj=sent_msg)
            return ""
        raise
    finally:
        if spinner_task_handle:
            spinner_task_handle.cancel()
        if typing_task:
            typing_task.cancel()

    if routing and routing.get("router_usage"):
        usage_logs.append(routing["router_usage"])

    if is_codex_subscription_provider(provider):
        codex_billable_usage = calculate_codex_billable_usage(
            usage_logs,
            estimated_app_input_tokens=estimated_in_tokens,
            default_output_tokens=CHAT_OUTPUT_TOKEN_ESTIMATE,
        )
        usage_input_tokens = codex_billable_usage["input_tokens"]
        usage_output_tokens = codex_billable_usage["output_tokens"]
        usage_source = codex_billable_usage["usage_source"]
        usage_event_metadata = usage_event.metadata_json if isinstance(usage_event.metadata_json, dict) else {}
        usage_event_metadata["codex_provider_usage"] = codex_billable_usage.get("provider_usage")
        usage_event_metadata["codex_billable_usage"] = {
            "input_tokens": usage_input_tokens,
            "output_tokens": usage_output_tokens,
            "total_tokens": usage_input_tokens + usage_output_tokens,
        }
        usage_event_metadata["codex_billing_note"] = "Input billing excludes Codex CLI internal prompt overhead and uses the app-visible prompt estimate."
        usage_event.metadata_json = usage_event_metadata
    else:
        usage_input_tokens, usage_output_tokens = _sum_usage_tokens(usage_logs)
        usage_source = "provider_reported" if (usage_input_tokens > 0 or usage_output_tokens > 0) else "estimated"
        if usage_input_tokens == 0 and usage_output_tokens == 0 and estimated_cost_usd > 0:
            usage_input_tokens = estimated_in_tokens
            usage_output_tokens = _estimate_text_tokens(full_reply) if full_reply else CHAT_OUTPUT_TOKEN_ESTIMATE
        elif usage_input_tokens == 0:
            usage_source = "partial_estimated"
        elif usage_output_tokens == 0:
            usage_output_tokens = _estimate_text_tokens(full_reply) if full_reply else CHAT_OUTPUT_TOKEN_ESTIMATE
            usage_source = "partial_estimated"
    reasoning = merge_reasoning_metadata(initial_reasoning, followup_reasoning)
    if reasoning:
        usage_event_metadata = usage_event.metadata_json if isinstance(usage_event.metadata_json, dict) else {}
        usage_event_metadata["reasoning_summary"] = reasoning.get("summary")
        usage_event_metadata["reasoning_topics"] = [
            str(stage.get("topic"))
            for stage in (reasoning.get("stages") or [])
            if isinstance(stage, dict) and stage.get("topic")
        ][:6]
        usage_event.metadata_json = usage_event_metadata
    actual_quote_usd = await _get_chat_quote_usd(db, model, usage_input_tokens, usage_output_tokens)
    actual_quote_toman = await _get_chat_quote_toman(db, model, usage_input_tokens, usage_output_tokens)
    usage_event_metadata = usage_event.metadata_json if isinstance(usage_event.metadata_json, dict) else {}
    usage_event_metadata["actual_usd_billing"] = _usd_usage_metadata(actual_quote_usd, input_tokens=usage_input_tokens, output_tokens=usage_output_tokens)
    usage_event_metadata["actual_toman_billing"] = _toman_usage_metadata(actual_quote_toman, input_tokens=usage_input_tokens, output_tokens=usage_output_tokens)
    usage_event.metadata_json = usage_event_metadata
    await _complete_usage_event(
        db,
        usage_event,
        input_tokens=usage_input_tokens,
        output_tokens=usage_output_tokens,
        actual_cost_usd=actual_quote_usd.global_api_cost_usd,
        usage_source=usage_source,
    )
    from app.services.toman_billing_service import charge_chat_usage_toman
    charge_result = await charge_chat_usage_toman(
        db,
        user=user,
        model=model,
        input_tokens=usage_input_tokens,
        output_tokens=usage_output_tokens,
        usage_event_id=usage_event.id if usage_event else None,
        idempotency_key=f"usage:{usage_event.id}:charge" if usage_event else None,
        metadata={
            "chat_id": chat.id,
            "message_id": user_message.id,
            "usage_event_id": usage_event.id,
            "model_id": model.id,
            "model_name": model.name,
            "provider_name": provider.name,
            "input_tokens": usage_input_tokens,
            "output_tokens": usage_output_tokens,
            "tool_calls": tool_calls_count,
        },
    )
    if not charge_result.ok:
        usage_event.status = "billing_failed"
        usage_event.error = "insufficient toman credit during final charge"
        await db.commit()
        current_balance = await _toman_balance(db, user)
        await _send_or_edit_formatted(
            sent_msg,
            _insufficient_toman_credit_text(
                needed_toman=actual_quote_toman.billable_cost_toman,
                balance_toman=current_balance,
                action_label="ثبت هزینه پاسخ",
            ),
            reply_markup=_insufficient_toman_credit_kb()
        )
        return full_reply
    usage_event.status = "completed"
    usage_event.completed_at = _utcnow()
    await db.commit()
    pdf_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📄 تبدیل به PDF", callback_data="pdf_export")]])
    await _send_final_response(update, sent_msg, full_reply, reply_markup=pdf_kb)

    if is_codex_subscription_provider(provider):
        try:
            from app.services.codex_runtime import CODEX_WORKSPACES_DIR
            from pathlib import Path
            import time as _time
            now = _time.time()
            image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
            doc_exts = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".py", ".html"}
            generated = []
            if CODEX_WORKSPACES_DIR.exists():
                for acct_dir in CODEX_WORKSPACES_DIR.iterdir():
                    if not acct_dir.is_dir():
                        continue
                    for entry in acct_dir.rglob("*"):
                        if not entry.is_file():
                            continue
                        ext = entry.suffix.lower()
                        if ext not in image_exts and ext not in doc_exts:
                            continue
                        if now - entry.stat().st_mtime > 120:
                            continue
                        generated.append({
                            "path": str(entry),
                            "filename": entry.name,
                            "size": entry.stat().st_size,
                            "type": "image" if ext in image_exts else "document",
                        })
            if generated:
                await _send_generated_files(update, generated)
        except Exception as e:
            logger.warning(f"Failed to send generated Codex files: {e}")

    bot = update.get_bot() if hasattr(update, "get_bot") else getattr(update, "_bot", None)
    await _check_and_send_math_tip(bot, update.effective_chat.id, full_reply, db, user.telegram_user_id)
    return full_reply


async def _run_precomputed_spreadsheet_completion(
    update: Update,
    db: AsyncSession,
    *,
    user: UserPreference,
    user_message: Message,
    chat: Chat,
    provider,
    model,
    user_text: str,
    system_content: str,
    preprocessing: SpreadsheetPreprocessResult,
) -> tuple[str, list[dict]]:
    compact_system = (
        f"{system_content}\n\n"
        "LOW-TOKEN SPREADSHEET MODE:\n"
        "A deterministic Python preprocessing step has already read the uploaded spreadsheets and computed the required numeric metrics. "
        "Use only the computed summary below for spreadsheet facts; do not ask to inspect raw rows and do not invent extra raw data.\n\n"
        f"{preprocessing.prompt_context}"
    )
    llm_messages = [
        {"role": "system", "content": compact_system},
        {"role": "user", "content": user_text},
    ]
    estimated_in_tokens = _estimate_messages_tokens(llm_messages)
    estimated_quote = await _get_chat_quote_toman(db, model, estimated_in_tokens, CHAT_OUTPUT_TOKEN_ESTIMATE)
    estimated_cost_toman = estimated_quote.billable_cost_toman
    ok, reason, user_sub = await _has_toman_credit_for_cost(db, user, model, estimated_in_tokens, CHAT_OUTPUT_TOKEN_ESTIMATE)
    is_limit_reached = reason in ["cooldown_limit_reached", "weekly_limit_reached", "cooldown_payg_available", "weekly_limit_payg_available"]
    if not ok or is_limit_reached:
        current_balance = await _toman_balance(db, user)
        user.pending_action_payload = {
            "action_type": "chat_completion",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "user_message_id": user_message.id,
                "chat_id": chat.id,
                "provider_name": getattr(provider, "name", ""),
                "model_name": getattr(model, "name", "") if hasattr(model, "name") else model,
                "llm_messages": llm_messages,
                "low_token_spreadsheet_mode": True,
            },
        }
        await db.commit()
        if is_limit_reached:
            text = _limit_reached_text(reason, user_sub)
            kb = _limit_reached_kb(reason)
        else:
            text = _insufficient_toman_credit_text(
                needed_toman=estimated_cost_toman,
                balance_toman=current_balance,
                action_label="تولید پاسخ",
            )
            kb = _insufficient_toman_credit_kb()
            
        await update.message.reply_text(text, reply_markup=kb)
        return "", llm_messages

    usage_event = await _create_usage_event(
        db,
        user=user,
        chat_id=chat.id,
        message_id=user_message.id,
        operation_type="chat_completion",
        provider_name=provider.name,
        provider_id=getattr(provider, "id", None),
        model=model,
        estimated_cost_usd=0,
        request_id=f"telegram:{update.update_id}:compact-spreadsheet:{chat.id}:message:{user_message.id}",
        metadata={
            "low_token_spreadsheet_mode": True,
            "source_files": preprocessing.source_files,
            "raw_input_chars": preprocessing.raw_input_chars,
            "compact_chars": preprocessing.compact_chars,
            "estimated_toman_billing": _toman_usage_metadata(estimated_quote, input_tokens=estimated_in_tokens, output_tokens=CHAT_OUTPUT_TOKEN_ESTIMATE),
        },
    )
    usage_event.status = "authorized"
    await db.flush()

    sent_msg = await update.message.reply_text("⏳ در حال محاسبه و نوشتن گزارش کم‌مصرف...")
    try:
        response = await request_chat_completion(provider, model.name, llm_messages, user_id=user.id, chat_id=chat.id)
        reply = (response.get("message") or {}).get("content") or ""
        if is_codex_subscription_provider(provider):
            codex_billable_usage = calculate_codex_billable_usage(
                [response.get("usage")],
                estimated_app_input_tokens=estimated_in_tokens,
                default_output_tokens=CHAT_OUTPUT_TOKEN_ESTIMATE,
            )
            usage_input_tokens = codex_billable_usage["input_tokens"]
            usage_output_tokens = codex_billable_usage["output_tokens"]
            usage_source = codex_billable_usage["usage_source"]
            usage_event_metadata = usage_event.metadata_json if isinstance(usage_event.metadata_json, dict) else {}
            usage_event_metadata["codex_provider_usage"] = codex_billable_usage.get("provider_usage")
            usage_event_metadata["codex_billable_usage"] = {
                "input_tokens": usage_input_tokens,
                "output_tokens": usage_output_tokens,
                "total_tokens": usage_input_tokens + usage_output_tokens,
            }
            usage_event_metadata["codex_billing_note"] = "Input billing excludes Codex CLI internal prompt overhead and uses the app-visible prompt estimate."
            usage_event.metadata_json = usage_event_metadata
        else:
            usage_input_tokens, usage_output_tokens = _extract_usage_tokens(response.get("usage"))
            usage_source = "provider_reported" if (usage_input_tokens > 0 or usage_output_tokens > 0) else "estimated"
            if usage_input_tokens == 0 and usage_output_tokens == 0:
                usage_input_tokens = estimated_in_tokens
                usage_output_tokens = _estimate_text_tokens(reply) if reply else CHAT_OUTPUT_TOKEN_ESTIMATE
            elif usage_input_tokens == 0:
                usage_source = "partial_estimated"
            elif usage_output_tokens == 0:
                usage_output_tokens = _estimate_text_tokens(reply) if reply else CHAT_OUTPUT_TOKEN_ESTIMATE
                usage_source = "partial_estimated"

        if _user_requested_pdf(user_text) and reply.strip():
            try:
                pdf_result = await run_pdf_generator_tool(
                    {
                        "content": reply,
                        "output_filename": "earthquake_analysis_report.pdf",
                        "latex_mode": "body",
                        "rtl": True,
                        "title": "گزارش تحلیل رکوردهای زلزله",
                    }
                )
                await _maybe_upload_generated_file_to_chat(update, tool_name="pdf_generator", tool_result=pdf_result)
            except Exception as pdf_exc:
                reply = f"{reply}\n\n⚠️ ساخت PDF با خطا روبه‌رو شد: {str(pdf_exc)[:300]}"

        actual_quote_usd = await _get_chat_quote_usd(db, model, usage_input_tokens, usage_output_tokens)
        actual_quote_toman = await _get_chat_quote_toman(db, model, usage_input_tokens, usage_output_tokens)
        usage_event_metadata = usage_event.metadata_json if isinstance(usage_event.metadata_json, dict) else {}
        usage_event_metadata["actual_usd_billing"] = _usd_usage_metadata(actual_quote_usd, input_tokens=usage_input_tokens, output_tokens=usage_output_tokens)
        usage_event_metadata["actual_toman_billing"] = _toman_usage_metadata(actual_quote_toman, input_tokens=usage_input_tokens, output_tokens=usage_output_tokens)
        usage_event.metadata_json = usage_event_metadata
        await _complete_usage_event(
            db,
            usage_event,
            input_tokens=usage_input_tokens,
            output_tokens=usage_output_tokens,
            actual_cost_usd=actual_quote_usd.global_api_cost_usd,
            usage_source=usage_source,
        )
        from app.services.toman_billing_service import charge_chat_usage_toman
        charge_result = await charge_chat_usage_toman(
            db,
            user=user,
            model=model,
            input_tokens=usage_input_tokens,
            output_tokens=usage_output_tokens,
            usage_event_id=usage_event.id if usage_event else None,
            idempotency_key=f"usage:{usage_event.id}:charge" if usage_event else None,
            metadata={
                "chat_id": chat.id,
                "message_id": user_message.id,
                "usage_event_id": usage_event.id,
                "model_id": model.id,
                "model_name": model.name,
                "provider_name": provider.name,
                "input_tokens": usage_input_tokens,
                "output_tokens": usage_output_tokens,
                "low_token_spreadsheet_mode": True,
            },
        )
        if not charge_result.ok:
            usage_event.status = "billing_failed"
            usage_event.error = "insufficient toman credit during compact spreadsheet charge"
            await db.commit()
        else:
            await db.commit()

        await _send_final_response(update, sent_msg, reply)
        return reply, llm_messages
    except Exception as exc:
        usage_event.status = "failed"
        usage_event.error = str(exc)
        usage_event.completed_at = _utcnow()
        await db.commit()
        try:
            await _send_or_edit_formatted(sent_msg, f"❌ {str(exc)[:4000]}")
        except Exception:
            pass
        raise


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

ADMIN_ID = 567136570
CHATS_PAGE_SIZE = 10

# ─── STATES ───
ADD_PROV_NAME, ADD_PROV_URL, ADD_PROV_KEY = range(3)
ADD_MODEL_NAME, ADD_MODEL_DISPLAY, ADD_MODEL_PROVIDER, ADD_MODEL_PRICE_IN, ADD_MODEL_PRICE_OUT, ADD_MODEL_CONTEXT = range(3, 9)
ASKING_NAME = 9  # New user onboarding state

admin_temp: dict[int, dict] = {}
USER_AGENT_TASKS: dict[int, set[asyncio.Task]] = {}
STOP_REQUESTED: dict[int, float] = {}  # key (uid or chat_id) -> timestamp

from collections import defaultdict
import asyncio

ALBUM_PENDING_COUNT = defaultdict(int)
ALBUM_CAPTIONS = {}
ALBUM_MESSAGES = {}
ALBUM_EXTRACTED_TEXTS = defaultdict(list)
ALBUM_FILE_REFS = defaultdict(list)
ALBUM_LOCK = asyncio.Lock()
ALBUM_STATUS_MSG = {} # mg_id -> Message object

async def _register_album_update(
    update: Update,
    extracted_text: str = None,
    file_id: int = None,
    *,
    count_pending: bool = True,
    rag: bool = False,
):
    mg_id = update.message.media_group_id
    if not mg_id: return
    async with ALBUM_LOCK:
        if count_pending:
            ALBUM_PENDING_COUNT[mg_id] += 1
        if update.message.caption:
            ALBUM_CAPTIONS[mg_id] = update.message.caption
        if extracted_text:
            filename = update.message.document.file_name if update.message.document else "image"
            ALBUM_EXTRACTED_TEXTS[mg_id].append((filename, extracted_text))
        if file_id:
            filename = None
            is_image = bool(getattr(update.message, "photo", None))
            document = getattr(update.message, "document", None)
            if document:
                filename = document.file_name
                ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
                is_image = ext in ("jpg", "jpeg", "png", "webp")
            ALBUM_FILE_REFS[mg_id].append({
                "id": file_id,
                "filename": filename or "image",
                "rag": rag,
                "is_image": is_image,
            })
        ALBUM_MESSAGES[mg_id] = update # keep latest update for context

async def _finish_album_update(update: Update, context: ContextTypes.DEFAULT_TYPE, process_album_func):
    mg_id = update.message.media_group_id
    if not mg_id: return
    trigger_llm = False
    caption = None
    target_update = None
    texts = []
    f_ids = []
    file_refs = []
    
    async with ALBUM_LOCK:
        ALBUM_PENDING_COUNT[mg_id] -= 1
        if ALBUM_PENDING_COUNT[mg_id] <= 0:
            ALBUM_PENDING_COUNT.pop(mg_id, None)
            status_msg = ALBUM_STATUS_MSG.pop(mg_id, None)
            caption = ALBUM_CAPTIONS.pop(mg_id, None)
            target_update = ALBUM_MESSAGES.pop(mg_id, None)
            texts = ALBUM_EXTRACTED_TEXTS.pop(mg_id, [])
            file_refs = ALBUM_FILE_REFS.pop(mg_id, [])
            f_ids = [ref.get("id") for ref in file_refs if isinstance(ref, dict) and ref.get("id") is not None]
            
            if (caption or texts or f_ids) and target_update:
                trigger_llm = True
    
    if trigger_llm:
        await asyncio.sleep(1.0)
        
        # If no caption, route album items to pending_files_queue for unified UX
        if not caption:
            if "pending_files_queue" not in context.user_data:
                context.user_data["pending_files_queue"] = []
            
            for ref in file_refs:
                queue_item = {
                    "filename": ref.get("filename", "file"),
                    "id": ref.get("id"),
                    "rag": bool(ref.get("rag")),
                    "is_image": bool(ref.get("is_image")),
                }
                fname = ref.get("filename", "file")
                for t_fname, t_text in texts:
                    if t_fname == fname:
                        queue_item["text"] = t_text[:15000]
                        break
                context.user_data["pending_files_queue"].append(queue_item)
            
            q_len = len(context.user_data["pending_files_queue"])
            reply_text = f"✅ {q_len} فایل دریافت شد."
            try:
                if status_msg:
                    await status_msg.edit_text(reply_text)
                else:
                    await target_update.message.reply_text(reply_text)
            except Exception:
                pass
            
            try:
                await target_update.message.reply_text(
                    "می‌تونی فایل‌های دیگه‌ای بفرستی یا با زدن دکمه زیر شروع به گفتگو کنی 👇",
                    reply_markup=upload_queue_kb()
                )
            except Exception:
                pass
            return
        
        # Album with caption: process immediately like single files with caption
        image_tags = "\n".join(
            f"[عکس ارسال شده: ID={ref.get('id')}]"
            for ref in file_refs
            if isinstance(ref, dict) and ref.get("is_image") and ref.get("id") is not None
        )
        combined_forced_text = "\n".join(part for part in (image_tags, caption or "") if part).strip()
        context.user_data["album_context"] = {"texts": texts, "file_ids": f_ids, "files": file_refs}
        
        # FIX 1: Persist file content to DB messages so it survives bot restarts
        if target_update and target_update.effective_user and texts:
            try:
                async with async_session() as db:
                    uid = target_update.effective_user.id
                    user = await get_user(db, uid, target_update.effective_user.first_name or "", target_update.effective_user.username or "")
                    chat_id = user.current_chat_id
                    if not chat_id:
                        chat = Chat(title="💬 چت جدید", model_id=user.current_model_id, project_id=user.current_project_id, user_preference_id=user.id)
                        db.add(chat); await db.commit(); await db.refresh(chat)
                        chat_id = chat.id; user.current_chat_id = chat.id; await db.commit()
                    
                    for fname, ftext in texts:
                        db.add(Message(chat_id=chat_id, role="system", content=f"[Uploaded File: {fname}]\n{ftext[:15000]}"))
                    await db.commit()
            except Exception:
                pass  # Non-critical, don't block the response
        
        await process_album_func(target_update, context, forced_text=combined_forced_text, status_message_obj=status_msg)
        # FIX 3: Don't pop album_context — keep it for subsequent questions

def _is_stopping(key: int) -> bool:
    """Check if a stop was recently requested for this user or chat."""
    t = STOP_REQUESTED.get(key, 0)
    return (time.time() - t) < 7.0

def _register_user_task(key: int) -> asyncio.Task:
    task = asyncio.current_task()
    if key not in USER_AGENT_TASKS:
        USER_AGENT_TASKS[key] = set()
    USER_AGENT_TASKS[key].add(task)
    return task

def _unregister_user_task(key: int, task: asyncio.Task):
    if key in USER_AGENT_TASKS:
        USER_AGENT_TASKS[key].discard(task)
        if not USER_AGENT_TASKS[key]:
            USER_AGENT_TASKS.pop(key, None)

TRANSIENT_FLAGS = {
    "asking_name",
    "account_set_name_return",
    "awaiting_toman_topup_amount",
    "awaiting_card_receipt",
    "awaiting_account_promo_code",
    "pending_card_amount_toman",
    "awaiting_subscription_card_receipt",
    "pending_subscription_plan_id",
    "pending_subscription_amount_toman",
}

NAVIGATION_TEXTS = {
    "💎 اشتراک‌ها", "💰 افزایش شارژ", "👤 حساب کاربری",
    "🎁 دعوت دوستان", "🚀 باز کردن دکتر بز",
    "🔧 مدیریت", "👥 یوزرها", "📋 درخواست‌های پرداخت",
    "🔙 منوی اصلی", "📞 پشتیبانی",
}

TOOL_GUIDANCE_STYLES = {"compact", "detailed"}
DEFAULT_TOOL_GUIDANCE_STYLE = "compact"
TELEGRAM_START_INTRO_PROMPT_NAME = "telegram_start_intro"
PENDING_PHOTO_STATUS_PROCESSING = "processing"
PENDING_PHOTO_STATUS_READY = "ready"


def _clear_transient_flags(context: ContextTypes.DEFAULT_TYPE):
    for key in TRANSIENT_FLAGS:
        context.user_data.pop(key, None)


def _reserve_pending_photo_context(context: ContextTypes.DEFAULT_TYPE, *, chat_id: int | None) -> dict:
    pending = context.user_data.get("pending_photo") or {}
    pending["chat_id"] = chat_id
    pending["status"] = PENDING_PHOTO_STATUS_PROCESSING
    pending.setdefault("uploaded_file_id", None)
    context.user_data["pending_photo"] = pending
    return pending


def _finalize_pending_photo_context(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    file_path: str,
    image_b64: str,
    uploaded_file_id: int,
) -> dict:
    pending = context.user_data.get("pending_photo") or {}
    pending.update(
        {
            "file_path": file_path,
            "image_b64": image_b64,
            "uploaded_file_id": uploaded_file_id,
            "status": PENDING_PHOTO_STATUS_READY,
        }
    )
    context.user_data["pending_photo"] = pending
    return pending


def _consume_ready_pending_photo_context(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    pending = context.user_data.get("pending_photo")
    if not isinstance(pending, dict):
        return None

    status = pending.get("status")
    is_ready = bool(pending.get("uploaded_file_id")) and status != PENDING_PHOTO_STATUS_PROCESSING
    if not is_ready:
        return None

    context.user_data.pop("pending_photo", None)
    return pending


def _clear_pending_inputs(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_file", None)
    context.user_data.pop("pending_photo", None)
    context.user_data.pop("pending_toman_topup_quote", None)
    context.user_data.pop("pending_card_amount_toman", None)


def _reset_ephemeral_state(context: ContextTypes.DEFAULT_TYPE, clear_pending: bool = False):
    _clear_transient_flags(context)
    if clear_pending:
        _clear_pending_inputs(context)


def _begin_mode(context: ContextTypes.DEFAULT_TYPE, mode: str):
    _reset_ephemeral_state(context, clear_pending=True)
    context.user_data[mode] = True


def _is_navigation_or_command(text: str | None) -> bool:
    if not text:
        return False
    normalized = text.strip()
    return normalized in NAVIGATION_TEXTS or normalized.startswith("/")


def _user_can_access_chat(user: UserPreference, chat: Chat) -> bool:
    if user.is_admin:
        return True
    return getattr(chat, "user_preference_id", None) == user.id


def _retry_upload_callback_data(project_id: int, filename: str) -> str:
    callback_data = f"retry_upload_{project_id}_{filename}"
    if len(callback_data.encode("utf-8")) <= 64:
        return callback_data
    return f"retry_upload_{project_id}"


def _is_group_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type in GROUP_ALLOWED_CHAT_TYPES)


async def _is_reply_to_this_bot(context: ContextTypes.DEFAULT_TYPE, message) -> bool:
    reply_to = getattr(message, "reply_to_message", None)
    if not reply_to:
        return False
    sender = getattr(reply_to, "from_user", None)
    if not sender or not getattr(sender, "is_bot", False):
        return False

    bot_id = getattr(context.bot, "id", None)
    if not bot_id:
        try:
            me = await context.bot.get_me()
            bot_id = me.id
        except Exception:
            return False
    return int(getattr(sender, "id", 0) or 0) == int(bot_id)

# ─── KEYBOARDS ───
def main_kb(is_admin: bool) -> ReplyKeyboardMarkup:
    buttons = [
        ["💎 اشتراک‌ها", "💰 افزایش شارژ"],
        ["👤 حساب کاربری"],
        ["🎁 دعوت دوستان"],
        ["🚀 باز کردن دکتر بز"],
        ["🔑 ورود به وب"],
        ["📞 پشتیبانی"],
    ]
    if is_admin:
        buttons.append(["🔧 مدیریت"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

ADMIN_KB = ReplyKeyboardMarkup([
    ["👥 یوزرها", "📋 درخواست‌های پرداخت"],
    ["🔙 منوی اصلی"],
], resize_keyboard=True)


def _chunk_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < int(limit * 0.5):
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


async def _safe_callback_edit(query, text: str, reply_markup=None):
    chunks = _chunk_text(text)
    try:
        await query.message.edit_text(chunks[0], reply_markup=reply_markup)
    except Exception:
        await query.message.reply_text(chunks[0], reply_markup=reply_markup)
    for chunk in chunks[1:]:
        await query.message.reply_text(chunk)


def _tool_scope_label(scope_type: str, scope_id: int | None) -> str:
    if scope_type == "global":
        return "سراسری"
    if scope_type == "project":
        return f"پروژه #{scope_id}" if scope_id is not None else "پروژه"
    if scope_type == "chat":
        return f"چت #{scope_id}" if scope_id is not None else "چت"
    return f"{scope_type}:{scope_id}" if scope_id is not None else scope_type


def _tool_call_status_icon(status: str | None) -> str:
    if status == "completed":
        return "✅"
    if status == "failed":
        return "❌"
    if status == "pending":
        return "⏳"
    return "⚪️"


async def _tool_summary_counts(db: AsyncSession) -> dict[str, int]:
    total_tools = (await db.execute(select(func.count(Tool.id)))).scalar() or 0
    active_tools = (await db.execute(select(func.count(Tool.id)).where(Tool.is_active == True))).scalar() or 0
    enabled_bindings = (await db.execute(select(func.count(ToolBinding.id)).where(ToolBinding.is_enabled == True))).scalar() or 0
    total_calls = (await db.execute(select(func.count(ToolCall.id)))).scalar() or 0
    failed_calls = (await db.execute(select(func.count(ToolCall.id)).where(ToolCall.status == "failed"))).scalar() or 0
    pending_calls = (await db.execute(select(func.count(ToolCall.id)).where(ToolCall.status == "pending"))).scalar() or 0
    return {
        "total_tools": int(total_tools),
        "active_tools": int(active_tools),
        "enabled_bindings": int(enabled_bindings),
        "total_calls": int(total_calls),
        "failed_calls": int(failed_calls),
        "pending_calls": int(pending_calls),
    }


def _tools_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📌 خلاصه", callback_data="tools_summary"),
            InlineKeyboardButton("📊 گزارش کامل", callback_data="tools_report"),
        ],
        [
            InlineKeyboardButton("🔗 بایندینگ‌ها", callback_data="tools_bindings"),
            InlineKeyboardButton("🔁 همگام‌سازی builtin", callback_data="tools_sync_builtin"),
        ],
        [
            InlineKeyboardButton("➕ ابزار جدید", callback_data="tools_add_start"),
            InlineKeyboardButton("➕ بایندینگ", callback_data="tools_bind_new_start"),
        ],
        [
            InlineKeyboardButton("🗑 حذف ابزار", callback_data="tools_delete_tools"),
            InlineKeyboardButton("🗑 حذف بایندینگ", callback_data="tools_delete_bindings"),
        ],
    ])


def _validate_binding_scope(scope_type: str, scope_id: int | None) -> str | None:
    if scope_type not in {"global", "project", "chat"}:
        return "scope باید یکی از global / project / chat باشه"
    if scope_type == "global" and scope_id is not None:
        return "برای scope سراسری، scope_id باید خالی باشه"
    if scope_type in {"project", "chat"} and scope_id is None:
        return f"برای scope نوع {scope_type} باید شناسه بدی"
    return None


async def _resolve_tool_by_ref(db: AsyncSession, text: str) -> Tool | None:
    if text.isdigit():
        result = await db.execute(select(Tool).where(Tool.id == int(text)))
        tool = result.scalar_one_or_none()
        if tool:
            return tool
    result = await db.execute(select(Tool).where(Tool.name == text))
    return result.scalar_one_or_none()


async def _build_tool_picker_hint_text(db: AsyncSession) -> str:
    tools = (await db.execute(select(Tool).order_by(Tool.is_active.desc(), Tool.name).limit(20))).scalars().all()
    if not tools:
        return "ابزاری ثبت نشده. اول ابزار بساز."
    lines = ["🧰 ابزارهای موجود (شناسه یا نام بفرست):", ""]
    for tool in tools:
        status = "✅" if tool.is_active else "❌"
        lines.append(f"{status} #{tool.id} | {tool.name}")
    return "\n".join(lines)


async def _create_tool_binding_with_validation(
    db: AsyncSession,
    *,
    tool_id: int,
    scope_type: str,
    scope_id: int | None,
) -> tuple[ToolBinding | None, str | None]:
    scope_error = _validate_binding_scope(scope_type, scope_id)
    if scope_error:
        return None, scope_error

    tool_result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = tool_result.scalar_one_or_none()
    if not tool:
        return None, "ابزار پیدا نشد"

    if scope_type == "project" and scope_id is not None:
        project_result = await db.execute(select(Project.id).where(Project.id == scope_id))
        if project_result.scalar_one_or_none() is None:
            return None, "پروژه پیدا نشد"

    if scope_type == "chat" and scope_id is not None:
        chat_result = await db.execute(select(Chat.id).where(Chat.id == scope_id))
        if chat_result.scalar_one_or_none() is None:
            return None, "چت پیدا نشد"

    existing = (
        await db.execute(
            select(ToolBinding).where(
                ToolBinding.tool_id == tool_id,
                ToolBinding.scope_type == scope_type,
                ToolBinding.scope_id == scope_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, "exists"

    binding = ToolBinding(tool_id=tool_id, scope_type=scope_type, scope_id=scope_id, is_enabled=True)
    db.add(binding)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(ToolBinding).where(
                    ToolBinding.tool_id == tool_id,
                    ToolBinding.scope_type == scope_type,
                    ToolBinding.scope_id == scope_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing, "exists"
        return None, "ثبت بایندینگ انجام نشد"
    await db.refresh(binding)
    return binding, None


async def _build_custom_tools_delete_text_and_kb(db: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    tools = (await db.execute(select(Tool).where(Tool.is_builtin == False).order_by(Tool.name))).scalars().all()
    lines = ["🗑 حذف ابزار سفارشی", ""]
    buttons: list[list[InlineKeyboardButton]] = []
    if not tools:
        lines.append("ابزار سفارشی‌ای برای حذف وجود نداره.")
    else:
        for tool in tools[:40]:
            name = (tool.display_name or tool.name or "?")[:28]
            lines.append(f"#{tool.id} | {tool.name}")
            buttons.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"tools_deltool_{tool.id}")])
        if len(tools) > 40:
            lines.append(f"... +{len(tools) - 40} ابزار دیگر")

    buttons.append([InlineKeyboardButton("🔄 تازه‌سازی", callback_data="tools_delete_tools")])
    buttons.append([InlineKeyboardButton("🔙 منوی ابزارها", callback_data="tools_summary")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _build_bindings_delete_text_and_kb(db: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    rows = (
        await db.execute(
            select(
                ToolBinding.id,
                ToolBinding.scope_type,
                ToolBinding.scope_id,
                ToolBinding.is_enabled,
                Tool.display_name,
                Tool.name,
            )
            .join(Tool, Tool.id == ToolBinding.tool_id)
            .order_by(ToolBinding.id.desc())
            .limit(50)
        )
    ).all()

    lines = ["🗑 حذف بایندینگ", ""]
    buttons: list[list[InlineKeyboardButton]] = []
    if not rows:
        lines.append("بایندینگی ثبت نشده.")
    else:
        for binding_id, scope_type, scope_id, is_enabled, display_name, name in rows:
            scope_label = _tool_scope_label(scope_type, scope_id)
            status = "✅" if is_enabled else "❌"
            tool_name = (display_name or name or "?")[:26]
            lines.append(f"#{binding_id} | {tool_name} | {scope_label} | {status}")
            buttons.append([InlineKeyboardButton(f"🗑 #{binding_id} {tool_name}", callback_data=f"tools_delbind_{binding_id}")])

    buttons.append([InlineKeyboardButton("🔄 تازه‌سازی", callback_data="tools_delete_bindings")])
    buttons.append([InlineKeyboardButton("🔙 منوی ابزارها", callback_data="tools_summary")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _build_tools_summary_text(db: AsyncSession) -> str:
    counts = await _tool_summary_counts(db)
    return (
        "🧰 مدیریت ابزارها\n\n"
        f"کل ابزارها: {counts['total_tools']}\n"
        f"ابزار فعال: {counts['active_tools']}\n"
        f"بایندینگ فعال: {counts['enabled_bindings']}\n"
        f"کل فراخوانی: {counts['total_calls']}\n"
        f"فراخوانی ناموفق: {counts['failed_calls']}\n"
        f"فراخوانی در انتظار: {counts['pending_calls']}"
    )


async def _build_tools_report_text(db: AsyncSession) -> str:
    counts = await _tool_summary_counts(db)
    tools = (await db.execute(select(Tool).order_by(Tool.is_active.desc(), Tool.name))).scalars().all()

    binding_rows = await db.execute(
        select(
            ToolBinding.tool_id,
            func.count(ToolBinding.id),
            func.sum(case((ToolBinding.is_enabled == True, 1), else_=0)),
        ).group_by(ToolBinding.tool_id)
    )
    binding_stats = {
        row[0]: {"total": int(row[1] or 0), "enabled": int(row[2] or 0)}
        for row in binding_rows.all()
    }

    call_rows = await db.execute(
        select(
            ToolCall.tool_id,
            func.count(ToolCall.id),
            func.sum(case((ToolCall.status == "failed", 1), else_=0)),
            func.sum(case((ToolCall.status == "pending", 1), else_=0)),
        ).group_by(ToolCall.tool_id)
    )
    call_stats = {
        row[0]: {"total": int(row[1] or 0), "failed": int(row[2] or 0), "pending": int(row[3] or 0)}
        for row in call_rows.all()
    }

    recent_calls = (
        await db.execute(
            select(
                ToolCall.id,
                Tool.name,
                ToolCall.status,
                ToolCall.chat_id,
                ToolCall.created_at,
            )
            .join(Tool, Tool.id == ToolCall.tool_id)
            .order_by(ToolCall.created_at.desc())
            .limit(12)
        )
    ).all()

    lines = [
        "📊 گزارش ابزارها",
        "",
        f"ابزارها: {counts['total_tools']} | فعال: {counts['active_tools']} | بایندینگ فعال: {counts['enabled_bindings']}",
        f"فراخوانی: {counts['total_calls']} | ناموفق: {counts['failed_calls']} | در انتظار: {counts['pending_calls']}",
        "",
        "🛠 لیست ابزارها:",
    ]
    for idx, tool in enumerate(tools[:25], start=1):
        b_stat = binding_stats.get(tool.id, {"total": 0, "enabled": 0})
        c_stat = call_stats.get(tool.id, {"total": 0, "failed": 0, "pending": 0})
        name = (tool.display_name or tool.name or "?")[:40]
        status = "✅" if tool.is_active else "❌"
        lines.append(
            f"{idx}. {status} {name} | B:{b_stat['enabled']}/{b_stat['total']} | C:{c_stat['total']} F:{c_stat['failed']} P:{c_stat['pending']}"
        )
    if len(tools) > 25:
        lines.append(f"... +{len(tools) - 25} ابزار دیگر")

    lines.append("")
    lines.append("🕘 فراخوانی‌های اخیر:")
    if not recent_calls:
        lines.append("موردی ثبت نشده")
    else:
        for call_id, tool_name, status, chat_id, created_at in recent_calls:
            stamp = format_persian(created_at, "%m/%d %H:%M") if created_at else "?"
            lines.append(
                f"#{call_id} {_tool_call_status_icon(status)} {tool_name} | چت:{chat_id or '-'} | {stamp}"
            )
    return "\n".join(lines)


async def _build_tools_index_text_and_kb(db: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    tools = (await db.execute(select(Tool).order_by(Tool.is_active.desc(), Tool.name))).scalars().all()
    binding_rows = await db.execute(
        select(
            ToolBinding.tool_id,
            func.count(ToolBinding.id),
            func.sum(case((ToolBinding.is_enabled == True, 1), else_=0)),
        ).group_by(ToolBinding.tool_id)
    )
    binding_stats = {
        row[0]: {"total": int(row[1] or 0), "enabled": int(row[2] or 0)}
        for row in binding_rows.all()
    }

    lines = ["🔗 بایندینگ‌ها (بر اساس ابزار)", ""]
    buttons: list[list[InlineKeyboardButton]] = []
    if not tools:
        lines.append("ابزاری ثبت نشده")
    else:
        for tool in tools[:30]:
            stat = binding_stats.get(tool.id, {"total": 0, "enabled": 0})
            display = (tool.display_name or tool.name or "?")[:30]
            status = "✅" if tool.is_active else "❌"
            lines.append(f"{status} {display} | بایندینگ: {stat['enabled']}/{stat['total']}")
            buttons.append([InlineKeyboardButton(f"{display} ({stat['enabled']}/{stat['total']})", callback_data=f"tools_btool_{tool.id}")])
        if len(tools) > 30:
            lines.append(f"... +{len(tools) - 30} ابزار دیگر")

    buttons.append([InlineKeyboardButton("🔄 تازه‌سازی", callback_data="tools_bindings")])
    buttons.append([
        InlineKeyboardButton("📌 خلاصه", callback_data="tools_summary"),
        InlineKeyboardButton("📊 گزارش", callback_data="tools_report"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _build_tool_bindings_text_and_kb(db: AsyncSession, tool_id: int) -> tuple[str, InlineKeyboardMarkup]:
    tool = (await db.execute(select(Tool).where(Tool.id == tool_id))).scalar_one_or_none()
    if not tool:
        return (
            "❌ ابزار پیدا نشد",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 لیست ابزارها", callback_data="tools_bindings")]]),
        )

    bindings = (
        await db.execute(
            select(ToolBinding)
            .where(ToolBinding.tool_id == tool_id)
            .order_by(ToolBinding.scope_type, ToolBinding.scope_id, ToolBinding.id)
        )
    ).scalars().all()

    display_name = tool.display_name or tool.name
    status = "✅ فعال" if tool.is_active else "❌ غیرفعال"
    lines = [
        f"🧰 {display_name}",
        f"وضعیت ابزار: {status}",
        "",
        "🔗 بایندینگ‌ها:",
    ]
    buttons: list[list[InlineKeyboardButton]] = []
    if not bindings:
        lines.append("بایندینگی برای این ابزار ثبت نشده")
    else:
        for binding in bindings:
            b_status = "✅ فعال" if binding.is_enabled else "❌ غیرفعال"
            scope_label = _tool_scope_label(binding.scope_type, binding.scope_id)
            lines.append(f"#{binding.id} | {scope_label} | {b_status}")
            toggle_label = f"{'⏸ غیرفعال' if binding.is_enabled else '▶️ فعال'} #{binding.id}"
            buttons.append([
                InlineKeyboardButton(toggle_label, callback_data=f"tools_tog_{binding.id}_{tool_id}"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"tools_delbind_{binding.id}"),
            ])

    buttons.append([InlineKeyboardButton("➕ بایندینگ جدید", callback_data="tools_bind_new_start")])
    buttons.append([InlineKeyboardButton("🔄 تازه‌سازی", callback_data=f"tools_btool_{tool_id}")])
    buttons.append([InlineKeyboardButton("🔙 لیست ابزارها", callback_data="tools_bindings")])
    buttons.append([
        InlineKeyboardButton("📌 خلاصه", callback_data="tools_summary"),
        InlineKeyboardButton("📊 گزارش", callback_data="tools_report"),
    ])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _normalize_tool_guidance_style(style: str | None) -> str:
    normalized = (style or "").strip().lower()
    if normalized not in TOOL_GUIDANCE_STYLES:
        return DEFAULT_TOOL_GUIDANCE_STYLE
    return normalized


async def _get_or_create_default_system_prompt(db: AsyncSession) -> SystemPrompt:
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.name == "default"))
    prompt = result.scalar_one_or_none()
    if prompt:
        return prompt

    # Reuse backend default behavior to initialize the record if missing.
    await get_system_prompt(db)
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.name == "default"))
    prompt = result.scalar_one_or_none()
    if prompt:
        return prompt

    prompt = SystemPrompt(
        name="default",
        content="",
        is_active=True,
        auto_tool_guidance_enabled=True,
        tool_guidance_style=DEFAULT_TOOL_GUIDANCE_STYLE,
    )
    db.add(prompt)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(SystemPrompt).where(SystemPrompt.name == "default"))
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        raise
    await db.refresh(prompt)
    return prompt


async def _get_system_prompt_by_name(db: AsyncSession, name: str) -> SystemPrompt | None:
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.name == name))
    return result.scalar_one_or_none()


async def _get_telegram_start_intro_text(db: AsyncSession) -> str | None:
    prompt = await _get_system_prompt_by_name(db, TELEGRAM_START_INTRO_PROMPT_NAME)
    if not prompt or not prompt.is_active:
        return None
    text = (prompt.content or "").strip()
    return text or None


async def _upsert_telegram_start_intro_prompt(db: AsyncSession, text: str) -> None:
    cleaned_text = (text or "").strip()
    if not cleaned_text:
        raise ValueError("start intro text cannot be empty")

    prompt = await _get_system_prompt_by_name(db, TELEGRAM_START_INTRO_PROMPT_NAME)
    if prompt:
        prompt.content = cleaned_text
        prompt.is_active = True
    else:
        db.add(
            SystemPrompt(
                name=TELEGRAM_START_INTRO_PROMPT_NAME,
                content=cleaned_text,
                is_active=True,
                auto_tool_guidance_enabled=False,
                tool_guidance_style=DEFAULT_TOOL_GUIDANCE_STYLE,
            )
        )
    await db.commit()


async def _clear_telegram_start_intro_prompt(db: AsyncSession) -> None:
    prompt = await _get_system_prompt_by_name(db, TELEGRAM_START_INTRO_PROMPT_NAME)
    if not prompt:
        return
    prompt.content = ""
    prompt.is_active = False
    await db.commit()


async def _build_prompt_admin_text_and_kb(db: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    prompt = await _get_or_create_default_system_prompt(db)
    prompt_content = (prompt.content or "").strip() or await get_system_prompt(db)
    auto_enabled = True if prompt.auto_tool_guidance_enabled is None else bool(prompt.auto_tool_guidance_enabled)
    style = _normalize_tool_guidance_style(prompt.tool_guidance_style)
    template_set = bool((prompt.tool_guidance_template or "").strip())
    start_intro = await _get_telegram_start_intro_text(db)
    if start_intro and len(start_intro) > 220:
        start_intro_preview = start_intro[:220].rstrip() + "..."
    else:
        start_intro_preview = start_intro or "تنظیم نشده"

    text = (
        f"📝 سیستم پرامپت:\n\n{prompt_content}\n\n"
        "🎬 پیام معرفی /start:\n"
        f"وضعیت: {'✅ فعال' if start_intro else '❌ خاموش'}\n"
        f"پیش‌نمایش: {start_intro_preview}\n\n"
        "⚙️ تنظیمات راهنمای پویا ابزار:\n"
        f"راهنمای خودکار: {'✅ روشن' if auto_enabled else '❌ خاموش'}\n"
        f"سبک: {style}\n"
        f"قالب سفارشی: {'✅ ست شده' if template_set else '❌ تنظیم نشده'}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ ویرایش پرامپت", callback_data="edit_prompt")],
        [
            InlineKeyboardButton("✏️ ویرایش پیام /start", callback_data="edit_start_intro"),
            InlineKeyboardButton("♻️ حذف پیام /start", callback_data="clear_start_intro"),
        ],
        [InlineKeyboardButton(
            "⏸ خاموش کردن راهنمای خودکار" if auto_enabled else "▶️ روشن کردن راهنمای خودکار",
            callback_data="prompt_toggle_auto",
        )],
        [
            InlineKeyboardButton(
                f"{'✅ ' if style == 'compact' else ''}compact",
                callback_data="prompt_style_compact",
            ),
            InlineKeyboardButton(
                f"{'✅ ' if style == 'detailed' else ''}detailed",
                callback_data="prompt_style_detailed",
            ),
        ],
        [
            InlineKeyboardButton("✏️ تنظیم قالب راهنما", callback_data="prompt_set_template"),
            InlineKeyboardButton("♻️ حذف قالب", callback_data="prompt_reset_template"),
        ],
        [InlineKeyboardButton("🔄 تازه‌سازی", callback_data="prompt_refresh")],
    ])
    return text, keyboard


# ─── DB-backed user state ───
async def get_user(db: AsyncSession, uid: int, first_name: str = None, username: str = None) -> UserPreference:
    # Refresh global feature toggle cache
    await _is_sub_feature_enabled(db)
    
    result = await db.execute(select(UserPreference).where(UserPreference.telegram_user_id == uid))
    user = result.scalars().first()
    if not user:
        user = UserPreference(
            telegram_user_id=uid,
            is_admin=(uid == ADMIN_ID),
            first_name=first_name,
            username=username,
            account_status="active",
        )
        db.add(user)
        await db.flush() # Ensure user.id is populated
        await apply_starter_credit(db, user)
        await db.commit()
        await db.refresh(user)
    else:
        changed = False
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if username and user.username != username:
            user.username = username
            changed = True
        if not user.is_admin:
            if _user_onboarding_completed(user):
                if user.account_status != "active":
                    user.account_status = "active"
                    changed = True
            else:
                previous_status = user.account_status
                _mark_onboarding_pending(user)
                if user.account_status != previous_status:
                    changed = True
        if changed:
            await db.commit()
            await db.refresh(user)
    return user

async def save_user(db: AsyncSession, uid: int, **kwargs):
    user = await get_user(db, uid)
    for k, v in kwargs.items():
        setattr(user, k, v)
    if not user.is_admin:
        if _user_onboarding_completed(user):
            _mark_onboarding_complete(user)
        else:
            _mark_onboarding_pending(user)
    await db.commit()
    await db.refresh(user)


async def _get_accessible_current_project(db: AsyncSession, user: UserPreference) -> Project | None:
    if not user.current_project_id:
        return None
    project = await user_can_access_project(db, user, int(user.current_project_id))
    if project:
        return project
    user.current_project_id = None
    await db.commit()
    await db.refresh(user)
    return None
    return user


async def _get_active_provider_models(
    db: AsyncSession,
    *,
    provider_id: int | None = None,
) -> list[tuple[Provider, DBModel]]:
    query = (
        select(Provider, DBModel)
        .join(DBModel, DBModel.provider_id == Provider.id)
        .where(Provider.is_active == True, DBModel.is_active == True)
        .order_by(Provider.name, DBModel.display_name, DBModel.name)
    )
    if provider_id is not None:
        query = query.where(Provider.id == provider_id)
    result = await db.execute(query)
    return result.all()


async def get_provider_picker_buttons(db: AsyncSession, current_provider_id: int | None = None) -> InlineKeyboardMarkup:
    rows = await _get_active_provider_models(db)
    seen_provider_ids: set[int] = set()
    buttons: list[list[InlineKeyboardButton]] = []
    for provider, _ in rows:
        if provider.id in seen_provider_ids:
            continue
        seen_provider_ids.add(provider.id)
        check = "✅ " if provider.id == current_provider_id else ""
        buttons.append([InlineKeyboardButton(f"{check}{provider.name}", callback_data=f"mprov_{provider.id}")])
    return InlineKeyboardMarkup(buttons)


async def get_model_picker_buttons(
    db: AsyncSession,
    provider_id: int,
    current_model_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows = await _get_active_provider_models(db, provider_id=provider_id)
    buttons: list[list[InlineKeyboardButton]] = []
    for _, model in rows:
        check = "✅ " if model.id == current_model_id else ""
        label = f"{check}{model.display_name or model.name}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"model_{model.id}")])
    buttons.append([InlineKeyboardButton("🔙 پروایدرها", callback_data="mprov_back")])
    return InlineKeyboardMarkup(buttons)


async def _build_vision_model_suggestion_keyboard(
    db: AsyncSession,
    *,
    exclude_model_id: int | None = None,
    limit: int = 4,
) -> tuple[InlineKeyboardMarkup | None, list[dict]]:
    suggestions = await suggest_models_for_input_capability(
        db,
        need_image_input=True,
        exclude_model_id=exclude_model_id,
        limit=limit,
    )
    if not suggestions:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🤖 انتخاب مدل", callback_data="mprov_back")]]
        )
        return kb, []

    buttons: list[list[InlineKeyboardButton]] = []
    for item in suggestions:
        label = f"{item['provider_name']} / {item['display_name']}"
        buttons.append([InlineKeyboardButton(label[:60], callback_data=f"model_{item['id']}")])
    buttons.append([InlineKeyboardButton("🔎 لیست کامل مدل‌ها", callback_data="mprov_back")])
    return InlineKeyboardMarkup(buttons), suggestions


async def _send_image_capability_error(
    update: Update,
    db: AsyncSession,
    *,
    model: DBModel,
    message_obj=None,
):
    kb, suggestions = await _build_vision_model_suggestion_keyboard(
        db,
        exclude_model_id=model.id,
        limit=4,
    )
    model_label = model.display_name or model.name
    if suggestions:
        text = (
            f"⚠️ مدل «{model_label}» از ورودی تصویر پشتیبانی نمی‌کند.\n"
            "برای ادامه، یکی از مدل‌های پیشنهادی را انتخاب کن."
        )
    else:
        text = (
            f"⚠️ مدل «{model_label}» از ورودی تصویر پشتیبانی نمی‌کند.\n"
            "مدل پیشنهادی فعالی پیدا نشد. در پنل ادمین، یک مدل vision را فعال کن "
            "و capability آن را روی image_input=true بگذار."
        )
    if message_obj is not None:
        try:
            await message_obj.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await update.message.reply_text(text, reply_markup=kb)


async def _send_subscription_required_error(
    update: Update,
    db: AsyncSession,
    *,
    message_obj=None,
):
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from app.services.toman_billing_service import get_or_create_subscription_config

    plans = await _get_active_subscription_plans(db)
    if plans:
        config = await get_or_create_subscription_config(db)
        keyboard = []
        for p in plans:
            _plan_price = getattr(p, "monthly_price_toman", None)
            price_toman = int(_plan_price) if _plan_price is not None else int(config.monthly_price_toman or 0)
            keyboard.append([InlineKeyboardButton(f"خرید {p.name} ({_format_toman(price_toman)})", callback_data=f"buy_plan_{p.id}")])
        markup = InlineKeyboardMarkup(keyboard)
        text = (
            "❌ برای استفاده از این مدل، نیاز به اشتراک فعال دارید.\n"
            "برای خرید اشتراک، یکی از پلن‌های زیر را انتخاب کنید:"
        )
    else:
        markup = None
        text = "❌ برای استفاده از این مدل، نیاز به اشتراک فعال دارید. لطفاً با پشتیبانی تماس بگیرید."

    if message_obj is not None:
        try:
            await message_obj.edit_text(text, reply_markup=markup)
            return
        except Exception:
            pass
    await update.message.reply_text(text, reply_markup=markup)


async def _send_group_setup_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    group_id: int,
    group_title: str | None,
):
    chat = update.effective_chat
    if not chat:
        return
    deep_link = await _build_group_optin_deep_link(context, group_id)
    title = (group_title or str(chat.id)).strip()
    if deep_link:
        setup_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("فعال‌سازی پرداخت سهمی در خصوصی", url=deep_link)]]
        )
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"👥 حالت گروهی برای «{title}» فعال شد.\n"
                "برای استفاده گروهی، هر عضو باید در PV بات پرداخت سهمی را فعال کند."
            ),
            reply_markup=setup_kb,
        )
        return
    await context.bot.send_message(
        chat_id=chat.id,
        text=(
            f"👥 حالت گروهی برای «{title}» فعال شد.\n"
            "برای فعال‌سازی پرداخت سهمی، در PV بات این دستور را بزن:\n"
            f"/start {GROUP_OPTIN_START_PREFIX}{group_id}"
        ),
    )


async def handle_group_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat or chat.type not in GROUP_ALLOWED_CHAT_TYPES:
        return
    new_members = message.new_chat_members or []
    if not new_members:
        return
    if not await _claim_update_once(update):
        return
    bot_me = await context.bot.get_me()
    if not any(member.id == bot_me.id for member in new_members):
        return
    async with async_session() as db:
        actor = None
        if update.effective_user:
            actor = await get_user(
                db,
                update.effective_user.id,
                update.effective_user.first_name or "",
                update.effective_user.username or "",
            )
        group_row, _ = await _ensure_telegram_group_record(
            db,
            telegram_chat_id=chat.id,
            title=getattr(chat, "title", None),
            chat_type=chat.type,
            created_by_user_id=actor.id if actor else None,
        )
        await db.commit()
    # The my_chat_member update is the canonical setup announcer. Telegram can
    # also send new_chat_members for the same join, so this path only syncs DB.


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member_update = update.my_chat_member
    chat = update.effective_chat
    if not member_update or not chat or chat.type not in GROUP_ALLOWED_CHAT_TYPES:
        return
    if not await _claim_update_once(update):
        return
    old_status = (member_update.old_chat_member.status or "").lower()
    new_status = (member_update.new_chat_member.status or "").lower()
    became_member = old_status in {"left", "kicked"} and new_status in {"member", "administrator"}
    left_group = new_status in {"left", "kicked"}

    async with async_session() as db:
        actor = None
        if update.effective_user:
            actor = await get_user(
                db,
                update.effective_user.id,
                update.effective_user.first_name or "",
                update.effective_user.username or "",
            )
        group_row, _ = await _ensure_telegram_group_record(
            db,
            telegram_chat_id=chat.id,
            title=getattr(chat, "title", None),
            chat_type=chat.type,
            created_by_user_id=actor.id if actor else None,
        )
        if left_group:
            await _set_telegram_group_status(db, group_row["id"], "inactive")
        elif became_member:
            await _set_telegram_group_status(db, group_row["id"], "active")
        await db.commit()

    if became_member:
        await _send_group_setup_message(
            update,
            context,
            group_id=group_row["id"],
            group_title=group_row.get("title"),
        )


async def _show_group_optin_panel(
    update: Update,
    *,
    db: AsyncSession,
    user: UserPreference,
    group_id: int,
):
    panel_text, panel_kb = await _build_group_optin_panel_text(db, group_id=group_id, user_id=user.id)
    await update.message.reply_text(panel_text, reply_markup=panel_kb)


async def _run_group_tool_aware_completion(
    update: Update,
    db: AsyncSession,
    *,
    group_row: dict,
    trigger_user: UserPreference,
    payer_members: list[UserPreference],
    user_message: Message,
    chat: Chat,
    provider,
    model,
    llm_messages: list[dict],
    estimated_cost_usd: float,
    estimated_shares_minor: list[int],
    status_message_obj=None,
) -> str:
    estimated_total_minor = _usd_to_minor(estimated_cost_usd)
    usage_event = await _create_usage_event(
        db,
        user=trigger_user,
        chat_id=chat.id,
        message_id=user_message.id,
        operation_type="chat_completion_group",
        uploaded_file_id=None,
        provider_name=provider.name,
        provider_id=getattr(provider, "id", None),
        model=model,
        estimated_cost_usd=estimated_cost_usd,
        request_id=f"telegram:{update.update_id}:group-chat:{group_row['id']}:{user_message.id}",
        metadata={
            "group_id": group_row["id"],
            "telegram_chat_id": group_row["telegram_chat_id"],
            "payer_user_ids": [member.id for member in payer_members],
        },
    )
    usage_event.status = "authorized"
    await db.flush()

    group_usage_event_id = await _create_group_usage_event_row(
        db,
        group_id=group_row["id"],
        usage_event_id=usage_event.id,
        request_id=f"telegram:{update.update_id}:group-usage:{group_row['id']}:{user_message.id}",
        chat_id=group_row["telegram_chat_id"],
        message_id=user_message.id,
        telegram_message_id=update.message.message_id if update.message else None,
        triggered_by_user_id=trigger_user.id,
        provider_id=getattr(provider, "id", None),
        provider_name=provider.name,
        model_id=model.id,
        model_name=model.name,
        estimated_cost_minor=estimated_total_minor,
        split_member_count=len(payer_members),
        metadata={"trigger_text": update.message.text if update.message else ""},
    )

    for member, estimated_share_minor in zip(payer_members, estimated_shares_minor):
        await _upsert_group_usage_share_estimate(
            db,
            group_usage_event_id=group_usage_event_id,
            user_id=member.id,
            estimated_share_minor=estimated_share_minor,
        )
    await db.commit()

    sent_msg = status_message_obj
    if sent_msg is None:
        sent_msg = await update.message.reply_text("⏳")

    from app.group_agent_logic import _run_agent_for_group
    full_reply = await _run_agent_for_group(
        update,
        db,
        trigger_user=trigger_user,
        payer_members=payer_members,
        chat=chat,
        provider=provider,
        model=model,
        llm_messages=llm_messages,
        group_usage_event_id=group_usage_event_id,
        usage_event=usage_event,
        status_message_obj=sent_msg,
    )
    return full_reply



async def _process_group_text_turn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.message
    if not chat or not message or chat.type not in GROUP_ALLOWED_CHAT_TYPES:
        return
    raw_text = (message.text or "").strip()
    if not raw_text:
        return
    uid = update.effective_user.id if update.effective_user else 0
    async with async_session() as db:
        trigger_user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        group_row, _ = await _ensure_telegram_group_record(
            db,
            telegram_chat_id=chat.id,
            title=getattr(chat, "title", None),
            chat_type=chat.type,
            created_by_user_id=trigger_user.id,
        )
        await db.commit()

        if (group_row.get("status") or "active") != "active":
            return

        trigger_phrase, question = detect_group_trigger(raw_text, group_row.get("trigger_phrases") or [])
        reply_to_bot = await _is_reply_to_this_bot(context, message)
        if not trigger_phrase and not reply_to_bot:
            return
        if not question and reply_to_bot:
            question = raw_text
        if not question:
            await message.reply_text("سوالت رو بعد از تریگر بنویس؛ مثال: هی دکتر بز هزینه این چقدره؟")
            return
        if not _user_onboarding_completed(trigger_user):
            await message.reply_text("برای استفاده از حالت گروهی اول در PV بات ثبت‌نامت رو کامل کن: /start")
            return

        payer_members = await _list_active_group_payers(db, group_row["id"])
        min_active_members = max(1, int(group_row.get("min_active_members") or GROUP_MIN_ACTIVE_MEMBERS_DEFAULT))
        if trigger_user.id not in {member.id for member in payer_members}:
            await message.reply_text(
                "برای پرسیدن سوال در حالت پرداخت سهمی، اول باید پرداخت سهمی خودت را در PV بات فعال کنی.\n"
                f"در PV بات بفرست: /start {GROUP_OPTIN_START_PREFIX}{group_row['id']}"
            )
            return
        if len(payer_members) < min_active_members:
            await message.reply_text(
                "پرداخت سهمی آماده نیست.\n"
                f"حداقل اعضای فعال لازم: {min_active_members}\n"
                f"اعضای فعال فعلی: {len(payer_members)}"
            )
            return

        non_ready_members = [member for member in payer_members if not _user_onboarding_completed(member)]
        if non_ready_members:
            await message.reply_text("پرداخت سهمی آماده نیست؛ یکی از اعضای فعال وضعیت حساب کامل ندارد.")
            return

        selected_model_id = trigger_user.current_model_id
        if selected_model_id:
            provider, model = await get_provider_for_model(db, selected_model_id)
            if not model:
                provider, model = await get_default_model(db)
        else:
            provider, model = await get_default_model(db)
        if not model:
            await message.reply_text("مدل فعالی برای پاسخ‌گویی تنظیم نشده.")
            return

        group_chat = await _ensure_group_chat(db, group_row, model.id)
        user_msg = Message(chat_id=group_chat.id, role="user", content=question)
        db.add(user_msg)
        await db.commit()
        await db.refresh(user_msg)

        all_messages = (
            await db.execute(select(Message).where(Message.chat_id == group_chat.id).order_by(Message.created_at))
        ).scalars().all()
        llm_messages = [{"role": item.role, "content": item.content} for item in all_messages]

        system_content = await get_effective_system_prompt(db, chat=group_chat, user=trigger_user, include_tool_guidance=False)
        trigger_user_name = trigger_user.preferred_name or trigger_user.first_name or str(uid)
        system_content = (
            f"{system_content}\n\n"
            "This is a Telegram group conversation.\n"
            f"The triggering user is: {trigger_user_name}."
        )
        if group_chat.project_id:
            emb = await _get_emb_config(db)
            docs = await _search_with_config(group_chat.project_id, question, emb_config=emb, n_results=5)
            if docs:
                ctx = "\n\n---\n\n".join([d["content"] for d in docs])
                system_content += f"\n\nRelevant documents context:\n{ctx}"
        llm_messages.insert(0, {"role": "system", "content": system_content})

        provider, model, routing = await resolve_model_for_completion(
            db,
            selected_provider=provider,
            selected_model=model,
            messages=llm_messages,
        )
        if not provider or not model:
            await message.reply_text("مدل اجرایی فعالی برای Auto Routing تنظیم نشده.")
            return

        estimated_in_tokens = _estimate_messages_tokens(llm_messages)
        estimated_cost_usd = _calculate_standard_cost_usd(model, estimated_in_tokens, CHAT_OUTPUT_TOKEN_ESTIMATE)
        estimated_total_minor = _usd_to_minor(estimated_cost_usd)
        precheck = await estimate_split_and_strict_precheck(
            db,
            group_id=int(group_row["id"]),
            estimated_cost_minor=estimated_total_minor,
            remainder_user_id=trigger_user.id,
        )
        estimated_shares_minor = [int(precheck.shares_minor.get(member.id, 0)) for member in payer_members]
        if not precheck.ok:
            await message.reply_text(
                "پرداخت سهمی آماده نیست؛ حداقل موجودی یکی از اعضای فعال کافی نیست.\n"
                "لطفاً اعضای فعال گروه را شارژ کنید."
            )
            return

        full_reply = await _run_group_tool_aware_completion(
            update,
            db,
            group_row=group_row,
            trigger_user=trigger_user,
            payer_members=payer_members,
            user_message=user_msg,
            chat=group_chat,
            provider=provider,
            model=model,
            llm_messages=llm_messages,
            estimated_cost_usd=estimated_cost_usd,
            estimated_shares_minor=estimated_shares_minor,
            status_message_obj=None,
        )
        if not full_reply:
            return
        db.add(Message(chat_id=group_chat.id, role="assistant", content=full_reply))
        await db.commit()


async def cmd_group_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in GROUP_ALLOWED_CHAT_TYPES:
        await update.message.reply_text("این دستور فقط داخل گروه قابل استفاده است.")
        return
    uid = update.effective_user.id if update.effective_user else 0
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        group_row, _ = await _ensure_telegram_group_record(
            db,
            telegram_chat_id=chat.id,
            title=getattr(chat, "title", None),
            chat_type=chat.type,
            created_by_user_id=user.id,
        )
        member_state = await _get_group_member_state(db, int(group_row["id"]), int(user.id))
        if not user.is_admin and not (member_state and member_state.get("shared_billing_enabled") and member_state.get("status") == "active"):
            await update.message.reply_text("گزارش پرداخت گروهی فقط برای اعضای پرداخت‌کننده فعال در دسترسه.")
            return
        total_usage_count = (
            await db.execute(
                text("SELECT COUNT(*) FROM group_usage_events WHERE group_id = :group_id"),
                {"group_id": int(group_row["id"])},
            )
        ).scalar() or 0
        total_cost_minor = (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(SUM(actual_cost_minor), 0)
                    FROM group_usage_events
                    WHERE group_id = :group_id AND status IN ('completed', 'billing_failed')
                    """
                ),
                {"group_id": int(group_row["id"])},
            )
        ).scalar() or 0
        active_member_count = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM telegram_group_members
                    WHERE group_id = :group_id AND status = 'active' AND shared_billing_enabled = 1
                    """
                ),
                {"group_id": int(group_row["id"])},
            )
        ).scalar() or 0
        my_share_minor = (
            await db.execute(
                text(
                    """
                    SELECT COALESCE(SUM(gs.actual_share_minor), 0)
                    FROM group_usage_shares gs
                    JOIN group_usage_events ge ON ge.id = gs.group_usage_event_id
                    WHERE ge.group_id = :group_id AND gs.user_id = :user_id
                    """
                ),
                {"group_id": int(group_row["id"]), "user_id": int(user.id)},
            )
        ).scalar() or 0
        recent_rows = (
            await db.execute(
                text(
                    """
                    SELECT created_at, actual_cost_minor, split_member_count, status
                    FROM group_usage_events
                    WHERE group_id = :group_id
                    ORDER BY id DESC
                    LIMIT 5
                    """
                ),
                {"group_id": int(group_row["id"])},
            )
        ).all()

    lines = [
        f"📊 گزارش گروه: {group_row.get('title') or chat.id}",
        "",
        f"درخواست‌های ثبت‌شده: {int(total_usage_count)}",
        f"هزینه کل گروه: ${_minor_to_usd(int(total_cost_minor)):.4f}",
        f"اعضای پرداخت‌کننده فعال: {int(active_member_count)}",
        f"سهم پرداختی شما: ${_minor_to_usd(int(my_share_minor)):.4f}",
        "",
        "آخرین رویدادها:",
    ]
    if not recent_rows:
        lines.append("موردی ثبت نشده.")
    else:
        for row in recent_rows:
            created_at = (row[0] or "")[:16].replace("T", " ")
            cost_usd = _minor_to_usd(int(row[1] or 0))
            split_count = int(row[2] or 0)
            status = str(row[3] or "-")
            lines.append(f"{created_at} | ${cost_usd:.4f} | اعضا:{split_count} | {status}")
    await update.message.reply_text("\n".join(lines))


# ══════════════════════════════════════
#  /start
# ══════════════════════════════════════

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _reset_ephemeral_state(context, clear_pending=True)
    uid = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else uid
    
    # Assertive stop: set flag immediately to ignore zombie messages
    STOP_REQUESTED[uid] = time.time()
    if chat_id != uid:
        STOP_REQUESTED[chat_id] = time.time()
    
    # Cancel tasks for both user and chat (handles PV and Groups)
    was_running = False
    
    for key in [uid, chat_id]:
        tasks = USER_AGENT_TASKS.get(key, set())
        for task in list(tasks):
            if not task.done():
                task.cancel()
                was_running = True
        USER_AGENT_TASKS.pop(key, None)
    
    if was_running:
        await update.message.reply_text("⏹ عملیات متوقف شد.")
    else:
        await update.message.reply_text("هیچ عملیاتی در حال اجرا نیست.")

async def cmd_exit_upload_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _reset_ephemeral_state(context, clear_pending=True)
    await update.message.reply_text("✅ از حالت آپلود خارج شدیم.", reply_markup=project_kb())


async def _apply_promotional_offer(update, db, context, user, link, click):
    from app.services.toman_billing_service import get_or_create_billing_account
    from datetime import timedelta

    try:
        if link.offer_type == "credit_grant":
            account = await get_or_create_billing_account(db, user)
            account.gift_balance_toman = int(account.gift_balance_toman or 0) + link.offer_value_toman
            account.total_gift_granted_toman = int(account.total_gift_granted_toman or 0) + link.offer_value_toman
            account.version = int(account.version or 0) + 1

            ledger = TomanLedgerEntry(
                user_id=user.id,
                billing_account_id=account.id,
                amount_toman=link.offer_value_toman,
                gift_delta_toman=link.offer_value_toman,
                paid_delta_toman=0,
                gift_balance_after_toman=account.gift_balance_toman,
                paid_balance_after_toman=account.paid_balance_toman,
                entry_type="promotional_link_credit",
                reason=f"اعتبار هدیه از لینک تبلیغاتی: {link.title}",
                metadata_json={"promotional_link_id": link.id, "link_code": link.code},
            )
            db.add(ledger)
            click.redemption_status = "redeemed"
            click.redeemed_at = _utcnow()
            await db.commit()
            await update.message.reply_text(
                f"🎉 تبریک! {_format_toman(link.offer_value_toman)} تومان اعتبار هدیه به حسابت اضافه شد.\n\n"
                f"از لینک: {link.title}"
            )

        elif link.offer_type == "free_subscription":
            if not link.plan_id:
                click.redemption_status = "failed"
                await db.commit()
                await update.message.reply_text("این لینک مشکل داره. لطفاً به پشتیبانی اطلاع بده.")
                return

            plan = (await db.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.id == link.plan_id)
            )).scalar_one_or_none()
            if not plan:
                click.redemption_status = "failed"
                await db.commit()
                await update.message.reply_text("این لینک مشکل داره. لطفاً به پشتیبانی اطلاع بده.")
                return

            existing_sub = (await db.execute(
                select(UserSubscription).where(
                    UserSubscription.user_id == user.id,
                    UserSubscription.plan_id == link.plan_id,
                    UserSubscription.status == "active",
                    UserSubscription.expires_at > _utcnow()
                )
            )).scalar_one_or_none()

            if existing_sub:
                click.redemption_status = "already_used"
                await db.commit()
                await update.message.reply_text("تو قبلاً این اشتراک رو داری.")
                return

            expires_at = _utcnow() + timedelta(hours=link.offer_duration_hours)
            sub = UserSubscription(
                user_id=user.id,
                plan_id=link.plan_id,
                status="active",
                purchased_at=_utcnow(),
                expires_at=expires_at,
            )
            db.add(sub)

            click.redemption_status = "redeemed"
            click.redeemed_at = _utcnow()
            await db.commit()

            hours = link.offer_duration_hours
            duration_text = f"{hours} ساعت" if hours != 48 else "۴۸ ساعت"
            await update.message.reply_text(
                f"🎉 تبریک! اشتراک {plan.name} به مدت {duration_text} برات فعال شد.\n\n"
                f"از لینک: {link.title}"
            )

        elif link.offer_type == "topup_discount":
            account = await get_or_create_billing_account(db, user)
            metadata_json = {
                "promotional_link_id": link.id,
                "link_code": link.code,
                "discount_percent": link.discount_percent,
            }
            ledger = TomanLedgerEntry(
                user_id=user.id,
                billing_account_id=account.id,
                amount_toman=0,
                gift_delta_toman=0,
                paid_delta_toman=0,
                gift_balance_after_toman=account.gift_balance_toman,
                paid_balance_after_toman=account.paid_balance_toman,
                entry_type="promotional_link_topup_discount",
                reason=f"تخفیف شارژ از لینک تبلیغاتی: {link.title} ({link.discount_percent}%)",
                metadata_json=metadata_json,
            )
            db.add(ledger)
            click.redemption_status = "redeemed"
            click.redeemed_at = _utcnow()
            await db.commit()
            await update.message.reply_text(
                f"🎉 تبریک! تخفیف {link.discount_percent}% برای شارژ بعدیت فعال شد.\n\n"
                f"از لینک: {link.title}"
            )

        else:
            click.redemption_status = "failed"
            await db.commit()
            await update.message.reply_text("این لینک مشکل داره. لطفاً به پشتیبانی اطلاع بده.")

    except Exception as e:
        click.redemption_status = "failed"
        await db.commit()
        logger.error(f"Failed to apply promotional offer: {e}")
        await update.message.reply_text("خطایی رخ داد. لطفاً دوباره تلاش کن.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _reset_ephemeral_state(context, clear_pending=True)
    uid = update.effective_user.id
    first_name = update.effective_user.first_name or ""
    username = update.effective_user.username or ""
    payload = (context.args[0] or "").strip() if context.args else ""

    async with async_session() as db:
        user = await get_user(db, uid, first_name, username)

        if payload.startswith("ref_"):
            token = payload.strip()
            campaign = (await db.execute(select(ReferralCampaign).where(ReferralCampaign.code == token))).scalar_one_or_none()
            if campaign:
                if not user.referral_campaign_id:
                    user.referral_campaign_id = campaign.id

                event = ReferralEvent(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    event_type="start"
                )
                db.add(event)

                referrer_id = campaign.created_by_user_id
                if referrer_id and referrer_id != user.id:
                    from app.models import ReferralConfig, UserBillingAccount
                    from app.services.toman_billing_service import get_or_create_billing_account

                    config = (await db.execute(select(ReferralConfig).where(ReferralConfig.name == "default"))).scalar_one_or_none()
                    reward = int(config.reward_toman if config else 50000)

                    referrer = (await db.execute(select(UserPreference).where(UserPreference.id == referrer_id))).scalar_one_or_none()
                    if referrer:
                        referrer_account = await get_or_create_billing_account(db, referrer)
                        referrer_account.gift_balance_toman = int(referrer_account.gift_balance_toman or 0) + reward
                        referrer_account.total_gift_granted_toman = int(referrer_account.total_gift_granted_toman or 0) + reward
                        referrer_account.version = int(referrer_account.version or 0) + 1

                        from app.models import TomanLedgerEntry
                        ledger_entry = TomanLedgerEntry(
                            user_id=referrer.id,
                            billing_account_id=referrer_account.id,
                            amount_toman=reward,
                            gift_delta_toman=reward,
                            paid_delta_toman=0,
                            gift_balance_after_toman=referrer_account.gift_balance_toman,
                            paid_balance_after_toman=referrer_account.paid_balance_toman,
                            entry_type="referral_reward",
                            reason=f"\u067e\u0627\u062f\u0627\u0634 \u062f\u0639\u0648\u062a \u06a9\u0627\u0631\u0628\u0631 \u062c\u062f\u06cc\u062f (user {user.id})",
                            metadata_json={
                                "referred_user_id": user.id,
                                "campaign_id": campaign.id,
                                "campaign_code": campaign.code,
                            },
                        )
                        db.add(ledger_entry)

                        signup_event = ReferralEvent(
                            campaign_id=campaign.id,
                            user_id=user.id,
                            event_type="signup",
                        )
                        db.add(signup_event)

                        if referrer.telegram_user_id:
                            try:
                                await context.bot.send_message(
                                    chat_id=referrer.telegram_user_id,
                                    text=f"\U0001f389 \u06cc\u06a9\u06cc \u0627\u0632 \u062f\u0648\u0633\u062a\u0627\u0646\u062a\u0627\u0646 \u0628\u0627 \u0644\u06cc\u0646\u06a9 \u062f\u0639\u0648\u062a \u0634\u0645\u0627 \u0648\u0627\u0631\u062f \u0634\u062f!\n\n"
                                         f"\u067e\u0627\u062f\u0627\u0634 \u0634\u0645\u0627: {_format_toman(reward)} \u0628\u0647 \u06a9\u06cc\u0641 \u067e\u0648\u0644\u062a\u0627\u0646 \u0627\u0636\u0627\u0641\u0647 \u0634\u062f.",
                                )
                            except Exception:
                                pass

                await db.commit()

        if payload.startswith("offer_"):
            offer_code = payload.removeprefix("offer_").strip()
            link = (await db.execute(
                select(PromotionalLink).where(
                    PromotionalLink.code == offer_code,
                    PromotionalLink.is_active == True
                )
            )).scalar_one_or_none()

            if not link:
                await update.message.reply_text("\u0644\u06cc\u0646\u06a9 \u0646\u0627\u0645\u0639\u062a\u0628\u0631\u0647 \u06cc\u0627 \u0645\u0646\u0642\u0636\u06cc \u0634\u062f\u0647.")
            else:
                now = _utcnow()
                if link.expires_at and now > link.expires_at:
                    await update.message.reply_text("\u0627\u06cc\u0646 \u0644\u06cc\u0646\u06a9 \u0645\u0646\u0642\u0636\u06cc \u0634\u062f\u0647.")
                else:
                    from app.services.toman_billing_service import get_or_create_billing_account

                    click = PromotionalLinkClick(
                        promotional_link_id=link.id,
                        user_id=user.id,
                        redemption_status="pending"
                    )
                    db.add(click)
                    await db.flush()

                    existing = (await db.execute(
                        select(PromotionalLinkClick).where(
                            PromotionalLinkClick.promotional_link_id == link.id,
                            PromotionalLinkClick.user_id == user.id,
                            PromotionalLinkClick.redemption_status == "redeemed"
                        )
                    )).scalar_one_or_none()

                    if existing:
                        click.redemption_status = "already_used"
                        await db.commit()
                        await update.message.reply_text("\u062a\u0648 \u0642\u0628\u0644\u0627\u064b \u0627\u06cc\u0646 \u0644\u06cc\u0646\u06a9 \u0631\u0648 \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0631\u062f\u06cc.")
                    else:
                        if link.max_redemptions is not None:
                            redemption_count = (await db.execute(
                                select(func.count(PromotionalLinkClick.id)).where(
                                    PromotionalLinkClick.promotional_link_id == link.id,
                                    PromotionalLinkClick.redemption_status == "redeemed"
                                )
                            )).scalar() or 0
                            if redemption_count >= link.max_redemptions:
                                click.redemption_status = "failed"
                                await db.commit()
                                await update.message.reply_text("\u0638\u0631\u0641\u06cc\u062a \u0627\u06cc\u0646 \u0644\u06cc\u0646\u06a9 \u062a\u0645\u0627\u0645 \u0634\u062f\u0647.")
                            else:
                                await _apply_promotional_offer(update, db, context, user, link, click)
                        else:
                            await _apply_promotional_offer(update, db, context, user, link, click)

        if uid == ADMIN_ID and not user.preferred_name:
            user.preferred_name = first_name or "\u0645\u062d\u0645\u062f \u0639\u0644\u06cc"
            await db.commit()

        if uid != ADMIN_ID and not _user_onboarding_completed(user):
            await _ensure_onboarding_or_prompt(update, context, user=user)
            return

        main_menu = main_kb(uid == ADMIN_ID)

        welcome_text = (
            "\u0633\u0644\u0627\u0645! \U0001f44b\n\n"
            "\u0645\u0646 **\u062f\u06a9\u062a\u0631 \u0628\u0632** \u0647\u0633\u062a\u0645\u060c \u062f\u0633\u062a\u06cc\u0627\u0631 \u0647\u0648\u0634\u0645\u0646\u062f \u0634\u0645\u0627.\n\n"
            "\U0001f3af \u0627\u06cc\u0646\u062c\u0627 \u0645\u06cc\u200c\u062a\u0648\u0646\u06cc:\n"
            "\u2022 \U0001f48e \u0627\u0634\u062a\u0631\u0627\u06a9\u200c\u0647\u0627\u06cc \u0648\u06cc\u0698\u0647 \u0631\u0648 \u0628\u0628\u06cc\u0646\u06cc \u0648 \u062e\u0631\u06cc\u062f\u0627\u0631\u06cc \u06a9\u0646\u06cc\n"
            "\u2022 \U0001f4b0 \u06a9\u06cc\u0641 \u067e\u0648\u0644\u062a \u0631\u0648 \u0634\u0627\u0631\u0698 \u06a9\u0646\u06cc\n"
            "\u2022 \U0001f464 \u062d\u0633\u0627\u0628 \u06a9\u0627\u0631\u0628\u0631\u06cc \u0648 \u062a\u0631\u0627\u06a9\u0646\u0634\u200c\u0647\u0627\u062a \u0631\u0648 \u0645\u062f\u06cc\u0631\u06cc\u062a \u06a9\u0646\u06cc\n"
            "\u2022 \U0001f381 \u0628\u0627 \u062f\u0639\u0648\u062a \u062f\u0648\u0633\u062a\u0627\u0646\u060c \u0627\u0639\u062a\u0628\u0627\u0631 \u0647\u062f\u06cc\u0647 \u0628\u06af\u06cc\u0631\u06cc\n"
            "\u2022 \U0001f680 \u0627\u067e\u0644\u06cc\u06a9\u06cc\u0634\u0646 \u062f\u06a9\u062a\u0631 \u0628\u0632 \u0631\u0648 \u0628\u0627\u0632 \u06a9\u0646\u06cc\n\n"
            "\u0627\u0632 \u0645\u0646\u0648\u06cc \u0632\u06cc\u0631 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646:"
        )

        await update.message.reply_text(welcome_text, reply_markup=main_menu, parse_mode="Markdown")


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  NEW CHAT - DISABLED (AI removed)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\u0642\u0627\u0628\u0644\u06cc\u062a \u0686\u062a \u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc \u062f\u0631 \u062d\u0627\u0644 \u062d\u0627\u0636\u0631 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a.", reply_markup=main_kb(update.effective_user.id == ADMIN_ID))
# ══════════════════════════════════════
#  LIST CHATS
# ══════════════════════════════════════
async def cmd_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as db:
        user = await get_user(db, update.effective_user.id, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return
        text, kb = await _build_chats_page_text_and_kb(db, user=user, page=0, page_size=CHATS_PAGE_SIZE)
    await update.message.reply_text(text, reply_markup=kb)


async def _build_chats_page_text_and_kb(
    db: AsyncSession,
    *,
    user: UserPreference,
    page: int,
    page_size: int = CHATS_PAGE_SIZE,
) -> tuple[str, InlineKeyboardMarkup | None]:
    safe_page_size = max(1, min(page_size, 20))
    visibility_filter = True if user.is_admin else Chat.user_preference_id == user.id
    total = (
        await db.execute(
            select(func.count(func.distinct(Chat.id)))
            .join(Message, Message.chat_id == Chat.id)
            .where(Message.role == "user", visibility_filter)
        )
    ).scalar() or 0
    if total == 0:
        return "چتی نیست 💬", None

    total_pages = (total + safe_page_size - 1) // safe_page_size
    safe_page = max(0, min(page, total_pages - 1))
    offset = safe_page * safe_page_size
    result = await db.execute(
        select(Chat)
        .join(Message, Message.chat_id == Chat.id)
        .where(Message.role == "user", visibility_filter)
        .group_by(Chat.id)
        .order_by(Chat.created_at.desc())
        .offset(offset)
        .limit(safe_page_size)
    )
    chats = result.scalars().all()

    buttons: list[list[InlineKeyboardButton]] = []
    for c in chats:
        buttons.append([InlineKeyboardButton(f"{c.title}", callback_data=f"open_{c.id}")])

    nav_row: list[InlineKeyboardButton] = []
    if safe_page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"chats_page_{safe_page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {safe_page + 1}/{total_pages}", callback_data="chats_page_noop"))
    if safe_page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"chats_page_{safe_page + 1}"))
    buttons.append(nav_row)

    text = f"📋 چت‌ها (صفحه {safe_page + 1} از {total_pages}):"
    return text, InlineKeyboardMarkup(buttons)


# ══════════════════════════════════════
#  PRO STATUS HELPERS
# ══════════════════════════════════════
async def _is_pro_or_admin(db: AsyncSession, user: UserPreference) -> bool:
    if user.is_admin or user.is_pro:
        return True
    from app.models import UserSubscription
    active_sub = (
        await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
                UserSubscription.expires_at > _utcnow(),
            )
        )
    ).scalars().first()
    return active_sub is not None

async def _send_pro_restriction_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🚀 *دسترسی به پروژه‌ها مخصوص کاربران پرو است!*\n\n" \
           "شما می‌توانید با شارژ حساب خود، به قابلیت مدیریت پروژه‌ها و دانش‌نامه اختصاصی دسترسی پیدا کنید.\n\n" \
           "💡 کاربران پرو می‌توانند فایل‌های خود را آپلود کرده و از هوش مصنوعی بخواهند بر اساس آن‌ها پاسخ دهد."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("➕ شارژ و ارتقا", callback_data="toman_topup_start")]])
    
    if update.message:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)


# ══════════════════════════════════════
#  PROJECTS
# ══════════════════════════════════════
async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _claim_update_once(update):
        return
    try:
        _reset_ephemeral_state(context, clear_pending=True)
        uid = update.effective_user.id
        chat = update.effective_chat
        async with async_session() as db:
            user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")

            # Pro Status restriction
            if not await _is_pro_or_admin(db, user):
                text = "🚀 *دسترسی به پروژه‌ها مخصوص کاربران پرو است!*\n\n" \
                       "شما می‌توانید با شارژ حساب خود، به قابلیت مدیریت پروژه‌ها و دانش‌نامه اختصاصی دسترسی پیدا کنید.\n\n" \
                       "💡 کاربران پرو می‌توانند فایل‌های خود را آپلود کرده و از هوش مصنوعی بخواهند بر اساس آن‌ها پاسخ دهد."
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("➕ شارژ و ارتقا", callback_data="toman_topup_start")]])
                if update.message:
                    await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                elif update.callback_query:
                    await update.callback_query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                return

            if not await _ensure_onboarding_or_prompt(update, context, user=user):
                return
            if chat and chat.type in GROUP_ALLOWED_CHAT_TYPES:
                group_row, _ = await _ensure_telegram_group_record(
                    db,
                    telegram_chat_id=chat.id,
                    title=getattr(chat, "title", None),
                    chat_type=chat.type,
                    created_by_user_id=user.id,
                )
                group_chat = await _ensure_group_chat(db, group_row, user.current_model_id)
                projects = await list_group_public_projects(db)
                current_project_id = group_chat.project_id

                buttons: list[list[InlineKeyboardButton]] = []
                for p in projects:
                    check = "✅ " if p.id == current_project_id else ""
                    buttons.append([InlineKeyboardButton(f"{check}{p.name}", callback_data=f"gproj_{group_row['id']}_{p.id}")])
                clear_check = "✅ " if current_project_id is None else ""
                buttons.append([InlineKeyboardButton(f"{clear_check}بدون پروژه", callback_data=f"gproj_{group_row['id']}_0")])
                await db.commit()

                text_value = (
                    "📁 پروژه‌های عمومی گروه:\n"
                    "هر پروژه‌ای که لینک اشتراک داشته باشد یا عمومیِ ادمین باشد اینجا نمایش داده می‌شود."
                ) if projects else "پروژه عمومی‌ای برای گروه پیدا نشد."
                await update.message.reply_text(text_value, reply_markup=InlineKeyboardMarkup(buttons))
                return

            projects = await list_visible_projects(db, user)
            buttons = []
            for p in projects:
                check = "✅ " if p.id == user.current_project_id else ""
                buttons.append([InlineKeyboardButton(f"{check}{p.name}", callback_data=f"proj_{p.id}")])
            buttons.append([InlineKeyboardButton("➕ ساخت پروژه", callback_data="new_project")])
            text = "📁 پروژه‌ها:" if projects else "پروژه‌ای نیست!"
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
    finally:
        await _mark_update_completed(update)


# ══════════════════════════════════════
#  MODEL PICKER
# ══════════════════════════════════════
async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        await maybe_send_tip(context.bot, update.effective_chat.id, user.id, "model_menu", db)
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return

        rows = await _get_active_provider_models(db)
        if not rows:
            await update.message.reply_text("مدلی تنظیم نشده!")
            return

        current_model_name = "—"
        current_provider_name = "—"
        current_provider_id: int | None = None
        for provider, model in rows:
            if user.current_model_id and model.id == user.current_model_id:
                current_model_name = model.display_name or model.name
                current_provider_name = provider.name
                current_provider_id = provider.id
                break

        if current_provider_id is None:
            first_provider = rows[0][0]
            current_provider_id = first_provider.id
            current_provider_name = first_provider.name

        kb = await get_provider_picker_buttons(db, current_provider_id)
        current_name = "—"
        if current_model_name != "—":
            current_name = f"{current_provider_name} / {current_model_name}"
        await update.message.reply_text(
            f"🤖 {current_name}\n\nابتدا پروایدر را انتخاب کن:",
            reply_markup=kb,
        )


# ══════════════════════════════════════
#  PROJECT MODE
# ══════════════════════════════════════
async def cmd_start_convo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _reset_ephemeral_state(context, clear_pending=True)
    if _is_group_chat(update):
        await update.message.reply_text("در گروه، پروژه را با دستور /projects انتخاب کن.")
        return
    uid = update.effective_user.id
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return
        
        model_id = user.current_model_id
        if not model_id:
            _, default_model = await get_default_model(db)
            if default_model:
                model_id = default_model.id
            else:
                result = await db.execute(
                    select(DBModel)
                    .join(Provider, Provider.id == DBModel.provider_id)
                    .where(DBModel.is_active == True, Provider.is_active == True)
                    .limit(1)
                )
                fallback_model = result.scalar_one_or_none()
                if fallback_model:
                    model_id = fallback_model.id

        project_for_chat = await _get_accessible_current_project(db, user)

        chat = Chat(
            title="💬 چت جدید",
            model_id=model_id,
            project_id=user.current_project_id,
            user_preference_id=user.id,
        )
        db.add(chat)
        await db.commit()
        await db.refresh(chat)

        user.current_chat_id = chat.id
        await db.commit()

        proj_name = None
        if project_for_chat:
            proj_name = project_for_chat.name

    label = f"\n📁 {proj_name}" if proj_name else ""
    await update.message.reply_text(f"گفتگو شروع ✅{label}", reply_markup=project_kb())


async def cmd_project_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_group_chat(update):
        await update.message.reply_text("در گروه، پروژه را با دستور /projects انتخاب کن.")
        return
    uid = update.effective_user.id
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return

        if not await _is_pro_or_admin(db, user):
            await _send_pro_restriction_message(update, context)
            return

        pid = user.current_project_id
        if not pid:
            await update.message.reply_text("پروژه‌ای انتخاب نشده!")
            return
        proj = await _get_accessible_current_project(db, user)
        if not proj:
            await update.message.reply_text("این پروژه در دسترس تو نیست.", reply_markup=main_kb(uid == ADMIN_ID))
            return
        from app.models import Document
        result = await db.execute(select(Document).where(Document.project_id == pid))
        docs = result.scalars().all()
        pname = proj.name if proj else "?"

    if not docs:
        buttons = [[InlineKeyboardButton("📤 آپلود فایل", callback_data="upload_file")]]
        await update.message.reply_text(f"📂 {pname}\n\nفایلی نیست", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        buttons = []
        for d in docs:
            info = f" ({d.chunk_count} chunks)" if d.chunk_count else ""
            buttons.append([InlineKeyboardButton(f"📄 {d.filename}{info}", callback_data=f"doc_{d.id}")])
        buttons.append([InlineKeyboardButton("📤 آپلود فایل", callback_data="upload_file")])
        await update.message.reply_text(f"📂 {pname}", reply_markup=InlineKeyboardMarkup(buttons))


async def cmd_share_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_group_chat(update):
        await update.message.reply_text("اشتراک‌گذاری پروژه از چت خصوصی انجام می‌شود.")
        return
    uid = update.effective_user.id
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return

        if not await _is_pro_or_admin(db, user):
            await _send_pro_restriction_message(update, context)
            return

        if not user.current_project_id:
            await update.message.reply_text("پروژه‌ای انتخاب نشده!")
            return
        project = await user_can_access_project(db, user, user.current_project_id)
        if not project:
            await update.message.reply_text("پروژه پیدا نشد یا دسترسی نداری.", reply_markup=main_kb(uid == ADMIN_ID))
            return
        token = await ensure_project_share_token(db, project)

    link = await _build_project_share_deep_link(context, token)
    if link:
        await update.message.reply_text(f"🔗 لینک اشتراک پروژه:\n{link}", reply_markup=project_kb())
    else:
        await update.message.reply_text(f"🔗 کد اشتراک پروژه:\n/start {PROJECT_SHARE_START_PREFIX}{token}", reply_markup=project_kb())


async def cmd_project_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_group_chat(update):
        await update.message.reply_text("ویرایش دستورالعمل پروژه از چت خصوصی انجام می‌شود.")
        return
    uid = update.effective_user.id
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return

        if not await _is_pro_or_admin(db, user):
            await _send_pro_restriction_message(update, context)
            return

        if not user.current_project_id:
            await update.message.reply_text("پروژه‌ای انتخاب نشده!")
            return
        project = await user_can_access_project(db, user, user.current_project_id)
        if not project:
            await update.message.reply_text("پروژه پیدا نشد یا دسترسی نداری.", reply_markup=main_kb(uid == ADMIN_ID))
            return
        if project.owner_user_id is None and not user.is_admin:
            await update.message.reply_text("فقط ادمین می‌تواند دستورالعمل پروژه‌های عمومی را تغییر دهد.", reply_markup=project_kb())
            return
        current = (project.instructions or "").strip() or "تنظیم نشده"

    _begin_mode(context, "setting_project_instructions")
    await update.message.reply_text(
        f"🧾 دستورالعمل فعلی:\n{current}\n\nدستورالعمل جدید را بفرست. برای حذف، فقط - را بفرست.",
        reply_markup=project_kb(),
    )


async def cmd_project_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_group_chat(update):
        await update.message.reply_text("تنظیمات پروژه از چت خصوصی انجام می‌شود.")
        return
    uid = update.effective_user.id
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return

        if not await _is_pro_or_admin(db, user):
            await _send_pro_restriction_message(update, context)
            return

        if not user.current_project_id:
            await update.message.reply_text("پروژه‌ای انتخاب نشده!")
            return
        project = await user_can_access_project(db, user, user.current_project_id)
        if not project:
            await update.message.reply_text("پروژه پیدا نشد یا دسترسی نداری.", reply_markup=main_kb(uid == ADMIN_ID))
            return

        # Check ownership for sensitive operations
        is_owner = project.owner_user_id == user.id or user.is_admin
        if not is_owner:
            await update.message.reply_text("فقط صاحب پروژه یا ادمین می‌تواند تنظیمات پروژه را تغییر دهد.", reply_markup=project_kb())
            return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ تغییر نام", callback_data=f"pj_ren_{project.id}")],
        [InlineKeyboardButton("🗑 حذف پروژه", callback_data=f"pj_del_{project.id}")],
    ])
    await update.message.reply_text(f"⚙️ تنظیمات پروژه: {project.name}", reply_markup=kb)


async def cmd_exit_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _reset_ephemeral_state(context, clear_pending=True)
    if _is_group_chat(update):
        await update.message.reply_text("در گروه، با /projects می‌تونی پروژه گروه را روی «بدون پروژه» بگذاری.")
        return
    uid = update.effective_user.id
    async with async_session() as db:
        await save_user(db, uid, current_project_id=None)
    await update.message.reply_text("🔙 خروج از پروژه", reply_markup=main_kb(uid == ADMIN_ID))


async def handle_resume_pending_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    async with async_session() as db:
        user = await get_user(db, uid, query.from_user.first_name or "", query.from_user.username or "")
        if not user.pending_action_payload:
            await query.answer("هیچ کار معلقی پیدا نشد.", show_alert=True)
            try: await query.message.edit_reply_markup(reply_markup=None)
            except: pass
            return

        payload_data = user.pending_action_payload
        action_type = payload_data.get("action_type")
        args = payload_data.get("payload", {})
        
        # Clear state to prevent double execution
        user.pending_action_payload = None
        await db.commit()
        
        await query.answer("⏳ در حال ادامه...")
        try: await query.message.delete()
        except: pass

        if action_type == "chat_completion":
            from app.llm import get_provider_and_model
            provider_obj, model_obj = await get_provider_and_model(db, user, args.get("provider_name"), args.get("model_name"))
            
            payg_consent = context.user_data.pop("payg_consent", False)
            
            class DummyObj:
                def __init__(self, **kwargs): self.__dict__.update(kwargs)
            
            dummy_msg = DummyObj(id=args.get("user_message_id"))
            dummy_chat = DummyObj(id=args.get("chat_id"))
            
            await _run_tool_aware_completion(
                update, db, user=user, user_message=dummy_msg, chat=dummy_chat,
                provider=provider_obj, model=model_obj, llm_messages=args.get("llm_messages"),
                proj_label=args.get("proj_label", ""), allow_tools=args.get("allow_tools", True),
                uploaded_file_id=args.get("uploaded_file_id"), routing=None,
                payg_consent=payg_consent,
            )
        elif action_type == "voice_transcription":
            # Re-run transcription logic
            processing_msg = await query.message.reply_text("🎙 در حال از سرگیری تبدیل پیام صوتی...")
            
            # Transcription config
            async with async_session() as db:
                transcription_config = await _get_or_create_transcription_config(db)
            
            await _execute_voice_transcription(
                update,
                context,
                uid=uid,
                voice_file_id=args.get("voice_file_id"),
                voice_file_unique_id=args.get("voice_file_unique_id") or args.get("voice_file_id"),
                duration=args.get("duration", 0),
                mime_type=args.get("mime_type", "audio/ogg"),
                project_id=user.current_project_id,
                explicit_upload_requested=False, # Standard chat voice
                project_upload_mode=False,
                processing_msg=processing_msg,
                transcription_config=transcription_config,
                estimated_cost=0.0, # Already checked or will be charged actual
                estimated_in_tokens=_estimate_audio_tokens(args.get("duration", 0)),
                estimated_out_tokens=64,
                voice_file_size=0
            )
        elif action_type in ("audio_document_transcription", "document_embedding"):
            await query.message.reply_text("🔄 لطفاً فایل یا پیام صوتی را مجدداً ارسال کنید. (قابلیت از سرگیری فایل در حال تکمیل است)")
        else:
            await query.message.reply_text("❌ نوع عملیات نامعتبر است.")


# ══════════════════════════════════════
#  CALLBACK QUERIES
# ══════════════════════════════════════
class _CallbackAsMessageUpdate:
    """Mock update to allow processing a callback as if it were a message."""
    def __init__(self, update: Update):
        self._update = update
        # Set update_id to None to bypass _claim_update_once check in handle_message
        self.update_id = None
        self.callback_query = update.callback_query
        self.effective_user = update.effective_user
        self.effective_chat = update.effective_chat
        self.message = update.callback_query.message if update.callback_query else update.message

    def __getattr__(self, name):
        return getattr(self._update, name)


async def _show_subscription_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE, query, *, plan_id: int) -> None:
    uid = update.effective_user.id
    async with async_session() as db:
        if not await _is_sub_feature_enabled(db):
            await query.answer("این ویژگی در حال حاضر غیرفعال است.", show_alert=True)
            return

        from app.models import SubscriptionPlan
        from app.services.toman_billing_service import get_or_create_subscription_config

        plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))).scalar_one_or_none()
        if not plan:
            await query.answer("طرح یافت نشد.", show_alert=True)
            return

        config = await get_or_create_subscription_config(db)
        price_toman = int(getattr(plan, "monthly_price_toman", None) or config.monthly_price_toman or 0)

        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        wallet_balance_toman = await _toman_balance(db, user)
        usable_wallet = min(wallet_balance_toman, price_toman)

    buttons = []
    if usable_wallet > 0:
        if usable_wallet >= price_toman:
            buttons.append([InlineKeyboardButton("💰 پرداخت از کیف پول", callback_data=f"sub_pay_wallet_{plan_id}")])
        else:
            buttons.append([InlineKeyboardButton(f" کیف پول + پرداخت {_format_toman(price_toman - usable_wallet)}", callback_data=f"sub_pay_wallet_{plan_id}")])

    buttons.append([InlineKeyboardButton("💳 درگاه پرداخت بله", callback_data=f"sub_pay_bale_{plan_id}")])
    buttons.append([InlineKeyboardButton("💰 کارت به کارت", callback_data=f"sub_pay_card_{plan_id}")])
    buttons.append([InlineKeyboardButton("❌ انصراف", callback_data="cancel_buy_plan")])

    kb = InlineKeyboardMarkup(buttons)

    wallet_line = f"\n موجودی کیف پول: {_format_toman(wallet_balance_toman)} تومان" if wallet_balance_toman > 0 else ""
    text = (
        f"💵 روش پرداخت برای خرید اشتراک *{plan.name}* را انتخاب کنید:\n"
        f"مبلغ: {_format_toman(price_toman)} تومان{wallet_line}\n\n"
        " *درگاه پرداخت بله*\n"
        "پرداخت آنلاین از طریق درگاه بله\n\n"
        "💰 *کارت به کارت*\n"
        "واریز به شماره کارت ادمین و ارسال رسید\n"
        "تأیید معمولاً ۵ تا ۱۰ دقیقه (به جز نیمه‌شب)"
    )

    await query.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")
    await query.answer()


async def _start_subscription_card_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, query, *, plan_id: int) -> None:
    uid = update.effective_user.id

    if not _is_bale_platform():
        await query.answer("پرداخت کارت به کارت فقط در حالت بازوی بله فعال است.", show_alert=True)
        return

    try:
        await query.message.delete()
    except Exception:
        pass

    async with async_session() as db:
        from app.models import PaymentMethod, SubscriptionPlan
        from app.services.toman_billing_service import get_or_create_subscription_config

        methods = (
            await db.execute(
                select(PaymentMethod).where(PaymentMethod.is_active == True).order_by(PaymentMethod.sort_order, PaymentMethod.id)
            )
        ).scalars().all()

        if not methods:
            await query.message.reply_text(
                "⚠️ در حال حاضر شماره کارتی برای پرداخت ثبت نشده است.\n"
                "لطفاً بعداً مجدداً تلاش کنید یا به پشتیبانی پیام دهید."
            )
            return

        plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))).scalar_one_or_none()
        if not plan:
            await query.message.reply_text("طرح یافت نشد.")
            return

        config = await get_or_create_subscription_config(db)
        price_toman = int(getattr(plan, "monthly_price_toman", None) or config.monthly_price_toman or 0)

    cards_text = "💳 *شماره کارت‌های مقصد:*\n\n"
    sub_kb_rows = []
    for m in methods:
        cards_text += f"🏦 *{m.bank_name}*\n"
        cards_text += f"شماره کارت: `{m.card_number}`\n"
        cards_text += f"صاحب کارت: {m.cardholder_name}\n"
        if m.description:
            cards_text += f"📝 {m.description}\n"
        cards_text += "\n"
        sub_kb_rows.append([InlineKeyboardButton(f"📋 کپی {m.card_number}", copy_text=CopyTextButton(text=m.card_number))])

    cards_text += (
        f"💰 مبلغ قابل پرداخت: *{_format_toman(price_toman)} تومان*\n\n"
        "⏱ *زمان تأیید:* معمولاً ۵ تا ۱۰ دقیقه بعد از ارسال رسید\n"
        "(به جز ساعات نیمه‌شب که ممکن است بیشتر طول بکشد)\n\n"
        "لطفاً تصویر رسید پرداخت را ارسال کنید:"
    )

    sub_reply_kb = InlineKeyboardMarkup(sub_kb_rows) if sub_kb_rows else None

    await query.message.reply_text(cards_text, parse_mode="Markdown", reply_markup=sub_reply_kb)

    _begin_mode(context, "awaiting_subscription_card_receipt")
    context.user_data["pending_subscription_plan_id"] = plan_id
    context.user_data["pending_subscription_amount_toman"] = price_toman
    await query.message.reply_text(
        "📸 لطفاً تصویر رسید پرداخت را ارسال کنید.",
        reply_markup=_cancel_reply_kb(),
    )


async def _start_subscription_payment(update: Update, query, *, plan_id: int, use_wallet: bool) -> None:
    uid = update.effective_user.id
    try:
        async with async_session() as db:
            if not await _is_sub_feature_enabled(db):
                await query.answer("این ویژگی در حال حاضر غیرفعال است.", show_alert=True)
                return

            from app.models import SubscriptionPlan, UserSubscription
            from app.services.toman_billing_service import get_or_create_subscription_config, purchase_toman_subscription

            plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))).scalar_one_or_none()
            if not plan:
                await query.answer("طرح یافت نشد.", show_alert=True)
                return
            user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            active_sub = (
                await db.execute(
                    select(UserSubscription)
                    .options(selectinload(UserSubscription.plan))
                    .where(
                        UserSubscription.user_id == user.id,
                        UserSubscription.status == "active",
                        UserSubscription.expires_at > _utcnow(),
                    )
                    .order_by(UserSubscription.expires_at.desc())
                )
            ).scalars().first()
            if active_sub:
                plan_name = active_sub.plan.name if active_sub.plan else "نامعلوم"
                await query.message.reply_text(
                    " اشتراک فعال دارید.\n"
                    f"پلن: {plan_name}\n"
                    f"انقضا: {format_persian(active_sub.expires_at, '%Y-%m-%d %H:%M')}"
                )
                await query.answer()
                return
            config = await get_or_create_subscription_config(db)
            _plan_price = getattr(plan, "monthly_price_toman", None)
            price_toman = int(_plan_price) if _plan_price is not None else int(config.monthly_price_toman or 0)
            _plan_gift = getattr(plan, "gift_credit_toman", None)
            gift_toman = int(_plan_gift) if _plan_gift is not None else int(config.gift_credit_toman or 0)
            wallet_balance_toman = await _toman_balance(db, user)
            wallet_payment = min(wallet_balance_toman, price_toman) if use_wallet else 0
            payable_toman = max(0, price_toman - wallet_payment)

            if payable_toman <= 0:
                wallet_ok, _, wallet_usd = await _debit_subscription_wallet_usd(
                    db,
                    user=user,
                    wallet_payment_toman=price_toman,
                    idempotency_key=f"subscription:wallet:{user.id}:{plan.id}:{datetime.now(timezone.utc).date().isoformat()}:wallet-usd",
                    metadata={"plan_id": plan.id},
                )
                if not wallet_ok:
                    await query.message.reply_text("❌ موجودی کیف پول برای خرید اشتراک کافی نیست.")
                    await query.answer()
                    return
                result = await purchase_toman_subscription(
                    db,
                    user=user,
                    plan=plan,
                    idempotency_key=f"subscription:wallet:{user.id}:{plan.id}:{datetime.now(timezone.utc).date().isoformat()}",
                    payment_confirmed=True,
                    wallet_payment_toman=0,
                    grant_gift_toman_balance=False,
                )
                if result.ok:
                    _, usd_balance, gift_usd = await _credit_subscription_gift_usd(
                        db,
                        user=user,
                        gift_toman=gift_toman,
                        idempotency_key=f"subscription:wallet:{user.id}:{plan.id}:{datetime.now(timezone.utc).date().isoformat()}:gift-usd",
                        metadata={"plan_id": plan.id, "subscription_id": result.subscription.id if result.subscription else None},
                    )
                    await query.message.reply_text(
                        "✅ اشتراک از موجودی کیف پول فعال شد.\n"
                        f"پلن: {plan.name}\n"
                        f"پرداخت از کیف پول: {_format_toman(price_toman)}\n"
                        f"اعتبار هدیه: {_format_toman(gift_toman)}\n"
                        f"موجودی هدیه جدید: {_format_toman(gift_toman)}"
                    )
                else:
                    await query.message.reply_text("❌ موجودی شارژشده تومانی شما برای خرید اشتراک کافی نیست.")
                await query.answer()
                return

            if not _is_bale_platform():
                await query.answer("پرداخت آنلاین فقط در حالت بازوی بله فعال است.", show_alert=True)
                return
            if not BALE_WALLET_PROVIDER_TOKEN:
                await query.answer("توکن پرداخت بله تنظیم نشده است.", show_alert=True)
                await query.message.reply_text("⚠️ توکن پرداخت بله تنظیم نشده است.")
                return
            try:
                bot = query.message.bot if hasattr(query.message, "bot") else update.get_bot()
                invoice_info = await _send_bale_subscription_invoice(
                    bot=bot,
                    chat_id=query.message.chat_id,
                    user_id=uid,
                    plan_id=plan.id,
                    plan_name=plan.name,
                    payable_toman=payable_toman,
                    wallet_payment_toman=wallet_payment,
                )
            except Exception as exc:
                logger.exception("failed to send bale subscription invoice")
                await query.message.reply_text(
                    "❌ ارسال فاکتور پرداخت اشتراک انجام نشد.\n"
                    f"خطا: {str(exc)}"
                )
                await query.answer()
                return
            await query.message.reply_text(
                "✅ فاکتور پرداخت اشتراک ارسال شد.\n"
                f"پلن: {plan.name}\n"
                f"اعتبار هدیه بعد از فعال‌سازی: {_format_toman(gift_toman)}\n"
                f"پرداخت از کیف پول: {_format_toman(wallet_payment)}\n"
                f"مبلغ پرداخت آنلاین: {_format_toman(invoice_info['total_toman'])}\n"
                "بعد از پرداخت موفق، اشتراک خودکار فعال می‌شود."
            )
            await query.answer()
    except Exception as exc:
        logger.exception(f"subscription payment failed for uid={uid}, plan_id={plan_id}, use_wallet={use_wallet}")
        try:
            await query.answer("❌ خطا در پردازش درخواست. لطفاً دوباره تلاش کنید.", show_alert=True)
        except Exception:
            pass
        try:
            await query.message.reply_text(f"❌ خطا در پردازش درخواست: {str(exc)[:200]}")
        except Exception:
            pass
            return
        config = await get_or_create_subscription_config(db)
        _plan_price = getattr(plan, "monthly_price_toman", None)
        price_toman = int(_plan_price) if _plan_price is not None else int(config.monthly_price_toman or 0)
        _plan_gift = getattr(plan, "gift_credit_toman", None)
        gift_toman = int(_plan_gift) if _plan_gift is not None else int(config.gift_credit_toman or 0)
        wallet_balance_toman = await _toman_balance(db, user)
        wallet_payment = min(wallet_balance_toman, price_toman) if use_wallet else 0
        payable_toman = max(0, price_toman - wallet_payment)

        if payable_toman <= 0:
            wallet_ok, _, wallet_usd = await _debit_subscription_wallet_usd(
                db,
                user=user,
                wallet_payment_toman=price_toman,
                idempotency_key=f"subscription:wallet:{user.id}:{plan.id}:{datetime.now(timezone.utc).date().isoformat()}:wallet-usd",
                metadata={"plan_id": plan.id},
            )
            if not wallet_ok:
                await query.message.reply_text("❌ موجودی کیف پول برای خرید اشتراک کافی نیست.")
                await query.answer()
                return
            result = await purchase_toman_subscription(
                db,
                user=user,
                plan=plan,
                idempotency_key=f"subscription:wallet:{user.id}:{plan.id}:{datetime.now(timezone.utc).date().isoformat()}",
                payment_confirmed=True,
                wallet_payment_toman=0,
                grant_gift_toman_balance=False,
            )
            if result.ok:
                _, usd_balance, gift_usd = await _credit_subscription_gift_usd(
                    db,
                    user=user,
                    gift_toman=gift_toman,
                    idempotency_key=f"subscription:wallet:{user.id}:{plan.id}:{datetime.now(timezone.utc).date().isoformat()}:gift-usd",
                    metadata={"plan_id": plan.id, "subscription_id": result.subscription.id if result.subscription else None},
                )
                await query.message.reply_text(
                    "✅ اشتراک از موجودی کیف پول فعال شد.\n"
                    f"پلن: {plan.name}\n"
                    f"پرداخت از کیف پول: {_format_toman(price_toman)}\n"
                    f"اعتبار هدیه: {_format_toman(gift_toman)}\n"
                    f"موجودی هدیه جدید: {_format_toman(gift_toman)}"
                )
            else:
                await query.message.reply_text("❌ موجودی شارژشده تومانی شما برای خرید اشتراک کافی نیست.")
            await query.answer()
            return

        if not _is_bale_platform():
            await query.answer("پرداخت آنلاین فقط در حالت بازوی بله فعال است.", show_alert=True)
            return
        if not BALE_WALLET_PROVIDER_TOKEN:
            await query.answer("توکن پرداخت بله تنظیم نشده است.", show_alert=True)
            await query.message.reply_text("⚠️ توکن پرداخت بله تنظیم نشده است.")
            return
        try:
            bot = query.message.bot if hasattr(query.message, "bot") else update.get_bot()
            invoice_info = await _send_bale_subscription_invoice(
                bot=bot,
                chat_id=query.message.chat_id,
                user_id=uid,
                plan_id=plan.id,
                plan_name=plan.name,
                payable_toman=payable_toman,
                wallet_payment_toman=wallet_payment,
            )
        except Exception as exc:
            logger.exception("failed to send bale subscription invoice")
            await query.message.reply_text(
                "❌ ارسال فاکتور پرداخت اشتراک انجام نشد.\n"
                f"خطا: {str(exc)}"
            )
            await query.answer()
            return
        await query.message.reply_text(
            "✅ فاکتور پرداخت اشتراک ارسال شد.\n"
            f"پلن: {plan.name}\n"
            f"اعتبار هدیه بعد از فعال‌سازی: {_format_toman(gift_toman)}\n"
            f"پرداخت از کیف پول: {_format_toman(wallet_payment)}\n"
            f"مبلغ پرداخت آنلاین: {_format_toman(invoice_info['total_toman'])}\n"
            "بعد از پرداخت موفق، اشتراک خودکار فعال می‌شود."
        )
        await query.answer()


async def handle_activate_trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    uid = query.from_user.id
    logger.info(f"!!! activate_trial callback: uid={uid}")

    try:
        await query.answer("در حال بررسی...")
    except Exception:
        pass

    async with async_session() as db:
        user = await get_user(db, uid, query.from_user.first_name or "", query.from_user.username or "")

        if user.trial_used:
            await query.message.reply_text("❌ شما قبلاً از اشتراک تست استفاده کرده‌اید.")
            return

        from app.services.trial_service import TrialService, TrialServiceError

        try:
            subscription = await TrialService.grant_trial_subscription(db, user.id, reason="User activated via bot callback")
            config_result = await db.execute(select(TrialConfig).limit(1))
            config = config_result.scalar_one_or_none()
            welcome_msg = config.welcome_message if config and config.welcome_message else "🎉 اشتراک تست ۲۴ ساعته شما فعال شد!\nاکنون می‌توانید از تمام امکانات استفاده کنید."
            await query.message.reply_text(welcome_msg)
        except TrialServiceError as e:
            await query.message.reply_text(f"❌ خطا در فعال‌سازی: {str(e)}")
        except Exception as e:
            logger.error(f"Trial activation failed for user {uid}: {e}")
            await query.message.reply_text("❌ خطایی رخ داد. لطفاً بعداً دوباره تلاش کنید.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data
    uid = query.from_user.id

    if data == "activate_trial":
        await handle_activate_trial_callback(update, context)
        return

    if data == "limit_wait":
        await query.answer("\u23f3 \u0647\u0631 \u0648\u0642\u062a \u0622\u0645\u0627\u062f\u0647 \u0628\u0648\u062f\u06cc \u062f\u0648\u0628\u0627\u0631\u0647 \u067e\u06cc\u0627\u0645 \u0628\u062f\u0647")
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if query.data.startswith("buy_plan_"):
        plan_id = int(query.data.replace("buy_plan_", ""))
        async with async_session() as db:
            if not await _is_sub_feature_enabled(db):
                await query.answer("\u0627\u06cc\u0646 \u0648\u06cc\u0698\u06af\u06cc \u062f\u0631 \u062d\u0627\u0644 \u062d\u0627\u0636\u0631 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a.", show_alert=True)
                return

            from app.models import SubscriptionPlan, UserSubscription
            plan = (await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))).scalar_one_or_none()
            if not plan:
                await query.answer("\u0637\u0631\u062d \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.", show_alert=True)
                return
            user = await get_user(db, update.effective_user.id, update.effective_user.first_name or "", update.effective_user.username or "")
            active_sub = (
                await db.execute(
                    select(UserSubscription)
                    .options(selectinload(UserSubscription.plan))
                    .where(
                        UserSubscription.user_id == user.id,
                        UserSubscription.status == "active",
                        UserSubscription.expires_at > _utcnow(),
                    )
                    .order_by(UserSubscription.expires_at.desc())
                )
            ).scalars().first()
            if active_sub:
                plan_name = active_sub.plan.name if active_sub.plan else "\u0646\u0627\u0645\u0639\u0644\u0648\u0645"
                await query.message.reply_text(
                    "\U0001f48e \u0627\u0634\u062a\u0631\u0627\u06a9 \u0641\u0639\u0627\u0644 \u062f\u0627\u0631\u06cc\u062f.\n"
                    f"\u067e\u0644\u0646: {plan_name}\n"
                    f"\u0627\u0646\u0642\u0636\u0627: {format_persian(active_sub.expires_at, '%Y-%m-%d %H:%M')}"
                )
                await query.answer()
                return

            from app.services.toman_billing_service import get_or_create_subscription_config

            config = await get_or_create_subscription_config(db)
            _plan_price = getattr(plan, "monthly_price_toman", None)
            price_toman = int(_plan_price) if _plan_price is not None else int(config.monthly_price_toman or 0)
            _plan_gift = getattr(plan, "gift_credit_toman", None)
            gift_toman = int(_plan_gift) if _plan_gift is not None else int(config.gift_credit_toman or 0)
            wallet_balance_toman = await _toman_balance(db, user)
            usable_wallet = min(wallet_balance_toman, price_toman)
            text = (
                f"\u062e\u0631\u06cc\u062f \u0627\u0634\u062a\u0631\u0627\u06a9 {plan.name}\n"
                f"\u0642\u06cc\u0645\u062a: {_format_toman(price_toman)}\n"
                f"\u0627\u0639\u062a\u0628\u0627\u0631 \u0647\u062f\u06cc\u0647 \u0628\u0639\u062f \u0627\u0632 \u0641\u0639\u0627\u0644\u200c\u0633\u0627\u0632\u06cc: {_format_toman(gift_toman)}\n"
                f"\u0645\u0648\u062c\u0648\u062f\u06cc \u062a\u0648\u0645\u0627\u0646\u06cc \u0642\u0627\u0628\u0644 \u0627\u0633\u062a\u0641\u0627\u062f\u0647: {_format_toman(wallet_balance_toman)}"
            )
            buttons = [[InlineKeyboardButton("\U0001f4b5 \u0627\u0646\u062a\u062e\u0627\u0628 \u0631\u0648\u0634 \u067e\u0631\u062f\u0627\u062e\u062a", callback_data=f"sub_pay_choose_{plan_id}")]]
            if usable_wallet > 0:
                if usable_wallet >= price_toman:
                    buttons.insert(0, [InlineKeyboardButton("\u067e\u0631\u062f\u0627\u062e\u062a \u0627\u0632 \u06a9\u06cc\u0641 \u067e\u0648\u0644", callback_data=f"sub_pay_wallet_{plan_id}")])
                else:
                    buttons.insert(0, [InlineKeyboardButton(f"\u06a9\u06cc\u0641 \u067e\u0648\u0644 + \u067e\u0631\u062f\u0627\u062e\u062a {_format_toman(price_toman - usable_wallet)}", callback_data=f"sub_pay_wallet_{plan_id}")])
            buttons.append([InlineKeyboardButton("\u274c \u0627\u0646\u0635\u0631\u0627\u0641", callback_data="cancel_buy_plan")])
            kb = InlineKeyboardMarkup(buttons)
            await query.message.reply_text(text, reply_markup=kb)
            await query.answer()
            return

    if query.data == "cancel_buy_plan":
        await query.message.delete()
        await query.answer("\u0639\u0645\u0644\u06cc\u0627\u062a \u0644\u063a\u0648 \u0634\u062f.")
        return

    if query.data.startswith("sub_pay_choose_"):
        plan_id = int(query.data.replace("sub_pay_choose_", ""))
        await _show_subscription_payment_methods(update, context, query, plan_id=plan_id)
        return

    if query.data.startswith("sub_pay_bale_"):
        plan_id = int(query.data.replace("sub_pay_bale_", ""))
        await _start_subscription_payment(update, query, plan_id=plan_id, use_wallet=False)
        return

    if query.data.startswith("sub_pay_card_"):
        plan_id = int(query.data.replace("sub_pay_card_", ""))
        await _start_subscription_card_payment(update, context, query, plan_id=plan_id)
        return

    if query.data.startswith("sub_pay_full_"):
        plan_id = int(query.data.replace("sub_pay_full_", ""))
        await _start_subscription_payment(update, query, plan_id=plan_id, use_wallet=False)
        return

    if query.data.startswith("sub_pay_wallet_"):
        plan_id = int(query.data.replace("sub_pay_wallet_", ""))
        await _start_subscription_payment(update, query, plan_id=plan_id, use_wallet=True)
        return

    if query.data.startswith("confirm_buy_plan_"):
        plan_id = int(query.data.replace("confirm_buy_plan_", ""))
        await _start_subscription_payment(update, query, plan_id=plan_id, use_wallet=True)
        return

    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {e}")

    if not await _claim_update_once(update):
        return

    try:
        data = query.data
        uid = query.from_user.id

        if data == "cancel_main":
            _reset_ephemeral_state(context, clear_pending=True)
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text("\u0628\u0631\u06af\u0634\u062a\u06cc\u0645 \u0628\u0647 \u0645\u0646\u0648\u06cc \u0627\u0635\u0644\u06cc.", reply_markup=main_kb(uid == ADMIN_ID))
            return

        if uid != ADMIN_ID and data not in {"share_contact_request", "just_name"}:
            async with async_session() as db:
                user = await get_user(db, uid, query.from_user.first_name or "", query.from_user.username or "")
                if not await _ensure_onboarding_or_prompt(update, context, user=user):
                    return

        if data in {
            "account_home", "account_profile", "account_usage",
            "account_credit", "account_transactions", "account_referral",
            "account_refresh", "account_refresh_home", "account_refresh_profile",
            "account_refresh_usage", "account_refresh_credit",
            "account_refresh_transactions", "account_refresh_referral",
        }:
            section = "home"
            if data in {"account_profile", "account_refresh_profile"}:
                section = "profile"
            elif data in {"account_usage", "account_refresh_usage"}:
                section = "usage"
            elif data in {"account_credit", "account_refresh_credit"}:
                section = "credit"
            elif data in {"account_transactions", "account_refresh_transactions"}:
                section = "transactions"
            elif data in {"account_referral", "account_refresh_referral"}:
                section = "referral"

            async with async_session() as db:
                user = await get_user(db, uid, query.from_user.first_name or "", query.from_user.username or "")
                ctx = await _load_account_context(db, user, tx_limit=12 if section == "transactions" else 8)
                if section == "profile":
                    text = _account_profile_text(user, ctx)
                elif section == "usage":
                    text = await _account_usage_text(db, user, ctx)
                elif section == "credit":
                    text = _account_credit_text(ctx)
                elif section == "transactions":
                    text = _account_transactions_text(ctx)
                elif section == "referral":
                    text = await _account_referral_text(db, user, context)
                else:
                    text = _account_home_text(ctx)

            await _safe_callback_edit(query, text, reply_markup=_account_kb(section, ctx))
            return

        if data == "account_set_name":
            _begin_mode(context, "asking_name")
            context.user_data["account_set_name_return"] = True
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text("\u0627\u0633\u0645 \u062c\u062f\u06cc\u062f\u062a \u0631\u0648 \u0628\u0646\u0648\u06cc\u0633:", reply_markup=_cancel_reply_kb())
            return

        if data in ("account_topup_start", "toman_topup_start"):
            await cmd_toman_topup(update, context)
            return

        if data == "account_promo_start":
            _begin_mode(context, "awaiting_account_promo_code")
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(
                "\U0001f381 \u06a9\u062f \u062a\u062e\u0641\u06cc\u0641 \u062e\u0648\u062f \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:\n\n"
                "\u06a9\u062f \u0631\u0627 \u062a\u0627\u06cc\u067e \u06a9\u0646 \u06cc\u0627 \u062f\u06a9\u0645\u0647 \u0644\u063a\u0648 \u0631\u0627 \u0628\u0632\u0646.",
                reply_markup=_cancel_reply_kb(),
            )
            return

        if data == "account_referral_copy":
            async with async_session() as db:
                user = await get_user(db, uid, query.from_user.first_name or "", query.from_user.username or "")
                campaign = None
                if user.referral_campaign_id:
                    campaign = (await db.execute(select(ReferralCampaign).where(ReferralCampaign.id == user.referral_campaign_id))).scalar_one_or_none()
                if not campaign:
                    campaign = ReferralCampaign(
                        code=f"ref_u{user.id}_{user.telegram_user_id}",
                        description=f"Referral link for user {user.id}",
                        created_by_user_id=user.id,
                        is_active=True,
                    )
                    db.add(campaign)
                    await db.flush()
                    user.referral_campaign_id = campaign.id
                    await db.commit()

            bot_username = context.bot.username or "jgpti_bot"
            referral_link = f"https://t.me/{bot_username}?start={campaign.code}"
            await query.answer("\u0644\u06cc\u0646\u06a9 \u062f\u0639\u0648\u062a \u06a9\u067e\u06cc \u0634\u062f!")
            await query.message.reply_text(
                f"\U0001f517 \u0644\u06cc\u0646\u06a9 \u062f\u0639\u0648\u062a \u0634\u0645\u0627:\n\n{referral_link}\n\n"
                f"\u0627\u06cc\u0646 \u0644\u06cc\u0646\u06a9 \u0631\u0627 \u0628\u0631\u0627\u06cc \u062f\u0648\u0633\u062a\u0627\u0646\u062a\u0627\u0646 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f.",
            )
            return

        if data == "topup_method_bale":
            await _handle_topup_method_bale(update, context)
            return

        if data == "topup_method_card":
            await _handle_topup_method_card(update, context)
            return

        if data == "share_contact_request":
            try: await query.message.delete()
            except: pass
            await query.message.reply_text("\u0634\u0645\u0627\u0631\u0647 \u062a\u0645\u0627\u0633\u062a \u0631\u0648 \u0628\u0641\u0631\u0633\u062a \u06cc\u0627 \u0647\u0645\u06cc\u0646\u062c\u0627 \u062a\u0627\u06cc\u067e \u06a9\u0646:", reply_markup=_contact_request_kb())
            return

        if data == "just_name":
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text("\u0627\u06cc\u0646 \u06af\u0632\u06cc\u0646\u0647 \u062d\u0630\u0641 \u0634\u062f. \u0644\u0637\u0641\u0627\u064b \u0634\u0645\u0627\u0631\u0647 \u062a\u0645\u0627\u0633 \u0631\u0648 \u0628\u0641\u0631\u0633\u062a.")
            return

        if data == "cancel_admin_delete":
            await query.message.reply_text("\u062d\u0630\u0641 \u0644\u063a\u0648 \u0634\u062f.", reply_markup=ADMIN_KB)
            return

        if data.startswith("delconfirm_"):
            if uid != ADMIN_ID:
                await query.message.reply_text("\u0641\u0642\u0637 \u0627\u062f\u0645\u06cc\u0646")
                return
            parts = data.split("_", 2)
            if len(parts) != 3:
                await query.message.reply_text("\u274c \u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0646\u0627\u0645\u0639\u062a\u0628\u0631")
                return
            kind = parts[1]
            try:
                entity_id = int(parts[2])
            except ValueError:
                await query.message.reply_text("\u274c \u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0646\u0627\u0645\u0639\u062a\u0628\u0631")
                return
            async with async_session() as db:
                try:
                    if kind == "prov":
                        row = (await db.execute(select(Provider).where(Provider.id == entity_id))).scalar_one_or_none()
                        if not row:
                            await query.message.reply_text("\u067e\u0631\u0648\u0627\u06cc\u062f\u0631 \u067e\u06cc\u062f\u0627 \u0646\u0634\u062f.")
                            return
                        name = row.name
                        await db.delete(row)
                        await db.commit()
                        await query.message.reply_text(f"\U0001f5d1 \u062d\u0630\u0641 \u0634\u062f: {name}", reply_markup=ADMIN_KB)
                        return
                    if kind == "model":
                        row = (await db.execute(select(DBModel).where(DBModel.id == entity_id))).scalar_one_or_none()
                        if not row:
                            await query.message.reply_text("\u0645\u062f\u0644 \u067e\u06cc\u062f\u0627 \u0646\u0634\u062f.")
                            return
                        name = row.display_name or row.name
                        await db.delete(row)
                        await db.commit()
                        await query.message.reply_text(f"\U0001f5d1 \u062d\u0630\u0641 \u0634\u062f: {name}", reply_markup=ADMIN_KB)
                        return
                    await query.message.reply_text("\u274c \u0646\u0648\u0639 \u062d\u0630\u0641 \u0646\u0627\u0645\u0639\u062a\u0628\u0631\u0647")
                except IntegrityError:
                    await db.rollback()
                    await query.message.reply_text("\u274c \u062d\u0630\u0641 \u0627\u0646\u062c\u0627\u0645 \u0646\u0634\u062f \u0686\u0648\u0646 \u0631\u06a9\u0648\u0631\u062f \u0648\u0627\u0628\u0633\u062a\u0647 \u0648\u062c\u0648\u062f \u062f\u0627\u0631\u062f.")
            return

    except Exception as e:
        logger.exception(f"Callback error: {str(e)}")
        try:
            await query.answer("\u062e\u0637\u0627\u06cc\u06cc \u0631\u062e \u062f\u0627\u062f.")
        except Exception:
            pass
    finally:
        await _mark_update_completed(update)



async def handle_scenario_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        try:
            await query.answer()
        except Exception as exc:
            logger.warning("Scenario callback answer failed: %s", exc)
        data = query.data
        scenario_id_str = data.split("_")[-1]
        if not scenario_id_str.isdigit():
            return
        scenario_id = int(scenario_id_str)
        
        async with async_session() as db:
            scenario = await db.get(BotStartScenario, scenario_id)
            if not scenario:
                await query.message.reply_text("این سناریو دیگر در دسترس نیست.")
                return
            
            # Create a mock update to simulate user sending the prompt
            # Call handle_message to process it via LLM with forced text
            await handle_message(_CallbackAsMessageUpdate(update), context, forced_text=scenario.prompt)
    finally:
        await _mark_update_completed(update)


async def handle_admin_btn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        try:
            await query.answer()
        except Exception as exc:
            logger.warning("Admin prompt button callback answer failed: %s", exc)
        data = query.data
        btn_id_str = data.split("_")[-1]
        if not btn_id_str.isdigit():
            return
        btn_id = int(btn_id_str)

        async with async_session() as db:
            btn = await db.get(AdminMessageButton, btn_id)
            if not btn:
                await query.message.reply_text("این دکمه دیگر فعال نیست.")
                return
            if not (btn.prompt or "").strip():
                await query.message.reply_text("پرامپت این دکمه خالی است.")
                return

            # Call handle_message to process it via LLM with forced text
            await handle_message(_CallbackAsMessageUpdate(update), context, forced_text=btn.prompt)
    finally:
        await _mark_update_completed(update)


# ══════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════
async def _require_admin_message(update: Update) -> bool:
    if update.effective_user.id == ADMIN_ID:
        return True
    await update.message.reply_text("فقط ادمین")
    return False


def _admin_delete_confirm_kb(kind: str, entity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید حذف", callback_data=f"delconfirm_{kind}_{entity_id}"),
            InlineKeyboardButton("❌ لغو", callback_data="cancel_admin_delete"),
        ]
    ])


async def _admin_conversation_cancel_if_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not _is_navigation_or_command(update.message.text):
        return False
    admin_temp.pop(update.effective_user.id, None)
    _reset_ephemeral_state(context, clear_pending=True)
    await update.message.reply_text("فرآیند لغو شد.", reply_markup=ADMIN_KB)
    return True


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _reset_ephemeral_state(context, clear_pending=True)
    if not await _require_admin_message(update):
        return
    async with async_session() as db:
        p_count = (await db.execute(select(func.count(Provider.id)))).scalar()
        m_count = (await db.execute(select(func.count(DBModel.id)))).scalar()
        u_count = (await db.execute(select(func.count(UserPreference.id)))).scalar()
        emb_config = (await db.execute(select(EmbeddingConfig).where(EmbeddingConfig.is_active == True))).scalar_one_or_none()
        emb_info = f"{emb_config.model} ({emb_config.provider})" if emb_config else "تنظیم نشده (پیش‌فرض: gemini-embedding-001)"
        sys_prompt = await get_system_prompt(db)
        preview = sys_prompt[:60] + "..." if len(sys_prompt) > 60 else sys_prompt
        m_count = (await db.execute(select(func.count(DBModel.id)))).scalar()
        u_count = (await db.execute(select(func.count(UserPreference.id)))).scalar()
        # Show current system prompt
        sys_prompt = await get_system_prompt(db)
        preview = sys_prompt[:100] + "..." if len(sys_prompt) > 100 else sys_prompt
    await update.message.reply_text(f"🔧 مدیریت\n\nپروایدر: {p_count} | مدل: {m_count} | یوزر: {u_count}\n🔮 Embedding: {emb_info}\n\n📝 سیستم پرامپت:\n{preview}", reply_markup=ADMIN_KB)

async def admin_tools_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    async with async_session() as db:
        text = await _build_tools_summary_text(db)
    await update.message.reply_text(text, reply_markup=_tools_menu_kb())

async def admin_show_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    async with async_session() as db:
        text, kb = await _build_prompt_admin_text_and_kb(db)
    chunks = _chunk_text(text)
    await update.message.reply_text(chunks[0], reply_markup=kb)
    for chunk in chunks[1:]:
        await update.message.reply_text(chunk)

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    async with async_session() as db:
        result = await db.execute(select(UserPreference))
        users = result.scalars().all()
    if not users:
        await update.message.reply_text("هیچ یوزری نیست")
        return
    text = "👥 یوزرها:\n\n"
    for u in users:
        admin_mark = "[ادمین]" if u.is_admin else ""
        name = u.preferred_name or u.first_name or "?"
        text += f"{u.telegram_user_id}: {name} {admin_mark}\n"
    for chunk in _chunk_text(text):
        await update.message.reply_text(chunk)


async def admin_pending_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending payment requests for admin review."""
    if update.effective_user.id != ADMIN_ID:
        return
    async with async_session() as db:
        from app.models import PaymentRequest
        pending = (await db.execute(
            select(PaymentRequest)
            .where(PaymentRequest.status == "pending")
            .order_by(PaymentRequest.created_at.desc())
            .limit(20)
        )).scalars().all()

    if not pending:
        await update.message.reply_text("درخواست پرداخت معلقی وجود ندارد.", reply_markup=ADMIN_KB)
        return

    text_lines = ["💳 درخواست‌های پرداخت معلق:\n"]
    for req in pending:
        ptype = "شارژ" if req.payment_type == "topup" else "اشتراک"
        text_lines.append(
            f"#{req.id} | {_format_toman(int(req.amount_toman or 0))} | {ptype} | "
            f"یوزر {req.user_id}\n"
            f"تاریخ: {format_persian(req.created_at, '%Y-%m-%d %H:%M')}"
        )

    for chunk in _chunk_text("\n".join(text_lines)):
        await update.message.reply_text(chunk, reply_markup=ADMIN_KB)


async def admin_embedding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current embedding config and allow editing."""
    if update.effective_user.id != ADMIN_ID:
        return
    async with async_session() as db:
        emb = await _get_emb_config(db)
    if emb:
        text = f"🔮 تنظیمات Embedding:\n\n"
        text += f"مدل: {emb.model}\n"
        text += f"پروایدر: {emb.provider}\n"
        text += f"API Key: {'✅ ست شده' if emb.api_key else '❌'}\n"
        text += f"Base URL: {emb.base_url}\n"
        text += f"فعال: {'✅' if emb.is_active else '❌'}\n"
    else:
        text = "🔮 تنظیمات Embedding:\n\nتنظیم نشده — از پیش‌فرض استفاده میشه\nمدل پیش‌فرض: gemini-embedding-001"
    buttons = [
        [InlineKeyboardButton("✏️ تغییر مدل", callback_data="emb_set_model")],
        [InlineKeyboardButton("✏️ تغییر API Key", callback_data="emb_set_key")],
        [InlineKeyboardButton("✏️ تغییر Base URL", callback_data="emb_set_url")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def admin_delete_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    async with async_session() as db:
        result = await db.execute(select(Provider))
        providers = result.scalars().all()
    if not providers:
        await update.message.reply_text("پروایدری نیست", reply_markup=ADMIN_KB)
        return
    buttons = []
    for p in providers:
        buttons.append([InlineKeyboardButton(f"🗑 {p.name}", callback_data=f"delprov_{p.id}")])
    await update.message.reply_text("🗑 حذف پروایدر:", reply_markup=InlineKeyboardMarkup(buttons))

async def admin_delete_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    async with async_session() as db:
        result = await db.execute(select(DBModel))
        models = result.scalars().all()
    if not models:
        await update.message.reply_text("مدلی نیست", reply_markup=ADMIN_KB)
        return
    buttons = []
    for m in models:
        buttons.append([InlineKeyboardButton(f"🗑 {m.display_name or m.name}", callback_data=f"delmodel_{m.id}")])
    await update.message.reply_text("🗑 حذف مدل:", reply_markup=InlineKeyboardMarkup(buttons))

async def admin_set_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    # Get text after command or from message
    text = update.message.text
    if text.startswith("/setprompt"):
        text = text.replace("/setprompt", "").strip()
    elif context.user_data.get("editing_prompt"):
        context.user_data.pop("editing_prompt", None)
    else:
        text = text.strip()
    if not text:
        _begin_mode(context, "editing_prompt")
        await update.message.reply_text("📝 پرامپت جدید رو بفرست:")
        return
    async with async_session() as db:
        result = await db.execute(select(SystemPrompt).where(SystemPrompt.name == "default"))
        prompt = result.scalar_one_or_none()
        if prompt:
            prompt.content = text
        else:
            prompt = SystemPrompt(name="default", content=text, is_active=True)
            db.add(prompt)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            await update.message.reply_text("❌ ذخیره پرامپت انجام نشد. دوباره تلاش کن.", reply_markup=ADMIN_KB)
            return
    await update.message.reply_text("✅ سیستم پرامپت آپدیت شد", reply_markup=ADMIN_KB)


async def admin_set_start_intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = " ".join(context.args or []).strip()
    if not text:
        _begin_mode(context, "editing_start_intro")
        await update.message.reply_text(
            "📝 متن معرفی /start رو بفرست:\n\n"
            "این متن برای کاربر بعد از اجرای /start نمایش داده میشه."
        )
        return
    async with async_session() as db:
        try:
            await _upsert_telegram_start_intro_prompt(db, text)
        except ValueError:
            await update.message.reply_text("❌ متن خالیه", reply_markup=ADMIN_KB)
            return
    await update.message.reply_text("✅ پیام معرفی /start آپدیت شد", reply_markup=ADMIN_KB)


async def admin_clear_start_intro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    async with async_session() as db:
        await _clear_telegram_start_intro_prompt(db)
    await update.message.reply_text("✅ پیام معرفی /start حذف شد", reply_markup=ADMIN_KB)


async def admin_list_providers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return
    async with async_session() as db:
        result = await db.execute(select(Provider))
        for p in result.scalars().all():
            s = "✅" if p.is_active else "❌"
            await update.message.reply_text(f"{s} {p.name}\n{p.base_url}")

async def admin_list_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return
    async with async_session() as db:
        from app.services.toman_billing_service import get_or_create_subscription_config, DEFAULT_USD_TO_TOMAN_RATE
        config = await get_or_create_subscription_config(db)
        rate = int(config.usd_to_toman_rate) if config else DEFAULT_USD_TO_TOMAN_RATE
        result = await db.execute(select(DBModel))
        result2 = await db.execute(select(Provider))
        prov_map = {p.id: p.name for p in result2.scalars().all()}
        for m in result.scalars().all():
            s = "✅" if m.is_active else "❌"
            t_in = int(round(float(m.pricing_input or 0.0) * rate))
            t_out = int(round(float(m.pricing_output or 0.0) * rate))
            await update.message.reply_text(
                f"{s} {m.display_name or m.name}\n"
                f"{prov_map.get(m.provider_id, '?')} | "
                f"${m.pricing_input}/${m.pricing_output} per 1M "
                f"(≈ {_format_toman(t_in)} / {_format_toman(t_out)})"
            )


# Admin conversations (same as before)
async def admin_start_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END
    admin_temp[update.effective_user.id] = {}
    await update.message.reply_text("➕ پروایدر\n\nنام:")
    return ADD_PROV_NAME

async def admin_prov_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    admin_temp.setdefault(update.effective_user.id, {})["name"] = update.message.text
    await update.message.reply_text("Base URL:")
    return ADD_PROV_URL

async def admin_prov_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    admin_temp.setdefault(update.effective_user.id, {})["base_url"] = update.message.text
    await update.message.reply_text("API Key:")
    return ADD_PROV_KEY

async def admin_prov_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    uid = update.effective_user.id
    data = admin_temp.pop(uid, {})
    async with async_session() as db:
        try:
            prov = Provider(name=data.get("name", ""), base_url=data.get("base_url", ""), api_key=update.message.text, is_active=True)
            db.add(prov)
            await db.commit()
            await db.refresh(prov)
        except IntegrityError:
            await db.rollback()
            await update.message.reply_text("❌ ذخیره نشد: نام پروایدر تکراری است.", reply_markup=ADMIN_KB)
            return ConversationHandler.END
    await update.message.reply_text(f"✅ {prov.name}", reply_markup=ADMIN_KB)
    return ConversationHandler.END

async def admin_start_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END
    async with async_session() as db:
        result = await db.execute(select(Provider).where(Provider.is_active == True))
        providers = result.scalars().all()
        if not providers:
            await update.message.reply_text("❌ اول پروایدر بساز!", reply_markup=ADMIN_KB)
            return ConversationHandler.END
        prov_list = "\n".join([f"{p.id}: {p.name}" for p in providers])
        admin_temp[update.effective_user.id] = {"providers": {p.id: p.name for p in providers}}
    await update.message.reply_text(f"➕ مدل\n\nنام:\n\nپروایدرها:\n{prov_list}")
    return ADD_MODEL_NAME

async def admin_model_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    admin_temp.setdefault(update.effective_user.id, {})["model_name"] = update.message.text
    await update.message.reply_text("نام نمایشی یا skip:")
    return ADD_MODEL_DISPLAY

async def admin_model_display(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    uid = update.effective_user.id
    admin_temp.setdefault(uid, {})["display_name"] = None if update.message.text.lower() == "skip" else update.message.text
    providers = admin_temp.get(uid, {}).get("providers", {})
    await update.message.reply_text("ID پروایدر:\n" + "\n".join([f"{pid}: {pname}" for pid, pname in providers.items()]))
    return ADD_MODEL_PROVIDER

async def admin_model_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    uid = update.effective_user.id
    try:
        pid = int(update.message.text)
    except ValueError:
        await update.message.reply_text("عدد بفرست")
        return ADD_MODEL_PROVIDER
    if pid not in admin_temp.get(uid, {}).get("providers", {}):
        await update.message.reply_text("ID نامعتبر")
        return ADD_MODEL_PROVIDER
    admin_temp.setdefault(uid, {})["provider_id"] = pid
    await update.message.reply_text("قیمت ورودی ($/1M) — کاربر معادل تومانی را می‌بیند:")
    return ADD_MODEL_PRICE_IN

async def admin_model_price_in(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    try:
        admin_temp.setdefault(update.effective_user.id, {})["pricing_input"] = float(update.message.text)
    except ValueError:
        return ADD_MODEL_PRICE_IN
    await update.message.reply_text("قیمت خروجی ($/1M) — کاربر معادل تومانی را می‌بیند:")
    return ADD_MODEL_PRICE_OUT

async def admin_model_price_out(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    try:
        admin_temp.setdefault(update.effective_user.id, {})["pricing_output"] = float(update.message.text)
    except ValueError:
        return ADD_MODEL_PRICE_OUT
    await update.message.reply_text("Context window یا skip:")
    return ADD_MODEL_CONTEXT

async def admin_model_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin_message(update):
        return ConversationHandler.END
    if await _admin_conversation_cancel_if_navigation(update, context):
        return ConversationHandler.END
    uid = update.effective_user.id
    text = update.message.text
    cw = 128000 if text.lower() == "skip" else int(text) if text.isdigit() else 128000
    data = admin_temp.pop(uid, {})
    async with async_session() as db:
        try:
            model = DBModel(
                name=data.get("model_name", ""), display_name=data.get("display_name"),
                provider_id=data.get("provider_id"), pricing_input=data.get("pricing_input", 0),
                pricing_output=data.get("pricing_output", 0), context_window=cw, is_active=True,
            )
            db.add(model)
            await db.commit()
            await db.refresh(model)
        except IntegrityError:
            await db.rollback()
            await update.message.reply_text("❌ ذخیره نشد: نام مدل تکراری است.", reply_markup=ADMIN_KB)
            return ConversationHandler.END
    await update.message.reply_text(f"✅ {model.display_name or model.name}", reply_markup=ADMIN_KB)
    return ConversationHandler.END

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_temp.pop(update.effective_user.id, None)
    _reset_ephemeral_state(context, clear_pending=True)
    uid = update.effective_user.id
    await update.message.reply_text("برگشتیم به منوی اصلی.", reply_markup=main_kb(uid == ADMIN_ID))
    return ConversationHandler.END

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _reset_ephemeral_state(context, clear_pending=True)
    uid = update.effective_user.id
    await update.message.reply_text("🔙 منوی اصلی", reply_markup=main_kb(uid == ADMIN_ID))


# ══════════════════════════════════════
#  CONTACT SHARING (for new user onboarding)
# ══════════════════════════════════════
async def _save_phone_onboarding_and_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    uid: int,
    raw_phone: str,
) -> None:
    phone = normalize_phone_number(raw_phone) or (raw_phone or "").strip()
    if not phone:
        await update.message.reply_text("شماره معتبر نبود. لطفاً دوباره بفرست یا تایپ کن.")
        return

    async with async_session() as db:
        current_user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        user = current_user
        existing_user = await get_user_by_phone(db, phone)
        if existing_user and existing_user.id != current_user.id:
            holder = (await db.execute(select(UserPreference).where(UserPreference.telegram_user_id == uid))).scalar_one_or_none()
            if holder and holder.id != existing_user.id:
                holder.telegram_user_id = None
                await db.flush()
            user = existing_user
            user.telegram_user_id = uid
            user.first_name = update.effective_user.first_name or user.first_name
            user.username = update.effective_user.username or user.username
        user.phone_number = phone
        was_pending = not _user_onboarding_completed(user)
        if not user.is_admin:
            if _missing_preferred_name(user):
                user.account_status = "pending_name"
            else:
                _mark_onboarding_complete(user)
                if was_pending:
                    await _log_referral_event(db, user, "signup")
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            await update.message.reply_text("ثبت شماره انجام نشد. لطفاً یک‌بار دیگر تلاش کن.")
            return
        needs_name = (not user.is_admin) and _missing_preferred_name(user)
        restored_existing = existing_user is not None and existing_user.id != current_user.id

    if needs_name:
        _begin_mode(context, "asking_name")
        await update.message.reply_text("✅ شماره تماس ثبت شد.\nحالا دوست داری چی صدات کنم؟")
        return
    if restored_existing:
        await update.message.reply_text("✅ حسابت بازیابی شد.", reply_markup=main_kb(uid == ADMIN_ID))
    else:
        await update.message.reply_text("✅ شماره تماس ثبت شد.", reply_markup=main_kb(uid == ADMIN_ID))


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """When user shares contact during onboarding, save phone and ask preferred name."""
    uid = update.effective_user.id
    contact = update.message.contact
    if not contact:
        return
    if not await _claim_update_once(update):
        return
    if contact.user_id and contact.user_id != uid and not _is_bale_platform():
        await update.message.reply_text("شماره باید متعلق به خودت باشه.")
        return
    if contact.user_id and contact.user_id != uid and _is_bale_platform():
        logger.warning(
            "Bale contact user_id mismatch tolerated: update_uid=%s contact_user_id=%s",
            uid,
            contact.user_id,
        )
    await _save_phone_onboarding_and_reply(
        update,
        context,
        uid=uid,
        raw_phone=update.message.contact.phone_number,
    )
    await _mark_update_completed(update)



# ══════════════════════════════════════
#  FILE/DOCUMENT HANDLER — Upload PDFs, TXTs, etc.
# ══════════════════════════════════════

async def _background_index_with_notification(
    bot,
    chat_id: int,
    project_id: int | None,
    document_id: int,
    file_path: str,
    uid: int,
    update_id: int,
    file_unique_id: str,
    estimated_cost: float,
    estimated_tokens: int,
    filename: str,
    api_key: str = None,
    model: str = None,
    provider: str = "google",
    base_url: str = None,
    status_message_obj: Message = None,
    target_chat_id: int | None = None,
    after_indexing=None,
    pre_read_text: str = None,
):
    """
    Background task for Telegram bot indexing.
    Runs indexing, charges credits, updates usage event, and notifies user.
    """
    progress_data = {
        "phase": "starting",
        "current": 0,
        "total": 0,
        "last_update": time.time()
    }

    async def progress_cb(phase, current, total):
        progress_data.update({
            "phase": phase,
            "current": current,
            "total": total,
            "last_update": time.time()
        })

    spinner_task = None
    typing_task = None

    if status_message_obj:
        async def spinner():
            frames = ["🕛", "🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚"]
            i = 0
            while True:
                try:
                    phase = progress_data["phase"]
                    current = progress_data["current"]
                    total = progress_data["total"]

                    phase_text = "در حال شروع..."
                    if phase == "reading":
                        phase_text = "🔍 در حال استخراج و تحلیل محتوا..."
                    elif phase == "chunking":
                        phase_text = "✂️ در حال تقسیم‌بندی متن به قطعات کوچک..."
                    elif phase == "indexing":
                        if total > 0:
                            phase_text = f"🏗 در حال ایندکس کردن: {current} از {total} قطعه"
                        else:
                            phase_text = f"🏗 در حال ایندکس کردن قطعات ({current})..."

                    status_msg = (
                        f"{frames[i % len(frames)]} {phase_text}\n"
                        f"📄 فایل: {filename}\n\n"
                        f"این کار در پس‌زمینه انجام می‌شود و شما می‌توانید به کارهای دیگر خود بپردازید. ⏳"
                    )

                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_message_obj.message_id,
                        text=status_msg
                    )
                    i += 1
                    await asyncio.sleep(2.0)
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(2.0)
        
        spinner_task = asyncio.create_task(spinner())

        async def typing_loop():
            while True:
                try:
                    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                    await asyncio.sleep(4.5)
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(5.0)
        
        typing_task = asyncio.create_task(typing_loop())

    try:
        # 1. Run indexing using the shared service
        await background_index_document(
            project_id=project_id,
            document_id=document_id,
            file_path=file_path,
            api_key=api_key,
            model=model,
            provider=provider,
            base_url=base_url,
            progress_callback=progress_cb,
            chat_id=target_chat_id,
            pre_read_text=pre_read_text
        )
        
        if spinner_task:
            spinner_task.cancel()
        if typing_task:
            typing_task.cancel()

        # 2. Charge credits
        async with async_session() as db:
            doc = await db.get(Document, document_id)
            user = await get_user(db, uid)
            
            request_id = f"telegram:{update_id}:rag:{project_id}:{document_id}:{file_unique_id}"
            usage_event = (
                await db.execute(
                    select(UsageEvent).where(UsageEvent.request_id == request_id)
                )
            ).scalar_one_or_none()

            # If not found by project_id, try by target_chat_id
            if not usage_event and target_chat_id:
                request_id_chat = f"telegram:{update_id}:rag:chat_{target_chat_id}:{document_id}:{file_unique_id}"
                usage_event = (
                    await db.execute(
                        select(UsageEvent).where(UsageEvent.request_id == request_id_chat)
                    )
                ).scalar_one_or_none()

            if usage_event:
                usage_event.status = "completed"
                usage_event.completed_at = _utcnow()
                usage_event.units = doc.chunk_count

            from app.services.toman_billing_service import charge_generic_usage_toman
            await charge_generic_usage_toman(
                db,
                user=user,
                cost_usd=estimated_cost,
                entry_type="rag_embedding",
                reason="telegram document indexing",
                usage_event_id=usage_event.id if usage_event else None,
                idempotency_key=f"usage:{usage_event.id}:charge" if usage_event else None,
                metadata={
                    "project_id": project_id,
                    "filename": filename,
                    "chunk_count": doc.chunk_count,
                    "estimated_tokens": estimated_tokens,
                    "embedding_model": model,
                },
            )
            await db.commit()

            # 3. Notify user with persistent keyboard
            if after_indexing:
                if status_message_obj:
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_message_obj.message_id,
                            text=f"✅ فایل {filename} پردازش شد. در حال آماده‌سازی پاسخ به کپشن..."
                        )
                    except Exception:
                        pass
                await after_indexing()
                await _mark_update_completed_by_id(update_id)
                return

            success_msg = f"✅ فایل {filename} با موفقیت پردازش و در حافظه ایندکس شد. ({doc.chunk_count} قطعه)"
            kb = upload_queue_kb()
            if status_message_obj:
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=status_message_obj.message_id, text=success_msg, reply_markup=kb)
                except Exception:
                    await bot.send_message(chat_id=chat_id, text=success_msg, reply_markup=kb)
            else:
                await bot.send_message(chat_id=chat_id, text=success_msg, reply_markup=kb)
            await _mark_update_completed_by_id(update_id)

    except Exception as e:
        if spinner_task:
            spinner_task.cancel()
        if typing_task:
            typing_task.cancel()
        logger.exception(f"Error in background indexing for {filename}")
        error_msg = f"❌ متاسفانه در پردازش فایل {filename} خطایی رخ داد: {str(e)}\n\nمی‌توانی لیست را پاک کنی یا با بقیه فایل‌ها ادامه دهی 👇"
        kb = upload_queue_kb()
        if status_message_obj:
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=status_message_obj.message_id, text=error_msg, reply_markup=kb)
            except Exception:
                await bot.send_message(chat_id=chat_id, text=error_msg, reply_markup=kb)
        else:
            try:
                await bot.send_message(chat_id=chat_id, text=error_msg, reply_markup=kb)
            except:
                pass
        await _mark_update_completed_by_id(update_id)

ALBUM_STATUS_MSG = {} # mg_id -> Message object

ALBUM_STATUS_MSG = {} # mg_id -> Message object

ALBUM_STATUS_MSG = {} # mg_id -> Message object

def upload_queue_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["✅ اتمام آپلود و شروع گفتگو"],
        ["❌ انصراف و پاکسازی لیست"]
    ], resize_keyboard=True)

async def _handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads with a persistent Upload Mode."""
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    doc = update.message.document
    if not doc: return
    if not await _claim_update_once(update): return

    # Check if user is sending a receipt as a document
    if context.user_data.get("awaiting_card_receipt"):
        await _handle_card_receipt_as_document(update, context, doc)
        return

    if context.user_data.get("awaiting_subscription_card_receipt"):
        await _handle_subscription_receipt_as_document(update, context, doc)
        return

    await _register_album_update(update)
    task = _register_user_task(chat_id)
    use_rag = False
    try:
        filename = doc.file_name or "unknown"
        file_size = doc.file_size or 0
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mg_id = update.message.media_group_id

        async with async_session() as db:
            user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            if not await _ensure_onboarding_or_prompt(update, context, user=user): return
            project_id = user.current_project_id
            current_chat_id = user.current_chat_id
            project_upload_mode = bool(context.user_data.get("project_upload_mode"))
            explicit_upload_requested = bool(context.user_data.get("awaiting_project_file_upload")) or project_upload_mode
            user_has_pro_access = await _is_pro_or_admin(db, user)

        # ─── Album & Status Message Consolidation ───
        processing_msg = None
        if mg_id:
            async with ALBUM_LOCK:
                if mg_id in ALBUM_STATUS_MSG: processing_msg = ALBUM_STATUS_MSG[mg_id]
                else:
                    processing_msg = await update.message.reply_text("📥 در حال دریافت فایل‌ها...")
                    ALBUM_STATUS_MSG[mg_id] = processing_msg
        else:
            processing_msg = await update.message.reply_text(f"📥 {filename}\n\n📄 در حال پردازش...")

        # ─── Format & Download ───
        is_audio = ext in DOCUMENT_AUDIO_EXTENSIONS
        SUPPORTED_KB_EXTS = {"pdf", "txt", "md", "csv", "docx", "xlsx", "pptx", "html", "jpg", "jpeg", "png", "webp", "json", "py", "js", "sql"}
        if not is_audio and ext not in SUPPORTED_KB_EXTS:
            await _safe_edit_or_reply(update, processing_msg, f"⚠️ فرمت {ext} پشتیبانی نمیشه.")
            return

        try:
            abs_dest_dir = os.path.abspath("./uploads/chat_files")
            os.makedirs(abs_dest_dir, exist_ok=True)
            file_path = os.path.join(abs_dest_dir, f"{int(time.time())}_{filename}")
            await _download_telegram_file(context, doc.file_id, file_path)
        except Exception as e:
            logger.error(f"Download failed for {filename}: {e}")
            platform_name = "بله" if BOT_PLATFORM == "bale" else "تلگرام"
            retry_cb = f"retry_dl_{int(time.time())}_{doc.file_id}"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 تلاش مجدد", callback_data=retry_cb)
            ]])
            await _safe_edit_or_reply(
                update,
                processing_msg,
                f"⚠️ این پیام مخصوص {platform_name} است.\n\n"
                f"❌ دانلود فایل از سرور {platform_name} ناموفق بود.\n"
                f"علت: اتصال به سرور {platform_name} قطع شده یا فایل در دسترس نیست.\n\n"
                f"🔸 اگر از وب‌سایت استفاده می‌کنید، فایل را مستقیماً در چت وب آپلود کنید.\n"
                f"🔸 اگر از ربات {platform_name} استفاده می‌کنید، دکمه زیر را بزنید یا فایل را دوباره بفرستید.",
                reply_markup=kb,
            )
            return

        if is_audio:
            await _handle_audio_doc_inline(update, context, user, project_id, current_chat_id, doc, file_path, filename, ext, explicit_upload_requested, processing_msg)
            return

        # ─── Process Decision ───
        from app.rag import _read_file
        file_text = ""
        is_large = file_size > 500 * 1024 # > 500KB is definitively large
        
        try:
            # Try to read text to see if it's small/readable
            if ext in ("txt", "md", "json", "py", "js", "sql", "csv"):
                file_text = await asyncio.to_thread(_read_file, file_path)
                if len(file_text) > 15000:
                    is_large = True
            elif not is_large:
                # Small PDF/Excel? Try reading it now to avoid RAG if possible
                file_text = await asyncio.to_thread(_read_file, file_path)
        except Exception as e:
            logger.warning(f"Initial read_file failed for {filename}: {e}")
            if not is_large:
                # If reading failed and it's small, it's probably better to try RAG (OCR/Better parsing)
                pass

        if is_large and not user_has_pro_access:
            await _send_pro_restriction_message(update, context)
            return

        # DECISION: RAG or Direct?
        # Only use RAG if: explicit for project, OR file is ACTUALLY large and a complex format
        use_rag = explicit_upload_requested or (is_large and ext in ("pdf", "docx", "xlsx", "pptx"))

        if use_rag:
            await _perform_rag_indexing(update, context, user, project_id, current_chat_id, doc, file_path, filename, file_size, ext, explicit_upload_requested, processing_msg, file_text=file_text)
        else:
            await _perform_direct_extraction(update, context, user, current_chat_id, doc, file_path, filename, file_text, ext, processing_msg)

    except Exception as e:
        logger.exception(f"Upload failed for {filename}: {e}")
        await _safe_edit_or_reply(update, processing_msg, "❌ خطایی در پردازش رخ داد.")
    finally:
        _unregister_user_task(chat_id, task)
        await _finish_album_update(update, context, handle_message)
        if update.message and update.message.media_group_id:
            await _mark_update_completed(update)
        # Mark update completed if not already done by a background task
        # RAG indexing logic handles its own completion marking in the background.
        if not use_rag:
            await _mark_update_completed(update)

async def _safe_edit_or_reply(update, msg, text):
    try:
        if msg: await msg.edit_text(text)
        else: await update.message.reply_text(text)
    except: pass

def _infer_mime_type(ext: str, filename: str) -> str:
    ext_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
        "txt": "text/plain", "md": "text/markdown", "json": "application/json",
        "csv": "text/csv", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "html": "text/html", "py": "text/x-python", "js": "application/javascript",
        "sql": "application/sql",
    }
    return ext_map.get(ext.lower(), "application/octet-stream")

async def _perform_direct_extraction(update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id, doc, file_path, filename, text, ext, processing_msg):
    mg_id = update.message.media_group_id
    async with async_session() as db:
        if not chat_id:
            chat = Chat(title="💬 چت جدید", model_id=user.current_model_id, user_preference_id=user.id)
            db.add(chat); await db.commit(); await db.refresh(chat)
            chat_id = chat.id; user.current_chat_id = chat.id; await db.commit()
        
        mime_type = _infer_mime_type(ext, filename)
        uploaded_file = await _record_uploaded_file(db, user=user, chat_id=chat_id, filename=filename, file_type=ext, mime_type=mime_type, size_bytes=doc.file_size, storage_path=file_path, status="completed")
        uploaded_file_id = uploaded_file.id
        
        # Only save a DB message for non-album items; album flow handles grouping
        if not mg_id:
            msg_content = f"[فایل: {filename} (ID={uploaded_file_id})]"
            db.add(Message(chat_id=chat_id, role="user", content=msg_content))
            await db.commit()
        else:
            await db.commit()

    if mg_id:
        await _register_album_update(update, extracted_text=text, file_id=uploaded_file_id, count_pending=False)
    else:
        if "pending_files_queue" not in context.user_data: context.user_data["pending_files_queue"] = []
        context.user_data["pending_files_queue"].append({"filename": filename, "text": text[:15000], "id": uploaded_file_id})
        
        caption = update.message.caption
        if caption:
            is_img = ext in ("jpg", "jpeg", "png", "webp")
            if is_img:
                forced_text = f"[عکس ارسال شده: ID={uploaded_file_id}]\n{caption}"
            else:
                forced_text = f"[فایل: {filename} (ID={uploaded_file_id})]\n{caption}"
            await handle_message(update, context, forced_text=forced_text, status_message_obj=processing_msg)
        else:
            q_len = len(context.user_data["pending_files_queue"])
            await _safe_edit_or_reply(update, processing_msg, f"✅ فایل {filename} دریافت شد ({q_len} فایل در لیست).\n\nمی‌تونی فایل‌های دیگه‌ای بفرستی یا با زدن دکمه زیر شروع به گفتگو کنی 👇", reply_markup=upload_queue_kb())

async def _perform_rag_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE, user, project_id, chat_id, doc, file_path, filename, file_size, ext, explicit_upload_requested, processing_msg, file_text: str = ""):
    from app.rag import _read_file
    try:
        if not file_text:
            file_text = await asyncio.to_thread(_read_file, file_path)
        estimated_tokens = _estimate_text_tokens(file_text)
    except:
        estimated_tokens = max(1, file_size // 4)

    async with async_session() as db:
        user = await get_user(db, user.telegram_user_id)
        if not chat_id and not project_id:
            chat = Chat(title="💬 چت جدید", model_id=user.current_model_id, user_preference_id=user.id)
            db.add(chat); await db.commit(); await db.refresh(chat)
            chat_id = chat.id; user.current_chat_id = chat.id; await db.commit()
            
        mime_type = _infer_mime_type(ext, filename)
        uploaded_file = await _record_uploaded_file(db, user=user, chat_id=chat_id, project_id=project_id, filename=filename, file_type=ext, mime_type=mime_type, size_bytes=file_size, storage_path=file_path, status="stored")
        uploaded_file_id = uploaded_file.id
        
        emb_config = (await db.execute(select(EmbeddingConfig).where(EmbeddingConfig.is_active == True))).scalar_one_or_none()
        cost = _embedding_cost_usd(emb_config, estimated_tokens)
        
        from app.models import Document
        doc_record = Document(project_id=project_id, chat_id=chat_id if not project_id else None, filename=filename, file_type=ext, file_path=file_path)
        db.add(doc_record)
        
        usage = await _create_usage_event(
            db,
            user=user,
            chat_id=chat_id,
            message_id=update.message.message_id,
            operation_type="rag_embedding",
            uploaded_file_id=uploaded_file_id,
            estimated_cost_usd=cost,
            request_id=f"tg:{update.update_id}:rag:{doc.file_unique_id}"
        )
        usage.status = "authorized"; await db.commit(); await db.refresh(doc_record)

    mg_id = update.message.media_group_id
    if mg_id:
        await _register_album_update(update, file_id=uploaded_file_id, count_pending=False, rag=True)
    else:
        if "pending_files_queue" not in context.user_data: context.user_data["pending_files_queue"] = []
        context.user_data["pending_files_queue"].append({"filename": filename, "id": uploaded_file_id, "rag": True})
        
        caption = update.message.caption
        if caption:
            await _safe_edit_or_reply(
                update,
                processing_msg,
                f"📄 {filename}\n\nدر حال پردازش فایل... بعد از کامل شدن پردازش، به کپشن پاسخ می‌دم."
            )
        else:
            q_len = len(context.user_data["pending_files_queue"])
            await _safe_edit_or_reply(update, processing_msg, f"✅ {filename} (فایل سنگین) آماده شد ({q_len} فایل در لیست).\n\nمی‌تونی فایل‌های دیگه‌ای بفرستی یا با زدن دکمه زیر شروع به گفتگو کنی 👇", reply_markup=upload_queue_kb())

    after_indexing = None
    if update.message.caption and not mg_id:
        async def answer_caption_after_indexing():
            forced_text = f"[فایل: {filename} (ID={uploaded_file_id})]\n{update.message.caption}"
            await handle_message(update, context, forced_text=forced_text, status_message_obj=processing_msg)
        after_indexing = answer_caption_after_indexing


    asyncio.create_task(_background_index_with_notification(bot=context.bot, chat_id=update.effective_chat.id, project_id=project_id, document_id=doc_record.id, file_path=file_path, uid=user.telegram_user_id, update_id=update.update_id, file_unique_id=doc.file_unique_id, estimated_cost=cost, estimated_tokens=estimated_tokens, filename=filename, api_key=emb_config.api_key if emb_config else None, model=emb_config.model if emb_config else None, provider=emb_config.provider if emb_config else "google", base_url=emb_config.base_url if emb_config else None, status_message_obj=processing_msg, target_chat_id=chat_id if not project_id else None, after_indexing=after_indexing, pre_read_text=file_text))

async def _handle_audio_doc_inline(update, context, user, project_id, chat_id, doc, file_path, filename, ext, explicit_upload, processing_msg):
    mime_type = (doc.mime_type or "audio/mp4").strip() or "audio/mp4"
    estimated_audio_seconds = _estimate_audio_duration_from_size(doc.file_size)
    async with async_session() as db: transcription_config = await _get_or_create_transcription_config(db)
    estimated_in_tokens = _estimate_audio_tokens(estimated_audio_seconds); estimated_out_tokens = 512
    cost = _transcription_cost_usd(transcription_config, estimated_in_tokens, estimated_out_tokens)
    transcript = await _execute_voice_transcription(update, context, uid=user.telegram_user_id, voice_file_id=doc.file_id, voice_file_unique_id=doc.file_unique_id, duration=estimated_audio_seconds, mime_type=mime_type, project_id=project_id, explicit_upload_requested=explicit_upload, project_upload_mode=False, processing_msg=processing_msg, transcription_config=transcription_config, estimated_cost=cost, estimated_in_tokens=estimated_in_tokens, estimated_out_tokens=estimated_out_tokens, voice_file_size=doc.file_size)
    if transcript and explicit_upload:
        transcript_path = file_path + ".txt"
        with open(transcript_path, "w", encoding="utf-8") as f: f.write(transcript)
        async with async_session() as db:
            emb = (await db.execute(select(EmbeddingConfig).where(EmbeddingConfig.is_active == True))).scalar_one_or_none()
            doc_record = Document(project_id=project_id, filename=filename, file_type="audio", file_path=file_path)
            db.add(doc_record); await db.commit(); await db.refresh(doc_record)
            asyncio.create_task(_background_index_with_notification(bot=context.bot, chat_id=chat_id, project_id=project_id, document_id=doc_record.id, file_path=transcript_path, uid=user.telegram_user_id, update_id=update.update_id, file_unique_id=doc.file_unique_id, estimated_cost=0, estimated_tokens=_estimate_text_tokens(transcript), filename=filename, api_key=emb.api_key if emb else None, model=emb.model if emb else None, provider=emb.provider if emb else "google", base_url=emb.base_url if emb else None, status_message_obj=processing_msg, pre_read_text=transcript))
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photos.

    With caption -> treat caption as question, answer directly with vision.
    Without caption -> save photo, ask what they want to know.
    """
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    if not await _claim_update_once(update):
        return

    if context.user_data.get("awaiting_card_receipt"):
        await _handle_card_receipt_photo(update, context)
        return

    if context.user_data.get("awaiting_subscription_card_receipt"):
        await _handle_subscription_receipt_photo(update, context)
        return

    await _register_album_update(update)

    task = _register_user_task(chat_id)
    try:
        caption = update.message.caption or ""
        reserve_pending_photo = not caption and not update.message.media_group_id
        
        photo = update.message.photo[-1] if update.message.photo else None
        if not photo:
            return
    
        async with async_session() as db:
            user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            if not await _ensure_onboarding_or_prompt(update, context, user=user):
                return
            chat_id = user.current_chat_id
            if not chat_id:
                chat = Chat(
                    title="💬 چت جدید",
                    model_id=user.current_model_id,
                    project_id=user.current_project_id,
                    user_preference_id=user.id,
                )
                db.add(chat)
                await db.commit()
                await db.refresh(chat)
                user.current_chat_id = chat.id
                await db.commit()
                chat_id = chat.id
        
        processing_msg = await update.message.reply_text("📸 در حال دریافت عکس...")
        if reserve_pending_photo:
            _clear_pending_inputs(context)
            _reserve_pending_photo_context(context, chat_id=chat_id)
        # Absolute path for storage
        abs_upload_dir = os.path.abspath("./uploads/chat_photos")
        os.makedirs(abs_upload_dir, exist_ok=True)
        file_path = os.path.join(abs_upload_dir, f"{photo.file_unique_id}.jpg")
        
        try:
            await _download_telegram_file(context, photo.file_id, file_path)
        except Exception as e:
            if reserve_pending_photo:
                context.user_data.pop("pending_photo", None)
            retry_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تلاش مجدد", callback_data="retry_photo")]])
            logger.error(f"Photo download error: {str(e)}")
            # If admin, show the raw error for better debugging
            err_detail = f"\n(Error: {str(e)})" if uid == ADMIN_ID else ""
            platform_name = "بله" if _is_bale_platform() else "تلگرام"
            await processing_msg.edit_text(f"❌ مشکلی در دریافت عکس از {platform_name} پیش آمد.{err_detail}", reply_markup=retry_kb)
            return
        
        # Encode image for vision API
        try:
            image_b64 = _encode_image_to_base64(file_path)
        except Exception as e:
            if reserve_pending_photo:
                context.user_data.pop("pending_photo", None)
            logger.error(f"Photo processing error: {str(e)}")
            await processing_msg.edit_text("❌ مشکلی در آماده‌سازی عکس پیش آمد.")
            return
        async with async_session() as db:
            user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            uploaded_photo = await _record_uploaded_file(
                db,
                user=user,
                chat_id=chat_id,
                project_id=user.current_project_id,
                telegram_file_id=photo.file_id,
                telegram_file_unique_id=photo.file_unique_id,
                filename=f"{photo.file_unique_id}.jpg",
                mime_type="image/jpeg",
                file_type="jpg",
                size_bytes=photo.file_size or 0,
                storage_path=file_path,
                caption=caption or None,
                status="stored",
                metadata={"source": "telegram_photo"},
            )
            await db.commit()
            uploaded_photo_id = uploaded_photo.id

        if reserve_pending_photo:
            _finalize_pending_photo_context(
                context,
                file_path=file_path,
                image_b64=image_b64,
                uploaded_file_id=uploaded_photo_id,
            )

        if update.message.media_group_id:
            await _register_album_update(update, file_id=uploaded_photo_id, count_pending=False)
        
        if caption and not update.message.media_group_id:
            # ═══ Caption = question → Answer directly with vision ═══
            async with async_session() as db:
                user_msg = Message(chat_id=chat_id, role="user", content=f"[عکس ارسال شده: ID={uploaded_photo_id}]\n{caption}")
                db.add(user_msg)
                await db.commit()
                await db.refresh(user_msg)

            # Stream reply with vision
            async with async_session() as db:
                user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                chat_id = user.current_chat_id
                model_id = user.current_model_id
                if model_id:
                    provider, model = await get_provider_for_model(db, model_id)
                    if not model:
                        provider, model = await get_default_model(db)
                else:
                    provider, model = await get_default_model(db)

                if not model:
                    await update.message.reply_text("مدلی تنظیم نشده")
                    return

                current_chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
                if not current_chat:
                    await update.message.reply_text("چت پیدا نشد")
                    return
                system_content = await get_effective_system_prompt(db, chat=current_chat, user=user, include_tool_guidance=False)
                user_display = user.preferred_name or user.first_name or uid
                system_content = f"{system_content}\n\nThe user's name is {user_display}. Address them by their name sometimes."

                # RAG
                project_id = user.current_project_id
                if project_id or chat_id:
                    emb = await _get_emb_config(db); docs = await _search_with_config(project_id, caption, emb_config=emb, n_results=5, chat_id=chat_id)
                    if docs:
                        ctx = "\n\n---\n\n".join([d["content"] for d in docs])
                        system_content += f"\n\nRelevant documents context:\n{ctx}"

                # Add chat history (last 40 messages)
                result = await db.execute(
                    select(Message)
                    .where(Message.chat_id == chat_id)
                    .order_by(Message.created_at.desc())
                    .limit(20)
                )
                all_msgs = list(reversed(result.scalars().all()))
                llm_messages = []
                for m in all_msgs:
                    llm_messages.append({"role": m.role, "content": m.content})

                llm_messages.insert(0, {"role": "system", "content": system_content})
                provider, model, routing = await resolve_model_for_completion(
                    db,
                    selected_provider=provider,
                    selected_model=model,
                    messages=llm_messages,
                )
                if not provider or not model:
                    await update.message.reply_text("مدل اجرایی فعالی برای Auto Routing تنظیم نشده.")
                    return

                supports_vis = await asyncio.to_thread(model_supports_image_input, model)
                llm_messages = await _resolve_vision_messages(db, llm_messages, supports_vis)

                # Check if model needs vision capability warning
                needs_vision_warning = any(m.get("role") == "_vision" and m.get("content") == "_needs_vision_warning" for m in llm_messages)
                # Remove the internal flag from messages
                llm_messages = [m for m in llm_messages if not (m.get("role") == "_vision")]

                proj_label = ""
                if project_id:
                    result3 = await db.execute(select(Project).where(Project.id == project_id))
                    proj = result3.scalar_one_or_none()
                    if proj:
                        proj_label = f"\n📁 {proj.name}"

                try:
                    full_reply = await _run_tool_aware_completion(
                        update,
                        db,
                        user=user,
                        user_message=user_msg,
                        chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none(),
                        provider=provider,
                        model=model,
                        llm_messages=llm_messages,
                        proj_label=proj_label,
                        allow_tools=False,
                        uploaded_file_id=uploaded_photo_id,
                        status_message_obj=processing_msg,
                        routing=routing,
                    )
                except Exception as e2:
                    err_text = str(e2)[:4000]
                    try:
                        await update.message.reply_text(f"❌ {err_text}")
                    except Exception:
                        pass
                    return

                # If model doesn't support vision but user sent an image, inform them
                if needs_vision_warning:
                    model_label = model.display_name or model.name
                    kb, suggestions = await _build_vision_model_suggestion_keyboard(db, exclude_model_id=model.id, limit=4)
                    if suggestions:
                        error_text = (
                            f"⚠️ مدل «{model_label}» از ورودی تصویر پشتیبانی نمی‌کند.\n"
                            "برای ادامه با تصویر، یکی از مدل‌های پیشنهادی را انتخاب کن:"
                        )
                    else:
                        error_text = (
                            f"⚠️ Model «{model_label}» does not support image input. / از ورودی تصویر پشتیبانی نمی‌کند.\n"
                            "No active vision model found. / مدل vision فعالی پیدا نشد. لطفاً در پنل ادمین یک مدل vision فعال کن."
                        )
                    try:
                        await update.message.reply_text(error_text, reply_markup=kb)
                    except Exception:
                        pass
                    return

                await _save_assistant_message_and_post_actions(
                    update,
                    db,
                    uid=uid,
                    chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none(),
                    model=model,
                    llm_messages=llm_messages,
                    assistant_text=full_reply,
                    user_text=caption,
                )
            await _mark_update_completed(update)
        elif update.message.media_group_id:
            await _safe_edit_or_reply(update, processing_msg, "📥 عکس‌ها دریافت شدند. در حال آماده‌سازی پاسخ...")
        else:
            # ═══ No caption → Save photo, ask what they want ═══
            photo_msg = f"[عکس ارسال شده: ID={uploaded_photo_id}]"
            async with async_session() as db:
                db.add(Message(chat_id=chat_id, role="user", content=photo_msg))
                await db.commit()

            await processing_msg.edit_text(
                "عکس رو گرفتم.\n"
                "می‌تونم توصیفش کنم، متن داخلش رو بخونم، جزئیاتش رو تحلیل کنم یا به سوالت درباره‌اش جواب بدم. دوست داری از کجا شروع کنم؟"
            )
            await _mark_update_completed(update)
    finally:
        _unregister_user_task(chat_id, task)
        await _finish_album_update(update, context, handle_message)
        if update.message and update.message.media_group_id:
            await _mark_update_completed(update)


async def _resolve_vision_messages(db: AsyncSession, llm_messages: list, supports_vision: bool) -> list:
    import re
    import os
    import base64
    from app.models import UploadedFile
    
    # 1. Collapse consecutive user messages
    collapsed = []
    for msg in llm_messages:
        if collapsed and collapsed[-1]["role"] == "user" and msg["role"] == "user":
            if isinstance(collapsed[-1]["content"], str) and isinstance(msg["content"], str):
                collapsed[-1]["content"] += "\n\n" + msg["content"]
            else:
                collapsed.append(dict(msg))
        else:
            collapsed.append(dict(msg))
            
    resolved_messages = []
    
    for msg in collapsed:
        if msg["role"] != "user" or not isinstance(msg["content"], str):
            resolved_messages.append(msg)
            continue
            
        content_str = msg["content"]
        # Find all image tags: [عکس ارسال شده: ID=123]
        matches = list(re.finditer(r"\[عکس ارسال شده: ID=(\d+)\]", content_str))
        
        if matches:
            logger.info(f"Found {len(matches)} image tags in user message. supports_vision={supports_vision}")

        # Clean text by removing all image tags and redundant newlines
        clean_text = re.sub(r"\[عکس ارسال شده: ID=\d+\]\n?", "", content_str).strip()
        
        # If model definitely doesn't support vision, inform user and skip processing
        if matches and supports_vision is False:
            logger.info(f"Model explicitly doesn't support vision; will inform user after LLM call")
            resolved_messages.append(msg)
            # Add a flag to indicate model lacks vision capability
            resolved_messages.append({"role": "_vision", "content": "_needs_vision_warning"})
            continue
            
        # Build multi-part content
        content_parts = []
        
        # Add each image found in the message
        images_found = 0
        for match in matches:
            file_id = int(match.group(1))
            logger.info(f"Attempting to resolve image ID={file_id}")
            try:
                uploaded_file = await db.get(UploadedFile, file_id)
                if uploaded_file and uploaded_file.storage_path:
                    path = uploaded_file.storage_path
                    logger.info(f"Found record for ID={file_id}, path={path}")
                    if not os.path.isabs(path):
                        # Try current dir and backend dir
                        if os.path.exists(path):
                            path = os.path.abspath(path)
                        elif os.path.exists(os.path.join("backend", path)):
                            path = os.path.abspath(os.path.join("backend", path))
                        else:
                            path = os.path.abspath(path)
                    
                    if os.path.exists(path):
                        # Check file size (limit to 10MB to avoid proxy issues)
                        if os.path.getsize(path) > 10 * 1024 * 1024:
                            logger.warning(f"Image ID={file_id} too large skipping")
                            continue

                        b64 = _encode_image_to_base64(path)
                        logger.info(f"Encoded image ID={file_id} to base64, size={len(b64)}")
                        
                        # Use MIME type from DB if available and valid
                        mime = "image/jpeg"
                        if uploaded_file.mime_type and uploaded_file.mime_type.startswith("image/"):
                            mime = uploaded_file.mime_type
                        else:
                            lower_path = path.lower()
                            if lower_path.endswith(".png"): mime = "image/png"
                            elif lower_path.endswith(".gif"): mime = "image/gif"
                            elif lower_path.endswith(".webp"): mime = "image/webp"
                        
                        # Add image part FIRST
                        content_parts.append({
                            "type": "image_url", 
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}"
                            }
                        })
                        images_found += 1
                    else:
                        logger.error(f"Image file not found for ID={file_id} at {path}")
                else:
                    logger.error(f"UploadedFile record not found or has no storage_path for ID={file_id}")
            except Exception as e:
                logger.error(f"Failed to process image ID={file_id}: {e}")
        
        if images_found > 0:
            # Add text part AFTER images (Gemini often prefers this)
            text_for_llm = clean_text if clean_text else "لطفاً این تصویر را بررسی کن."
            content_parts.append({"type": "text", "text": text_for_llm})
            
            logger.info(f"Resolved {images_found} images for user message.")
            resolved_messages.append({"role": "user", "content": content_parts})
        else:
            # Fallback to original text if no images could be loaded
            resolved_messages.append(msg)
            
    return resolved_messages

async def _process_chat_text_turn(
    update: Update,
    *,
    uid: int,
    content: str,
    uploaded_file_id: int | None = None,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    recent_uploads_context: dict | None = None,
    status_message_obj=None,
):
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        chat_id = user.current_chat_id

        if not chat_id:
            chat = Chat(
                title="💬 چت جدید",
                model_id=user.current_model_id,
                project_id=user.current_project_id,
                user_preference_id=user.id,
            )
            db.add(chat)
            await db.commit()
            await db.refresh(chat)
            user.current_chat_id = chat.id
            await db.commit()
            chat_id = chat.id

        result = await db.execute(select(Chat).where(Chat.id == chat_id))
        chat = result.scalar_one_or_none()
        if not chat:
            chat = Chat(
                title="💬 چت جدید",
                model_id=user.current_model_id,
                project_id=user.current_project_id,
                user_preference_id=user.id,
            )
            db.add(chat)
            await db.commit()
            await db.refresh(chat)
            user.current_chat_id = chat.id
            await db.commit()
            chat_id = chat.id

        user_msg = Message(chat_id=chat_id, role="user", content=content)
        db.add(user_msg)
        await db.commit()
        await db.refresh(user_msg)

        model_id = user.current_model_id or chat.model_id
        if model_id:
            provider, model = await get_provider_for_model(db, model_id)
            if not model:
                provider, model = await get_default_model(db)
        else:
            provider, model = await get_default_model(db)

        if not model:
            await update.message.reply_text("مدلی تنظیم نشده" + ("\n→ 🔧 مدیریت" if uid == ADMIN_ID else ""), reply_markup=main_kb(uid == ADMIN_ID))
            return

        # Build history (last 40 messages)
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
        all_messages = list(reversed(result.scalars().all()))
        llm_messages = [{"role": m.role, "content": m.content} for m in all_messages]

        system_content = await get_effective_system_prompt(db, chat=chat, user=user, include_tool_guidance=False)
        user_display = user.preferred_name or user.first_name or uid
        system_content = f"{system_content}\n\nThe user's name is {user_display}. Address them by their name sometimes."

        provider, model, routing = await resolve_model_for_completion(
            db,
            selected_provider=provider,
            selected_model=model,
            messages=[{"role": "system", "content": system_content}] + llm_messages,
        )
        if not provider or not model:
            await update.message.reply_text("مدل اجرایی فعالی برای Auto Routing تنظیم نشده.")
            return

        supports_vis = await asyncio.to_thread(model_supports_image_input, model)
        has_image_tags = any("[عکس ارسال شده:" in (m.content or "") for m in all_messages)
        llm_messages = await _resolve_vision_messages(db, llm_messages, supports_vis)

        # Check if model needs vision capability warning
        needs_vision_warning = any(m.get("role") == "_vision" and m.get("content") == "_needs_vision_warning" for m in llm_messages)
        # Remove the internal flag from messages
        llm_messages = [m for m in llm_messages if not (m.get("role") == "_vision")]

        project_id = user.current_project_id or chat.project_id
        if project_id and not await _is_pro_or_admin(db, user):
            if context is not None:
                await _send_pro_restriction_message(update, context)
            else:
                await update.message.reply_text("🚀 استفاده از پروژه‌ها مخصوص کاربران پرو است.")
            return

        preprocessing = await _build_spreadsheet_preprocessing_context(
            db,
            user=user,
            user_text=content,
            chat_id=chat_id,
        )
        if preprocessing:
            try:
                full_reply, compact_messages = await _run_precomputed_spreadsheet_completion(
                    update,
                    db,
                    user=user,
                    user_message=user_msg,
                    chat=chat,
                    provider=provider,
                    model=model,
                    user_text=content,
                    system_content=system_content,
                    preprocessing=preprocessing,
                )
            except Exception as e2:
                await update.message.reply_text(f"❌ {str(e2)}")
                return

            await _save_assistant_message_and_post_actions(
                update,
                db,
                uid=uid,
                chat=chat,
                model=model,
                llm_messages=compact_messages,
                assistant_text=full_reply,
                user_text=content,
            )
            return

        lookup_project_id, lookup_chat_id = _rag_lookup_scope(project_id, chat_id)
        if lookup_project_id or lookup_chat_id:
            emb = await _get_emb_config(db)
            docs = await _search_with_config(
                lookup_project_id,
                content,
                emb_config=emb,
                n_results=5,
                chat_id=lookup_chat_id,
            )
            if docs:
                ctx = "\n\n---\n\n".join([d["content"] for d in docs])
                system_content += f"\n\nRelevant documents context:\n{ctx}"

        system_content = _append_recent_uploads_context(system_content, recent_uploads_context)

        llm_messages.insert(0, {"role": "system", "content": system_content})

        proj_label = ""
        if project_id:
            result3 = await db.execute(select(Project).where(Project.id == project_id))
            proj = result3.scalar_one_or_none()
            if proj:
                proj_label = f"\n📁 {proj.name}"

        try:
            full_reply = await _run_tool_aware_completion(
                update,
                db,
                user=user,
                user_message=user_msg,
                chat=chat,
                provider=provider,
                model=model,
                llm_messages=llm_messages,
                proj_label=proj_label,
                allow_tools=True,
                uploaded_file_id=uploaded_file_id,
                status_message_obj=status_message_obj,
                routing=routing,
            )
        except Exception as e2:
            await update.message.reply_text(f"❌ {str(e2)}")
            return

        # If model doesn't support vision but user sent an image, inform them
        if needs_vision_warning or (has_image_tags and not supports_vis):
            model_label = model.display_name or model.name
            kb, suggestions = await _build_vision_model_suggestion_keyboard(db, exclude_model_id=model.id, limit=4)
            if suggestions:
                error_text = (
                    f"⚠️ مدل «{model_label}» از ورودی تصویر پشتیبانی نمی‌کند.\n"
                    "برای ادامه با تصویر، یکی از مدل‌های پیشنهادی را انتخاب کن:"
                )
            else:
                error_text = (
                    f"⚠️ مدل «{model_label}» از ورودی تصویر پشتیبانی نمی‌کند.\n"
                    "مدل vision فعالی پیدا نشد. لطفاً در پنل ادمین یک مدل vision فعال کن."
                )
            try:
                await update.message.reply_text(error_text, reply_markup=kb)
            except Exception:
                pass
            return

        await _save_assistant_message_and_post_actions(
            update,
            db,
            uid=uid,
            chat=chat,
            model=model,
            llm_messages=llm_messages,
            assistant_text=full_reply,
            user_text=content,
        )


async def _execute_voice_transcription(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    uid: int,
    voice_file_id: str,
    voice_file_unique_id: str,
    duration: int,
    mime_type: str,
    project_id: Optional[int],
    explicit_upload_requested: bool,
    project_upload_mode: bool,
    processing_msg: Message,
    transcription_config: Any,
    estimated_cost: float,
    estimated_in_tokens: int,
    estimated_out_tokens: int,
    voice_file_size: int = 0
):
    file_path = f"./uploads/voice/{voice_file_unique_id}.ogg"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        await _download_telegram_file(context, voice_file_id, file_path)
        with open(file_path, "rb") as fp:
            audio_bytes = fp.read()
    except Exception as exc:
        logger.error(f"Voice download error: {str(exc)}")
        platform_name = "بله" if _is_bale_platform() else "تلگرام"
        await processing_msg.edit_text(f"❌ مشکلی در دریافت پیام صوتی از {platform_name} پیش آمد.")
        return

    uploaded_file_id = None
    usage_event_id = None
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        uploaded_file = await _record_uploaded_file(
            db,
            user=user,
            chat_id=user.current_chat_id,
            project_id=project_id if explicit_upload_requested else None,
            telegram_file_id=voice_file_id,
            telegram_file_unique_id=voice_file_unique_id,
            filename=f"{voice_file_unique_id}.ogg",
            mime_type=mime_type,
            file_type="voice",
            size_bytes=voice_file_size,
            storage_path=file_path,
            status="stored",
            metadata={"source": "telegram_voice"},
        )
        uploaded_file_id = uploaded_file.id
        usage_event = await _create_usage_event(
            db,
            user=user,
            chat_id=user.current_chat_id,
            message_id=None,
            uploaded_file_id=uploaded_file_id,
            operation_type="voice_transcription",
            provider_name=transcription_config.provider,
            model=None,
            estimated_cost_usd=estimated_cost,
            request_id=f"telegram:{update.update_id}:voice:{voice_file_unique_id}",
            metadata={
                "voice_duration_seconds": int(duration or 0),
                "voice_mime_type": mime_type,
                "transcription_model": transcription_config.model,
                "estimated_input_tokens": estimated_in_tokens,
                "estimated_output_tokens": estimated_out_tokens,
            },
        )
        usage_event.status = "authorized"
        await db.commit()
        usage_event_id = usage_event.id

    try:
        transcript, usage_log = await transcribe_audio(
            transcription_config,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            prompt=VOICE_TRANSCRIPTION_PROMPT,
        )
    except Exception as exc:
        async with async_session() as db:
            usage_event = await db.get(UsageEvent, usage_event_id) if usage_event_id else None
            uploaded_file = await db.get(UploadedFile, uploaded_file_id) if uploaded_file_id else None
            if usage_event:
                usage_event.status = "failed"
                usage_event.error = str(exc)
            if uploaded_file:
                uploaded_file.status = "failed"
                uploaded_file.processed_at = _utcnow()
            await db.commit()

        logger.error(f"Voice transcription error for voice message: {str(exc)}")
        user_friendly_error = "مشکلی در سرورهای تبدیل صوت پیش آمد (احتمالاً شلوغی شبکه). لطفاً کمی بعد دوباره تلاش کنید."
        if "503" in str(exc) or "502" in str(exc):
            user_friendly_error = "سرورهای هوش مصنوعی در حال حاضر شلوغ هستند. لطفاً چند دقیقه دیگر مجدداً ویس بفرستید."
        elif "429" in str(exc):
            user_friendly_error = "محدودیت تعداد درخواست‌های سرور. لطفاً کمی صبر کنید و دوباره امتحان کنید."

        await processing_msg.edit_text(f"❌ خطا در پردازش صوت:\n{user_friendly_error}")
        return

    transcript = (transcript or "").strip()
    if not transcript:
        async with async_session() as db:
            usage_event = await db.get(UsageEvent, usage_event_id) if usage_event_id else None
            uploaded_file = await db.get(UploadedFile, uploaded_file_id) if uploaded_file_id else None
            if usage_event:
                usage_event.status = "failed"
                usage_event.error = "empty transcript"
            if uploaded_file:
                uploaded_file.status = "failed"
                uploaded_file.processed_at = _utcnow()
            await db.commit()
        await processing_msg.edit_text("❌ متن قابل استفاده‌ای از پیام صوتی استخراج نشد.")
        return

    usage_input_tokens, usage_output_tokens = _extract_usage_tokens(usage_log)
    usage_source = "provider_reported"
    if usage_input_tokens == 0 and usage_output_tokens == 0:
        usage_input_tokens = estimated_in_tokens
        usage_output_tokens = estimated_out_tokens
        usage_source = "estimated"
    actual_cost = _transcription_cost_usd(transcription_config, usage_input_tokens, usage_output_tokens)

    async with async_session() as db:
        usage_event = await db.get(UsageEvent, usage_event_id) if usage_event_id else None
        uploaded_file = await db.get(UploadedFile, uploaded_file_id) if uploaded_file_id else None
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if usage_event:
            await _complete_usage_event(
                db,
                usage_event,
                input_tokens=usage_input_tokens,
                output_tokens=usage_output_tokens,
                actual_cost_usd=actual_cost,
                usage_source=usage_source,
            )
        from app.services.toman_billing_service import charge_generic_usage_toman
        charge_result = await charge_generic_usage_toman(
            db,
            user=user,
            cost_usd=actual_cost,
            entry_type="voice_transcription",
            reason="telegram voice transcription",
            usage_event_id=usage_event.id if usage_event else None,
            idempotency_key=f"usage:{usage_event.id}:charge" if usage_event else None,
            metadata={
                "usage_event_id": usage_event.id if usage_event else None,
                "voice_file_unique_id": voice_file_unique_id,
                "transcription_model": transcription_config.model,
                "input_tokens": usage_input_tokens,
                "output_tokens": usage_output_tokens,
            },
        )
        if not charge_result.ok:
            if usage_event:
                usage_event.status = "billing_failed"
                usage_event.error = "insufficient toman credit during voice transcription charge"
            await db.commit()
            current_balance = await _toman_balance(db, user)
            await processing_msg.edit_text(
                _insufficient_toman_credit_text(
                    needed_toman=charge_result.cost_toman or 0,
                    balance_toman=current_balance,
                    action_label="ثبت هزینه تبدیل صوت",
                ),
                reply_markup=_insufficient_toman_credit_kb()
            )
            return
        if uploaded_file:
            uploaded_file.status = "processed"
            uploaded_file.processed_at = datetime.now(timezone.utc)
        await db.commit()

    if project_id and explicit_upload_requested:
        # INDEX VOICE INTO PROJECT
        transcript_path = f"{file_path}.transcript.txt"
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        try:
            async with async_session() as db:
                user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                emb = await _get_emb_config(db)
                estimated_tokens = _estimate_text_tokens(transcript)
                estimated_embed_cost = _embedding_cost_usd(emb, estimated_tokens)

                # Create record first
                from app.models import Document
                doc_record = Document(
                    project_id=project_id,
                    filename=f"Voice_{voice_file_unique_id}.txt",
                    file_type="voice",
                    file_path=file_path,
                    chunk_count=0,
                )
                db.add(doc_record)
                await db.commit()
                await db.refresh(doc_record)

                api_key = emb.api_key if emb else None
                model_name = emb.model if emb else None
                chunk_count = await asyncio.to_thread(rag_index_document, project_id, doc_record.id, transcript_path, api_key=api_key, model=model_name)
                doc_record.chunk_count = chunk_count

                from app.services.toman_billing_service import charge_generic_usage_toman
                charge_result = await charge_generic_usage_toman(
                    db,
                    user=user,
                    cost_usd=estimated_embed_cost,
                    entry_type="rag_embedding",
                    reason="telegram voice document indexing",
                    metadata={
                        "project_id": project_id,
                        "filename": doc_record.filename,
                        "estimated_tokens": estimated_tokens,
                        "embedding_model": model_name,
                    },
                )
                if estimated_embed_cost <= 0:
                    await db.commit()
                elif not charge_result.ok:
                    pass

                uploaded_file = await db.get(UploadedFile, uploaded_file_id) if uploaded_file_id else None
                if uploaded_file:
                    uploaded_file.status = "indexed"
                uploaded_file.processed_at = _utcnow()
                await db.commit()

            reply_markup = upload_mode_kb() if project_upload_mode else None
            await processing_msg.edit_text(
                f"✅ ویس به متن تبدیل و در پروژه ایندکس شد.\n\n📊 {chunk_count} بخش ایندکس شد\n📁 Knowledge Base #{project_id}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Voice indexing error: {str(e)}")
            await processing_msg.edit_text("✅ ویس به متن تبدیل شد اما در ایندکس پروژه خطایی رخ داد.")
    else:
        await _send_or_edit_formatted(processing_msg, _voice_ack_text(transcript))
        await _process_chat_text_turn(
            update,
            uid=uid,
            content=transcript,
            uploaded_file_id=uploaded_file_id,
            context=context,
            status_message_obj=processing_msg,
        )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    if not await _claim_update_once(update):
        return

    task = _register_user_task(chat_id)
    try:
        project_upload_mode = bool(context.user_data.get("project_upload_mode", False))
        explicit_upload_requested = bool(context.user_data.pop("awaiting_project_file_upload", False)) or project_upload_mode

        voice = update.message.voice
        if not voice:
            return

        async with async_session() as gate_db:
            gate_user = await get_user(gate_db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            if not await _ensure_onboarding_or_prompt(update, context, user=gate_user):
                return

            current_project = await _get_accessible_current_project(gate_db, gate_user)
            project_id = current_project.id if current_project else None

            transcription_config = await _get_or_create_transcription_config(gate_db)
            if not transcription_config.is_active:
                await update.message.reply_text("تبدیل صوت به متن در حال حاضر غیرفعاله.")
                return
            if not (transcription_config.api_key or "").strip():
                await update.message.reply_text("کلید API برای تبدیل صوت به متن تنظیم نشده.")
                return
            estimated_in_tokens = _estimate_audio_tokens(getattr(voice, "duration", 0)) + _estimate_text_tokens(VOICE_TRANSCRIPTION_PROMPT)
            estimated_out_tokens = max(64, estimated_in_tokens // 6)
            estimated_cost_toman = await _transcription_cost_toman(gate_db, transcription_config, estimated_in_tokens, estimated_out_tokens)
            fake_model = DBModel(name=transcription_config.model, pricing_input=transcription_config.pricing_input, pricing_output=transcription_config.pricing_output)
            ok, reason, user_sub = await _has_toman_credit_for_cost(gate_db, gate_user, fake_model, estimated_in_tokens, estimated_out_tokens)
            if not ok:
                gate_user.pending_action_payload = {
                    "action_type": "voice_transcription",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "voice_file_id": voice.file_id,
                        "voice_file_unique_id": voice.file_unique_id,
                        "duration": getattr(voice, "duration", 0),
                        "mime_type": (getattr(voice, "mime_type", None) or "audio/ogg").strip() or "audio/ogg",
                    }
                }
                await gate_db.commit()
                current_balance = await _toman_balance(gate_db, gate_user)
                await update.message.reply_text(
                    _insufficient_toman_credit_text(
                        needed_toman=estimated_cost_toman,
                        balance_toman=current_balance,
                        action_label="تبدیل پیام صوتی",
                    ),
                    reply_markup=_insufficient_toman_credit_kb()
                )
                return

        processing_msg = await update.message.reply_text("🎙 در حال تبدیل پیام صوتی به متن...")

        await _execute_voice_transcription(
            update,
            context,
            uid=uid,
            voice_file_id=voice.file_id,
            voice_file_unique_id=voice.file_unique_id,
            duration=getattr(voice, "duration", 0),
            mime_type=(getattr(voice, "mime_type", None) or "audio/ogg").strip() or "audio/ogg",
            project_id=project_id,
            explicit_upload_requested=explicit_upload_requested,
            project_upload_mode=project_upload_mode,
            processing_msg=processing_msg,
            transcription_config=transcription_config,
            estimated_cost=estimated_cost,
            estimated_in_tokens=estimated_in_tokens,
            estimated_out_tokens=estimated_out_tokens,
            voice_file_size=voice.file_size or 0
        )
        await _mark_update_completed(update)
    finally:
        _unregister_user_task(chat_id, task)

# ══════════════════════════════════════
#  CHAT MESSAGE — STREAMING
# ══════════════════════════════════════
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, forced_text: str = None, status_message_obj=None):
    print(f"!!! RECEIVED MESSAGE from {update.effective_user.id} !!!")
    uid = update.effective_user.id
    chat_id = update.effective_chat.id

    if not await _claim_update_once(update, allow_reclaim=(forced_text is not None)):
        return

    task = _register_user_task(chat_id)
    try:
        content = forced_text if forced_text is not None else update.message.text
        normalized = content.strip() if content else ""

        if update.effective_chat and update.effective_chat.type in {"group", "supergroup"}:
            await update.message.reply_text("\u26a0\ufe0f \u0642\u0627\u0628\u0644\u06cc\u062a \u06af\u0641\u062a\u06af\u0648 \u062f\u0631 \u06af\u0631\u0648\u0647\u200c\u0647\u0627 \u062f\u0631 \u062d\u0627\u0644 \u062d\u0627\u0636\u0631 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a.")
            return

        if normalized == CANCEL_TEXT:
            _reset_ephemeral_state(context, clear_pending=True)
            await update.message.reply_text("\u0628\u0631\u06af\u0634\u062a\u06cc\u0645 \u0628\u0647 \u0645\u0646\u0648\u06cc \u0627\u0635\u0644\u06cc.", reply_markup=main_kb(uid == ADMIN_ID))
            return

        if _is_navigation_or_command(normalized):
            logger.info(f"handle_message: identified as navigation '{normalized}', ignoring generic handler")
            _reset_ephemeral_state(context, clear_pending=True)
            return

        # Name onboarding
        if context.user_data.get("asking_name"):
            name = content.strip()
            if not name:
                await update.message.reply_text("\u0627\u0633\u0645 \u062e\u0627\u0644\u06cc\u0647\u060c \u0644\u0637\u0641\u0627\u064b \u062f\u0648\u0628\u0627\u0631\u0647 \u0628\u0646\u0648\u06cc\u0633.")
                return
            return_to_account_panel = bool(context.user_data.pop("account_set_name_return", False))
            async with async_session() as db:
                user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                user.preferred_name = name
                _mark_onboarding_complete(user)
                await db.commit()
                ctx = await _load_account_context(db, user, tx_limit=8) if return_to_account_panel else None
            context.user_data.pop("asking_name", None)

            if return_to_account_panel and ctx:
                await update.message.reply_text(
                    f"\u2705 \u0646\u0627\u0645\u062a \u0628\u0647 \u00ab{name}\u00bb \u062a\u063a\u06cc\u06cc\u0631 \u06a9\u0631\u062f.\n\n{_account_home_text(ctx)}",
                    reply_markup=_account_kb("home", ctx),
                )
                return
            await update.message.reply_text(f"\u2705 {name}! \u0686\u0637\u0648\u0631\u06cc \u06a9\u0645\u06a9\u062a \u06a9\u0646\u0645\u061f", reply_markup=main_kb(uid == ADMIN_ID))
            return

        # Phone registration
        if PHONE_TEXT_RE.match(normalized):
            async with async_session() as db:
                user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                needs_phone = (not user.is_admin) and _missing_phone(user)
            if needs_phone:
                await _save_phone_onboarding_and_reply(
                    update, context, uid=uid, raw_phone=normalized,
                )
                return

        # Promo code entry
        if context.user_data.get("awaiting_account_promo_code"):
            code = normalize_promo_code(normalized)
            if not code:
                await update.message.reply_text("\u274c \u06a9\u062f \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a.")
                return
            async with async_session() as db:
                gate_user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                if not await _ensure_onboarding_or_prompt(update, context, user=gate_user):
                    return
                try:
                    redemption = await redeem_promo_code_for_user(
                        db, user=gate_user,
                        code=code, charge_amount_toman=0,
                        source="telegram_account",
                    )
                    _reset_ephemeral_state(context, clear_pending=True)
                    await update.message.reply_text(
                        f"\u2705 \u06a9\u062f \u062a\u062e\u0641\u06cc\u0641 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0627\u0639\u0645\u0627\u0644 \u0634\u062f!\n\n"
                        f"\u06a9\u062f: {redemption.promo_code_id}\n"
                        f"\u0627\u0639\u062a\u0628\u0627\u0631 \u0627\u0636\u0627\u0641\u0647\u200c\u0634\u062f\u0647: {_format_toman(redemption.total_credit_toman)}",
                        reply_markup=main_kb(uid == ADMIN_ID),
                    )
                except PromoCodeRedemptionError as exc:
                    await update.message.reply_text(
                        f"\u274c {_promo_error_to_fa(str(exc))}",
                        reply_markup=main_kb(uid == ADMIN_ID),
                    )
            return

        # Toman topup amount entry
        if context.user_data.get("awaiting_toman_topup_amount"):
            amount_toman = _parse_toman_amount(normalized)
            if amount_toman is None:
                await update.message.reply_text(
                    "\u274c \u0645\u0628\u0644\u063a \u0646\u0627\u0645\u0639\u062a\u0628\u0631\u0647.\n"
                    "\u06cc\u06a9 \u0639\u062f\u062f \u062a\u0648\u0645\u0627\u0646\u06cc \u0645\u0639\u062a\u0628\u0631 \u0628\u0641\u0631\u0633\u062a (\u0645\u062b\u0627\u0644: 300000)."
                )
                return
            async with async_session() as db:
                from app.services.toman_billing_service import quote_toman_topup_payment

                gate_user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                if not await _ensure_onboarding_or_prompt(update, context, user=gate_user):
                    return
                quote = await quote_toman_topup_payment(db, user=gate_user, credit_amount_toman=amount_toman)

            context.user_data["pending_toman_topup_quote"] = {
                "credit_amount_toman": quote.credit_amount_toman,
                "normal_payment_toman": quote.normal_payment_toman,
                "payment_due_toman": quote.payment_due_toman,
                "discount_toman": quote.discount_toman,
                "discount_applied": quote.discount_applied,
            }

            pre_invoice = (
                f"\U0001f4cb *\u067e\u06cc\u0634\u200c\u0641\u0627\u06a9\u062a\u0648\u0631 \u0627\u0641\u0632\u0627\u06cc\u0634 \u0634\u0627\u0631\u0698*\n\n"
                f"\U0001f4b0 \u0627\u0639\u062a\u0628\u0627\u0631 \u062f\u0631\u062e\u0648\u0627\u0633\u062a\u06cc: {_format_toman(quote.credit_amount_toman)}\n"
                f"\U0001f4ca \u0645\u0628\u0644\u063a \u0639\u0627\u062f\u06cc: {_format_toman(quote.normal_payment_toman)}\n"
            )
            if quote.discount_applied:
                pre_invoice += f"\U0001f381 \u062a\u062e\u0641\u06cc\u0641 \u0627\u0648\u0644\u06cc\u0646 \u0634\u0627\u0631\u0698: {_format_toman(quote.discount_toman)}\n"
            pre_invoice += f"\n\u2705 *\u0645\u0628\u0644\u063a \u0642\u0627\u0628\u0644 \u067e\u0631\u062f\u0627\u062e\u062a: {_format_toman(quote.payment_due_toman)}*\n\n"
            pre_invoice += "\U0001f4b5 \u0631\u0648\u0634 \u067e\u0631\u062f\u0627\u062e\u062a \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f4b3 \u062f\u0631\u06af\u0627\u0647 \u067e\u0631\u062f\u0627\u062e\u062a \u0628\u0644\u0647", callback_data="topup_method_bale")],
                [InlineKeyboardButton("\U0001f4b0 \u06a9\u0627\u0631\u062a \u0628\u0647 \u06a9\u0627\u0631\u062a", callback_data="topup_method_card")],
                [InlineKeyboardButton("\u274c \u0627\u0646\u0635\u0631\u0627\u0641", callback_data="cancel_main")],
            ])

            await update.message.reply_text(pre_invoice, reply_markup=kb, parse_mode="Markdown")
            return

        # Card-to-card amount entry
        if context.user_data.get("awaiting_card_to_card_amount"):
            amount_toman = _parse_toman_amount(normalized)
            if amount_toman is None:
                await update.message.reply_text(
                    "\u274c \u0645\u0628\u0644\u063a \u0646\u0627\u0645\u0639\u062a\u0628\u0631\u0647.\n"
                    "\u06cc\u06a9 \u0639\u062f\u062f \u062a\u0648\u0645\u0627\u0646\u06cc \u0645\u0639\u062a\u0628\u0631 \u0628\u0641\u0631\u0633\u062a (\u0645\u062b\u0627\u0644: 300000)."
                )
                return
            context.user_data["pending_card_amount_toman"] = amount_toman
            _begin_mode(context, "awaiting_card_receipt")
            await update.message.reply_text(
                "\u2705 \u0645\u0628\u0644\u063a \u062b\u0628\u062a \u0634\u062f.\n\n"
                "\U0001f4f8 \u062d\u0627\u0644\u0627 \u0644\u0637\u0641\u0627\u064b *\u062a\u0635\u0648\u06cc\u0631 \u0631\u0633\u06cc\u062f \u067e\u0631\u062f\u0627\u062e\u062a* \u0631\u0627 \u0627\u0631\u0633\u0627\u0644 \u06a9\u0646\u06cc\u062f.\n"
                "\u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u06cc\u062f \u0639\u06a9\u0633 \u0631\u0633\u06cc\u062f \u0631\u0627 \u0628\u0647 \u0635\u0648\u0631\u062a photo \u0628\u0641\u0631\u0633\u062a\u06cc\u062f.",
                reply_markup=_cancel_reply_kb(),
                parse_mode="Markdown",
            )
            return

        # Card receipt photo
        if context.user_data.get("awaiting_card_receipt"):
            if update.message.photo:
                await _handle_card_receipt_photo(update, context)
                return
            doc = update.message.document
            if doc:
                await _handle_card_receipt_as_document(update, context, doc)
                return
            await update.message.reply_text("\u274c \u0644\u0637\u0641\u0627\u064b \u062a\u0635\u0648\u06cc\u0631 \u0631\u0633\u06cc\u062f \u0631\u0627 \u0627\u0631\u0633\u0627\u0644 \u06a9\u0646\u06cc\u062f.")
            return

        # Subscription card receipt photo
        if context.user_data.get("awaiting_subscription_card_receipt"):
            if update.message.photo:
                await _handle_subscription_receipt_photo(update, context)
                return
            doc = update.message.document
            if doc:
                await _handle_subscription_receipt_as_document(update, context, doc)
                return
            await update.message.reply_text("\u274c \u0644\u0637\u0641\u0627\u064b \u062a\u0635\u0648\u06cc\u0631 \u0631\u0633\u06cc\u062f \u0631\u0627 \u0627\u0631\u0633\u0627\u0644 \u06a9\u0646\u06cc\u062f.")
            return

        # USD topup amount (Bale only)
        if context.user_data.get("awaiting_topup_amount"):
            if not _is_bale_platform():
                context.user_data.pop("awaiting_topup_amount", None)
                await update.message.reply_text("\u067e\u0631\u062f\u0627\u062e\u062a \u0622\u0646\u0644\u0627\u06cc\u0646 \u0641\u0642\u0637 \u062f\u0631 \u0628\u0627\u0632\u0648\u06cc \u0628\u0644\u0647 \u0641\u0639\u0627\u0644 \u0627\u0633\u062a.")
                return
            async with async_session() as db:
                gate_user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                if not await _ensure_onboarding_or_prompt(update, context, user=gate_user):
                    return
            amount_usd = _parse_topup_usd_amount(normalized)
            if amount_usd is None:
                await update.message.reply_text(
                    "\u274c \u0645\u0628\u0644\u063a \u0646\u0627\u0645\u0639\u062a\u0628\u0631\u0647.\n"
                    "\u06cc\u06a9 \u0639\u062f\u062f \u0628\u06cc\u0646 1 \u062a\u0627 5000 \u062f\u0644\u0627\u0631 \u0628\u0641\u0631\u0633\u062a (\u0645\u062b\u0627\u0644: 5 \u06cc\u0627 12.5)."
                )
                return
            _begin_mode(context, "awaiting_topup_promo_code")
            context.user_data["pending_topup_usd_amount"] = _decimal_to_plain(amount_usd)
            await update.message.reply_text(
                "\U0001f3f7 \u0627\u06af\u0631 \u06a9\u062f \u06a9\u0648\u067e\u0646 \u062f\u0627\u0631\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646.\n"
                f"\u0627\u06af\u0631 \u0646\u062f\u0627\u0631\u06cc \u062f\u06a9\u0645\u0647 \u00ab{TOPUP_PROMO_SKIP_TEXT}\u00bb \u0631\u0627 \u0628\u0632\u0646 \u06cc\u0627 \u0628\u0646\u0648\u06cc\u0633 skip.",
                reply_markup=_topup_promo_reply_kb(),
            )
            return

        # Topup promo code
        if context.user_data.get("awaiting_topup_promo_code"):
            if not _is_bale_platform():
                _reset_ephemeral_state(context, clear_pending=True)
                await update.message.reply_text("\u067e\u0631\u062f\u0627\u062e\u062a \u0622\u0646\u0644\u0627\u06cc\u0646 \u0641\u0642\u0637 \u062f\u0631 \u0628\u0627\u0632\u0648\u06cc \u0628\u0644\u0647 \u0641\u0639\u0627\u0644 \u0627\u0633\u062a.")
                return
            pending_amount_raw = context.user_data.get("pending_topup_usd_amount")
            amount_usd = _parse_topup_usd_amount(pending_amount_raw)
            if amount_usd is None:
                _reset_ephemeral_state(context, clear_pending=True)
                await update.message.reply_text(
                    "\u26a0\ufe0f \u0645\u0628\u0644\u063a \u0634\u0627\u0631\u0698 \u0642\u0628\u0644\u06cc \u0645\u0639\u062a\u0628\u0631 \u0646\u0628\u0648\u062f. \u0644\u0637\u0641\u0627\u064b \u062f\u0648\u0628\u0627\u0631\u0647 \u0627\u0632 \u0628\u062e\u0634 \u0634\u0627\u0631\u0698 \u062d\u0633\u0627\u0628 \u0634\u0631\u0648\u0639 \u06a9\u0646.",
                    reply_markup=main_kb(uid == ADMIN_ID),
                )
                return
            promo_code = _parse_topup_promo_code(normalized)
            if promo_code == "":
                await update.message.reply_text(
                    f"\u274c \u06a9\u062f \u06a9\u0648\u067e\u0646 \u0646\u0627\u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a.\n\u06a9\u062f \u0628\u0627\u06cc\u062f \u062d\u062f\u0627\u06a9\u062b\u0631 {MAX_TOPUP_PROMO_CODE_LEN} \u06a9\u0627\u0631\u0627\u06a9\u062a\u0631 \u0628\u0627\u0634\u062f."
                )
                return
            try:
                async with async_session() as db:
                    gate_user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                    if not await _ensure_onboarding_or_prompt(update, context, user=gate_user):
                        return
                    invoice_info = await _send_bale_topup_invoice(
                        bot=context.bot, db=db, user=gate_user,
                        chat_id=update.effective_chat.id, user_id=uid,
                        usd_amount=amount_usd, promo_code=promo_code,
                    )
            except Exception as exc:
                logger.exception("failed to send bale topup invoice")
                await update.message.reply_text(
                    "\u274c \u0627\u0631\u0633\u0627\u0644 \u0641\u0627\u06a9\u062a\u0648\u0631 \u067e\u0631\u062f\u0627\u062e\u062a \u0627\u0646\u062c\u0627\u0645 \u0646\u0634\u062f.\n"
                    f"\u062e\u0637\u0627: {str(exc)}"
                )
                return
            _reset_ephemeral_state(context, clear_pending=True)
            usd_label = _decimal_to_plain(invoice_info["usd_amount"])
            promo_line = ""
            if invoice_info.get("promo_code"):
                promo_line = f"\u06a9\u0648\u067e\u0646 \u0627\u0646\u062a\u062e\u0627\u0628\u200c\u0634\u062f\u0647: {invoice_info['promo_code']}\n"
            discount_line = f"\u062a\u062e\u0641\u06cc\u0641 \u0627\u0648\u0644\u06cc\u0646 \u0634\u0627\u0631\u0698: {invoice_info['discount_toman']:,} \u062a\u0648\u0645\u0627\u0646\n" if invoice_info.get("discount_toman") else ""
            await update.message.reply_text(
                "\u2705 \u0641\u0627\u06a9\u062a\u0648\u0631 \u067e\u0631\u062f\u0627\u062e\u062a \u0627\u0631\u0633\u0627\u0644 \u0634\u062f.\n"
                f"\u0634\u0627\u0631\u0698 \u062f\u0631\u062e\u0648\u0627\u0633\u062a\u06cc: ${usd_label}\n"
                f"\u0646\u0631\u062e \u0647\u0631 USDT: {invoice_info['usdt_price_rial']:,} \u0631\u06cc\u0627\u0644\n"
                f"{discount_line}"
                f"\u0645\u0628\u0644\u063a \u0646\u0647\u0627\u06cc\u06cc: {invoice_info['total_toman']:,} \u062a\u0648\u0645\u0627\u0646\n"
                f"{promo_line}"
                "\u0628\u0639\u062f \u0627\u0632 \u067e\u0631\u062f\u0627\u062e\u062a \u0645\u0648\u0641\u0642\u060c \u0627\u0639\u062a\u0628\u0627\u0631 \u062d\u0633\u0627\u0628\u062a \u062e\u0648\u062f\u06a9\u0627\u0631 \u0627\u0636\u0627\u0641\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f.",
                reply_markup=main_kb(uid == ADMIN_ID),
            )
            return

        # Default: no AI chat
        await update.message.reply_text(
            "\u0642\u0627\u0628\u0644\u06cc\u062a \u0686\u062a \u0647\u0648\u0634 \u0645\u0635\u0646\u0648\u0639\u06cc \u062f\u0631 \u062d\u0627\u0644 \u062d\u0627\u0636\u0631 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a.\n"
            "\u0644\u0637\u0641\u0627\u064b \u0627\u0632 \u0645\u0646\u0648\u06cc \u0632\u06cc\u0631 \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u06cc\u062f.",
            reply_markup=main_kb(uid == ADMIN_ID),
        )
        logger.info(f"handle_message: completed for uid={uid}")
    finally:
        await _mark_update_completed(update)
        _unregister_user_task(chat_id, task)




# ══════════════════════════════════════
#  LINK CODE COMMAND
# ══════════════════════════════════════
async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a 2-minute link code for web login."""
    uid = update.effective_user.id
    first_name = update.effective_user.first_name or ""
    username = update.effective_user.username or ""

    async with async_session() as db:
        user = await get_user(db, uid, first_name, username)

        import secrets
        from datetime import datetime, timezone, timedelta
        from app.models import LinkCode
        from sqlalchemy import select

        existing = await db.execute(
            select(LinkCode).where(
                LinkCode.user_preference_id == user.id,
                LinkCode.used == False,
                LinkCode.expires_at > datetime.now(timezone.utc)
            )
        )
        for code_obj in existing.scalars().all():
            code_obj.used = True

        code = LinkCode(
            code=''.join(secrets.choice('0123456789') for _ in range(6)),
            user_preference_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        )
        db.add(code)
        await db.commit()
        await db.refresh(code)

        display_name = user.preferred_name or user.first_name or user.username or f"User {uid}"
        await update.message.reply_text(
            f"🔗 کد اتصال شما:\n\n"
            f"<code>{code.code}</code>\n\n"
            f"⏳ این کد تا ۵ دقیقه معتبر است.\n"
            f"آن را در صفحه ورود وب‌سایت وارد کنید.",
            parse_mode=ParseMode.HTML,
        )


# ══════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════
prov_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^➕ پروایدر$"), admin_start_provider)],
    states={
        ADD_PROV_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_prov_name)],
        ADD_PROV_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_prov_url)],
        ADD_PROV_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_prov_key)],
    },
    fallbacks=[
        CommandHandler("cancel", admin_cancel),
        MessageHandler(filters.COMMAND, admin_cancel),
        MessageHandler(filters.Regex("^🔙"), admin_cancel),
        MessageHandler(filters.Regex(f"^{re.escape(CANCEL_TEXT)}$"), admin_cancel),
    ],
)

model_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^➕ مدل$"), admin_start_model)],
    states={
        ADD_MODEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_model_name)],
        ADD_MODEL_DISPLAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_model_display)],
        ADD_MODEL_PROVIDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_model_provider)],
        ADD_MODEL_PRICE_IN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_model_price_in)],
        ADD_MODEL_PRICE_OUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_model_price_out)],
        ADD_MODEL_CONTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_model_context)],
    },
    fallbacks=[
        CommandHandler("cancel", admin_cancel),
        MessageHandler(filters.COMMAND, admin_cancel),
        MessageHandler(filters.Regex("^🔙"), admin_cancel),
        MessageHandler(filters.Regex(f"^{re.escape(CANCEL_TEXT)}$"), admin_cancel),
    ],
)


async def bot_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error that happened during an update."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    async with async_session() as session:
        try:
            user_id = None
            if update and hasattr(update, "effective_user") and update.effective_user:
                user_id = update.effective_user.id

            error_log = ErrorLog(
                source="Telegram",
                error_message=str(context.error),
                stack_trace="".join(traceback.format_exception(None, context.error, context.error.__traceback__)),
                user_id=user_id,
            )
            session.add(error_log)
            await session.commit()
        except Exception as e:
            logger.error(f"Failed to log Telegram error: {e}")


async def open_mini_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message with a button to open the Dr. Boz web app as a mini app."""
    from app.config import OPENWEBUI_URL
    url = OPENWEBUI_URL.rstrip("/")
    await update.message.reply_text(
        "🚀 برای ورود به اپلیکیشن دکتر بز روی دکمه زیر بزن:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 باز کردن دکتر بز", web_app=WebAppInfo(url=url))],
        ]),
    )


async def open_app_or_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show referral info with copy link button."""
    uid = update.effective_user.id
    async with async_session() as db:
        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
        if not await _ensure_onboarding_or_prompt(update, context, user=user):
            return
        text = await _account_referral_text(db, user, context)
    await update.message.reply_text(text, reply_markup=_account_kb("referral"), parse_mode="Markdown")


# --- Web login code (shared with Open WebUI bot_auth) ---

_AUTH_CODE_TTL = 300
_AUTH_LOGIN_URL = "https://ai.alitekin.space:3000/auth"
_redis_client: Optional[aioredis.Redis] = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _generate_auth_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def cmd_get_login_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate an 8-char web login code and store it in Redis for Open WebUI to consume."""
    tg_user = update.effective_user
    if not tg_user:
        return
    uid = tg_user.id
    bale_username = tg_user.username or ""

    async with async_session() as db:
        user = await get_user(db, uid, tg_user.first_name or "", bale_username)

    phone = (user.phone_number or "").strip() if user else ""
    if not phone:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 ثبت شماره موبایل", callback_data="share_contact_request")],
        ])
        await update.message.reply_text(
            "ابتدا شماره موبایل خود را ثبت کنید.",
            reply_markup=kb,
        )
        return

    if not phone.startswith("+"):
        phone = normalize_phone_number(phone) or phone

    preferred_name = (user.preferred_name or "").strip() if user else ""
    display_name = preferred_name or (tg_user.first_name or "") or f"User_{uid}"

    code = _generate_auth_code()
    payload = {
        "user_id": str(uid),
        "provider": "bale",
        "sub": str(uid),
        "name": display_name,
        "username": bale_username or None,
        "phone": phone,
        "preferred_name": preferred_name or None,
    }
    try:
        redis_client = _get_redis()
        await redis_client.setex(
            f"auth:code:{code}",
            _AUTH_CODE_TTL,
            json.dumps(payload, ensure_ascii=False),
        )
    except Exception as e:
        logger.exception("Failed to store auth code in Redis: %s", e)
        await update.message.reply_text(
            "❌ خطا در تولید کد ورود. لطفاً چند لحظه بعد دوباره تلاش کنید."
        )
        return

    logger.info("Web login code generated for user %s: %s", uid, code)

    text = (
        "🔑 <b>کد ورود شما:</b>\n\n"
        f"<code>{code}</code>\n\n"
        "این کد را در صفحه ورود Dr. Boz وارد کنید.\n"
        "⏳ اعتبار کد: ۵ دقیقه"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 باز کردن صفحه ورود", url=_AUTH_LOGIN_URL)],
    ])
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


def run_bot():
    builder = Application.builder().token(BOT_TOKEN).connect_timeout(300.0).read_timeout(300.0).write_timeout(300.0).get_updates_read_timeout(300.0).concurrent_updates(True)
    if _is_bale_platform():
        builder = builder.base_url(BALE_API_BASE_URL).base_file_url(BALE_FILE_BASE_URL)
    app = builder.build()

    if app.job_queue:
        app.job_queue.run_repeating(run_scheduled_tips, interval=3600, first=10)
    app.add_error_handler(bot_error_handler)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("account", cmd_account))
    app.add_handler(CommandHandler("plans", cmd_plans))
    app.add_handler(CommandHandler("topup", cmd_topup))
    app.add_handler(CommandHandler("link", cmd_link))
    app.add_handler(CommandHandler("support", cmd_support))
    app.add_handler(CommandHandler("login", cmd_get_login_code))

    # Callback (main button handler)
    app.add_handler(CallbackQueryHandler(button_callback))

    # Pre-checkout / payment
    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))

    # Contact sharing
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))

    # Menu buttons — account/payment only
    app.add_handler(MessageHandler(filters.Regex("^👤 حساب کاربری$"), cmd_account))
    app.add_handler(MessageHandler(filters.Regex("^💎 اشتراک‌ها$"), cmd_plans))
    app.add_handler(MessageHandler(filters.Regex("^💰 افزایش شارژ$"), cmd_toman_topup))
    app.add_handler(MessageHandler(filters.Regex("^🎁 دعوت دوستان$"), open_app_or_referral))
    app.add_handler(MessageHandler(filters.Regex("^📞 پشتیبانی$"), cmd_support))
    app.add_handler(MessageHandler(filters.Regex("^🚀 باز کردن دکتر بز$"), open_mini_app))
    app.add_handler(MessageHandler(filters.Regex("^🔑 ورود به وب$"), cmd_get_login_code))
    app.add_handler(MessageHandler(filters.Regex("^🔧 مدیریت$"), admin_panel))
    app.add_handler(MessageHandler(filters.Regex("^👥 یوزرها$"), admin_list_users))
    app.add_handler(MessageHandler(filters.Regex("^📋 درخواست‌های پرداخت$"), admin_pending_payments))
    app.add_handler(MessageHandler(filters.Regex("^🔙 منوی اصلی$"), back_to_main))

    # Wallet payments
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))

    # Generic text — LAST
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(
        "🤖 Dr. Boz bot v5 (account/payment) starting... platform=%s base_url=%s",
        BOT_PLATFORM,
        BALE_API_BASE_URL if _is_bale_platform() else "telegram-default",
    )
    # Start polling
    app.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)


if __name__ == "__main__":
    asyncio.run(init_db())
    run_bot()
