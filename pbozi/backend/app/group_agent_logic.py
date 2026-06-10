import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update, Message as TGMessage
from telegram.ext import ContextTypes

from app.database import async_session
from app.models import UserPreference, Chat, Message, UsageEvent, Model as DBModel, Project, CreditLedgerEntry
from app.llm import (
    get_provider_for_model, 
    get_default_model, 
    get_chat_tools, 
    request_chat_completion, 
    execute_tool_call,
    extract_reasoning_metadata,
    merge_reasoning_metadata,
    _chat_completion_cost_usd,
    _usd_to_minor,
    _minor_to_usd,
    _estimate_messages_tokens,
    _sum_usage_tokens,
    _complete_usage_event,
    _tool_status_label,
    _sanitize_tool_result_for_llm,
    model_supports_image_input,
)
from app.services.group_billing_service import (
    detect_group_trigger,
    _ensure_telegram_group_record,
    _list_active_group_payers,
    _upsert_group_usage_share_estimate,
    _charge_credit,
    _update_group_usage_share_result,
    _complete_group_usage_event_row,
    split_cost_minor_with_remainder_rule,
)
from app.services.tool_delivery import files_to_deliver_from_python, parse_tool_output

logger = logging.getLogger(__name__)

# This is a specialized version of _run_tool_aware_completion for group chats
async def _run_agent_for_group(
    update: Update,
    db: AsyncSession,
    *,
    trigger_user: UserPreference,
    payer_members: list[UserPreference],
    chat: Chat,
    provider,
    model,
    llm_messages: list[dict],
    group_usage_event_id: int,
    usage_event: UsageEvent,
    status_message_obj=None,
):
    from app.agent_routes import event_generator
    
    sent_msg = status_message_obj
    if sent_msg is None:
        sent_msg = await update.message.reply_text("⏳")
        
    user_text = llm_messages[-1].get("content", "") if llm_messages else ""
    thread_id = f"group_chat_{chat.id}"
    
    full_reply = ""
    tool_calls_count = 0
    
    try:
        import time
        last_edit_time = time.time()
        
        status_labels = {
            "web_search": ("🔍", "جستجو در وب"),
            "run_python": ("🐍", "اجرای کد پایتون"),
            "pdf_generator": ("📄", "تولید فایل PDF"),
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
                    await sent_msg.edit_text(_get_display_text(frames[i % len(frames)]))
                    i += 1
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        # In groups, we don't necessarily track the task for cancellation the same way yet, 
        # but we use the event generator
        gen = event_generator(user_text, thread_id, provider, model, chat_id=chat.id, message_id=update.message.message_id, system_prompt='This is a group chat. Members are paying shared costs.', project_id=chat.project_id)
        
        spinner_task_handle = asyncio.create_task(_spinner_updater())
        
        try:
            async for event in gen:
                raw_data = event.get("data")
                if not raw_data: continue
                try:
                    data = json.loads(raw_data)
                except: continue
                    
                evt_type = data.get("type")
                if evt_type == "content":
                    full_reply += data.get("content", "")
                    current_time = time.time()
                    if current_time - last_edit_time > 2.0: # Slower updates for groups to avoid noise
                        try:
                            await sent_msg.edit_text(_get_display_text() + " ✍️")
                            last_edit_time = current_time
                        except: pass
                elif evt_type == "tool_start":
                    tool_calls_count += 1
                    tool_name = data.get("tool", "tool")
                    icon, label = status_labels.get(tool_name, ("🛠", tool_name))
                    
                    # Deduplicate: only add if no "running" step for this tool exists
                    if not any(s["label"] == label and s["status"] == "running" for s in execution_steps):
                        execution_steps.append({"label": label, "icon": icon, "status": "running"})
                        try:
                            await sent_msg.edit_text(_get_display_text())
                        except: pass
                elif evt_type == "tool_end":
                    # Mark the last running step of this type as completed
                    tool_name = data.get("tool")
                    _, label = status_labels.get(tool_name, ("🛠", tool_name))
                    for step in reversed(execution_steps):
                        if step["label"] == label and step["status"] == "running":
                            step["status"] = "completed"
                            break

                    try:
                        await sent_msg.edit_text(_get_display_text())
                    except: pass
                    # Handle PDF and file generation specifically
                    tool_name = data.get("tool")
                    tool_output = data.get("output")
                    if tool_name == "pdf_generator" and tool_output:
                        try:
                            from app.bot import _maybe_upload_generated_file_to_chat
                            res_dict = json.loads(tool_output)
                            await _maybe_upload_generated_file_to_chat(update, tool_name="pdf_generator", tool_result=res_dict)
                        except: pass
                    elif tool_name == "image_generator" and tool_output:
                        try:
                            res_dict = json.loads(tool_output)
                            if res_dict.get("ok") and res_dict.get("saved_image_paths"):
                                for path in res_dict["saved_image_paths"]:
                                    if __import__('os').path.isfile(path):
                                        with open(path, "rb") as f:
                                            await update.message.reply_photo(photo=f)
                        except Exception as e:
                            pass
                    elif tool_name == "run_python" and tool_output:
                        try:
                            res_dict = parse_tool_output(tool_output)
                            files_to_send = files_to_deliver_from_python(res_dict)
                            if files_to_send:
                                logger.info("Delivering run_python files to group chat: %s", files_to_send)
                                for path in files_to_send:
                                    if __import__('os').path.isfile(path):
                                        ext = __import__('os').path.splitext(path)[1].lower()
                                        with open(path, "rb") as f:
                                            if ext in [".png", ".jpg", ".jpeg", ".webp"]:
                                                await update.message.reply_photo(photo=f)
                                            else:
                                                await update.message.reply_document(document=f)
                        except Exception as exc:
                            logger.warning("Failed to deliver run_python files to group chat: %s", exc)
                elif evt_type == "error":
                    raise Exception(data.get("error"))
        finally:
            spinner_task_handle.cancel()

    except Exception as exc:
        usage_event.status = "failed"
        usage_event.error = str(exc)
        await db.commit()
        raise

    # Usage tracking and billing
    usage_input_tokens = _estimate_messages_tokens(llm_messages)
    usage_output_tokens = 512 # Estimate
    usage_source = "estimated"
    
    actual_cost_usd = _chat_completion_cost_usd(model, usage_input_tokens, usage_output_tokens)
    actual_total_minor = _usd_to_minor(actual_cost_usd)
    
    actual_share_minor_map = split_cost_minor_with_remainder_rule(
        actual_total_minor,
        [member.id for member in payer_members],
        remainder_user_id=trigger_user.id,
    )

    await _complete_usage_event(
        db,
        usage_event,
        input_tokens=usage_input_tokens,
        output_tokens=usage_output_tokens,
        actual_cost_usd=actual_cost_usd,
        usage_source=usage_source,
    )
    await db.flush()

    charge_errors: list[str] = []
    for member in payer_members:
        actual_share_minor = int(actual_share_minor_map.get(member.id, 0))
        idempotency_key = f"group-usage:{group_usage_event_id}:user:{member.id}:charge"
        charged, current_balance = await _charge_credit(
            db,
            user=member,
            amount_usd=_minor_to_usd(actual_share_minor),
            entry_type="chat_completion",
            reason="telegram group shared chat completion",
            usage_event_id=usage_event.id,
            idempotency_key=idempotency_key,
            metadata={
                "usage_event_id": usage_event.id,
                "group_usage_event_id": group_usage_event_id,
                "share_minor": actual_share_minor,
                "input_tokens": usage_input_tokens,
                "output_tokens": usage_output_tokens,
                "model_id": model.id,
                "tool_calls": tool_calls_count,
            },
        )
        if not charged:
            charge_errors.append(f"user:{member.id}")

    await db.commit()
    
    from app.bot import _send_final_response
    await _send_final_response(update, sent_msg, full_reply)

    return True, ""
