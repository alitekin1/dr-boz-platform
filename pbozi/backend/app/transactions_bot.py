"""
Transactions Bot — separate bot for payment approval/rejection via Telegram/Bale.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import (
    TRANSACTIONS_BOT_TOKEN,
    TRANSACTIONS_BOT_ADMIN_CHAT_ID,
    TRANSACTIONS_BOT_PLATFORM,
    BALE_API_BASE_URL,
    BALE_FILE_BASE_URL,
    ADMIN_PASSWORD,
)
from app.database import async_session
from app.models import PaymentRequest, UserPreference
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.persian_time import format_persian

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logger.setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:7000")


def _is_bale() -> bool:
    return (TRANSACTIONS_BOT_PLATFORM or "").strip().lower() == "bale"


def _format_toman(amount: int) -> str:
    return f"{amount:,} تومان"


def _payment_type_label(ptype: str) -> str:
    return "شارژ حساب" if ptype == "topup" else "خرید اشتراک"


def _status_label(status: str) -> str:
    mapping = {"pending": "⏳ در انتظار بررسی", "approved": "✅ تأیید شده", "rejected": "❌ رد شده"}
    return mapping.get(status, status)


async def _get_user_by_id(db, user_id: int) -> Optional[UserPreference]:
    result = await db.execute(select(UserPreference).where(UserPreference.id == user_id))
    return result.scalar_one_or_none()


def _build_payment_message(req: PaymentRequest, user: Optional[UserPreference]) -> str:
    uname = user.first_name or "کاربر"
    username = f"@{user.username}" if user and user.username else ""
    ptype = _payment_type_label(getattr(req, "payment_type", "topup") or "topup")
    status = _status_label(req.status)
    created = format_persian(req.created_at, "%Y-%m-%d %H:%M") if req.created_at else ""
    desc = f"\n📝 {req.description}" if req.description else ""

    lines = [
        f"🔔 *درخواست پرداخت جدید*",
        f"",
        f"🆔 شناسه: `{req.id}`",
        f"👤 کاربر: {uname} {username}",
        f"💰 مبلغ: {_format_toman(req.amount_toman)}",
        f"📂 نوع: {ptype}",
        f"📊 وضعیت: {status}",
        f"🕐 تاریخ: {created}",
    ]
    if desc:
        lines.append(desc)
    return "\n".join(lines)


def _build_action_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأیید", callback_data=f"txn_approve_{request_id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"txn_reject_{request_id}"),
        ],
    ])


def _build_done_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="txn_list")],
    ])


async def _approve_payment(request_id: int) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_BASE_URL}/api/admin/payment-requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {ADMIN_PASSWORD}"},
            json={},
        )
        return resp.json()


async def _reject_payment(request_id: int, reason: str = "رد توسط ادمین") -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{BACKEND_BASE_URL}/api/admin/payment-requests/{request_id}/reject",
            headers={"Authorization": f"Bearer {ADMIN_PASSWORD}"},
            json={"admin_note": reason},
        )
        return resp.json()


async def _send_pending_payments(bot_app, bot_data: dict):
    """Send all pending payment requests to admin."""
    async with async_session() as db:
        result = await db.execute(
            select(PaymentRequest)
            .options(selectinload(PaymentRequest.user))
            .where(PaymentRequest.status == "pending")
            .order_by(PaymentRequest.created_at.asc())
        )
        requests = result.scalars().all()

    for req in requests:
        sent_key = f"txn_sent_{req.id}"
        if bot_data.get(sent_key):
            continue

        user = req.user
        text = _build_payment_message(req, user)
        kb = _build_action_kb(req.id)

        receipt_path = req.receipt_image_path
        photo_sent = False
        if receipt_path and os.path.isfile(receipt_path):
            try:
                with open(receipt_path, "rb") as f:
                    msg = await bot_app.bot.send_photo(
                        chat_id=TRANSACTIONS_BOT_ADMIN_CHAT_ID,
                        photo=f,
                        caption=text,
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                photo_sent = True
            except Exception as e:
                logger.warning("Failed to send receipt photo for request %d: %s", req.id, e)

        if not photo_sent:
            await bot_app.bot.send_message(
                chat_id=TRANSACTIONS_BOT_ADMIN_CHAT_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )

        bot_data[sent_key] = True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔔 بات تراکنش‌ها فعال است.\n"
        "درخواست‌های پرداخت جدید به صورت خودکار ارسال می‌شوند.\n"
        f"از دستور /list برای مشاهده لیست استفاده کنید."
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List recent pending payments."""
    async with async_session() as db:
        result = await db.execute(
            select(PaymentRequest)
            .options(selectinload(PaymentRequest.user))
            .where(PaymentRequest.status == "pending")
            .order_by(PaymentRequest.created_at.desc())
            .limit(20)
        )
        requests = result.scalars().all()

    if not requests:
        await update.message.reply_text("✅ هیچ درخواست پرداخت در انتظاری وجود ندارد.")
        return

    for req in requests:
        user = req.user
        text = _build_payment_message(req, user)
        kb = _build_action_kb(req.id)

        receipt_path = req.receipt_image_path
        photo_sent = False
        if receipt_path and os.path.isfile(receipt_path):
            try:
                with open(receipt_path, "rb") as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=text,
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                photo_sent = True
            except Exception as e:
                logger.warning("Failed to send receipt photo for request %d: %s", req.id, e)

        if not photo_sent:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _edit_callback_message(query, text: str, parse_mode: str = None, reply_markup=None):
    """Edit message text or caption depending on message type."""
    message = query.message
    is_photo = bool(getattr(message, "photo", None))
    try:
        if is_photo:
            await query.edit_message_caption(
                caption=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        else:
            await query.edit_message_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
    except Exception as e:
        error_str = str(e).lower()
        if "message is not modified" in error_str:
            return
        raise


async def handle_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data
    await query.answer()

    if data == "txn_list":
        await cmd_list(update, context)
        return

    if data.startswith("txn_approve_"):
        request_id = int(data.replace("txn_approve_", ""))
        try:
            result = await _approve_payment(request_id)
            new_text = _build_payment_message_from_result(result)
            await _edit_callback_message(
                query,
                f"✅ پرداخت با موفقیت تأیید شد!\n\n{new_text}",
                parse_mode="Markdown",
                reply_markup=_build_done_kb(),
            )
        except Exception as e:
            await _edit_callback_message(
                query,
                f"❌ خطا در تأیید پرداخت: {str(e)[:200]}",
                reply_markup=_build_done_kb(),
            )
        return

    if data.startswith("txn_reject_"):
        request_id = int(data.replace("txn_reject_", ""))
        try:
            result = await _reject_payment(request_id)
            new_text = _build_payment_message_from_result(result)
            await _edit_callback_message(
                query,
                f"❌ پرداخت رد شد.\n\n{new_text}",
                parse_mode="Markdown",
                reply_markup=_build_done_kb(),
            )
        except Exception as e:
            await _edit_callback_message(
                query,
                f"❌ خطا در رد پرداخت: {str(e)[:200]}",
                reply_markup=_build_done_kb(),
            )
        return


def _build_payment_message_from_result(result: dict) -> str:
    req_id = result.get("id", "?")
    uname = result.get("first_name", "کاربر")
    username = f"@{result['username']}" if result.get("username") else ""
    amount = result.get("amount_toman", 0)
    ptype = _payment_type_label(result.get("payment_type", "topup"))
    status = _status_label(result.get("status", "unknown"))
    admin_note = result.get("admin_note", "")
    note_text = f"\n📝 یادداشت: {admin_note}" if admin_note else ""

    return (
        f"🆔 شناسه: `{req_id}`\n"
        f"👤 کاربر: {uname} {username}\n"
        f"💰 مبلغ: {_format_toman(amount)}\n"
        f"📂 نوع: {ptype}\n"
        f"📊 وضعیت: {status}"
        f"{note_text}"
    )


async def send_new_payment_notification(request_id: int):
    """Called from payment_routes.py when a new payment request is created."""
    if not TRANSACTIONS_BOT_TOKEN or not TRANSACTIONS_BOT_ADMIN_CHAT_ID:
        return

    async with async_session() as db:
        result = await db.execute(
            select(PaymentRequest)
            .options(selectinload(PaymentRequest.user))
            .where(PaymentRequest.id == request_id)
        )
        req = result.scalar_one_or_none()
        if not req:
            return

    user = req.user
    text = _build_payment_message(req, user)
    kb = _build_action_kb(req.id)

    builder = Application.builder().token(TRANSACTIONS_BOT_TOKEN).connect_timeout(30.0).read_timeout(30.0)
    if _is_bale():
        builder = builder.base_url(BALE_API_BASE_URL).base_file_url(BALE_FILE_BASE_URL)
    app = builder.build()

    photo_sent = False
    receipt_path = req.receipt_image_path
    if receipt_path and os.path.isfile(receipt_path):
        try:
            with open(receipt_path, "rb") as f:
                await app.bot.send_photo(
                    chat_id=TRANSACTIONS_BOT_ADMIN_CHAT_ID,
                    photo=f,
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=kb,
                )
            photo_sent = True
        except Exception as e:
            logger.warning("Failed to send receipt photo via notification for request %d: %s", req.id, e)

    if not photo_sent:
        try:
            await app.bot.send_message(
                chat_id=TRANSACTIONS_BOT_ADMIN_CHAT_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception as e:
            logger.error("Failed to send payment notification to transactions bot: %s", e)


def run_transactions_bot():
    if not TRANSACTIONS_BOT_TOKEN:
        logger.info("TRANSACTIONS_BOT_TOKEN not set, transactions bot disabled.")
        return

    if not TRANSACTIONS_BOT_ADMIN_CHAT_ID:
        logger.info("TRANSACTIONS_BOT_ADMIN_CHAT_ID not set, transactions bot disabled.")
        return

    builder = Application.builder().token(TRANSACTIONS_BOT_TOKEN).connect_timeout(30.0).read_timeout(30.0).write_timeout(30.0).get_updates_read_timeout(300.0).concurrent_updates(True)
    if _is_bale():
        builder = builder.base_url(BALE_API_BASE_URL).base_file_url(BALE_FILE_BASE_URL)
    app = builder.build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CallbackQueryHandler(handle_action_callback))

    logger.info("🔔 Transactions bot starting... platform=%s", TRANSACTIONS_BOT_PLATFORM)

    async def on_startup(application):
        await _send_pending_payments(application, application.bot_data)

    app.post_init = on_startup

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_transactions_bot()
