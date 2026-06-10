import sys
import os

with open("backend/app/bot.py", "r") as f:
    lines = f.readlines()

# 1. Update _background_index_with_notification to include keyboard in final messages
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "async def _background_index_with_notification(" in line:
        start_idx = i
    if "ALBUM_STATUS_MSG = {}" in line and start_idx != -1:
        end_idx = i
        break

if start_idx == -1 or end_idx == -1:
    print(f"Error: Could not find _background_index_with_notification boundaries ({start_idx}, {end_idx})")
    sys.exit(1)

new_bg_func = """
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
    processing_msg_id: int = None,
    target_chat_id: int | None = None,
):
    \"\"\"
    Background task for Telegram bot indexing.
    Runs indexing, charges credits, updates usage event, and notifies user.
    \"\"\"
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

    if processing_msg_id:
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
                        f"{frames[i % len(frames)]} {phase_text}\\n"
                        f"📄 فایل: {filename}\\n\\n"
                        f"این کار در پس‌زمینه انجام می‌شود و شما می‌توانید به کارهای دیگر خود بپردازید. ⏳"
                    )

                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=processing_msg_id,
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
            chat_id=target_chat_id
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
                usage_event.completed_at = datetime.now(timezone.utc)
                usage_event.units = doc.chunk_count

            charged, _ = await _charge_credit(
                db,
                user=user,
                amount_usd=estimated_cost,
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
            success_msg = f"✅ فایل {filename} با موفقیت پردازش و در حافظه ایندکس شد. ({doc.chunk_count} قطعه)"
            kb = upload_queue_kb()
            if processing_msg_id:
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=processing_msg_id, text=success_msg, reply_markup=kb)
                except Exception:
                    await bot.send_message(chat_id=chat_id, text=success_msg, reply_markup=kb)
            else:
                await bot.send_message(chat_id=chat_id, text=success_msg, reply_markup=kb)

    except Exception as e:
        if spinner_task:
            spinner_task.cancel()
        if typing_task:
            typing_task.cancel()
        logger.exception(f"Error in background indexing for {filename}")
        error_msg = f"❌ متاسفانه در پردازش فایل {filename} خطایی رخ داد: {str(e)}\\n\\nمی‌توانی لیست را پاک کنی یا با بقیه فایل‌ها ادامه دهی 👇"
        kb = upload_queue_kb()
        if processing_msg_id:
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=processing_msg_id, text=error_msg, reply_markup=kb)
            except Exception:
                await bot.send_message(chat_id=chat_id, text=error_msg, reply_markup=kb)
        else:
            try:
                await bot.send_message(chat_id=chat_id, text=error_msg, reply_markup=kb)
            except:
                pass
"""

# Replace the block
result = lines[:start_idx] + [new_bg_func + "\n"] + lines[end_idx:]

with open("backend/app/bot.py", "w") as f:
    f.writelines(result)

print("Surgically updated _background_index_with_notification.")
