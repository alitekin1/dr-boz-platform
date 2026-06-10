async def _handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads with multi-file queue support."""
    await _register_album_update(update)
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    doc = update.message.document
    if not doc: return
    if not await _claim_update_once(update): return
    task = _register_user_task(chat_id)
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

        # ─── Album & Status Message Consolidation ───
        processing_msg = None
        if mg_id:
            async with ALBUM_LOCK:
                if mg_id in ALBUM_STATUS_MSG: processing_msg = ALBUM_STATUS_MSG[mg_id]
                else:
                    processing_msg = await update.message.reply_text("📥 در حال دریافت فایل‌ها...")
                    ALBUM_STATUS_MSG[mg_id] = processing_msg
        else:
            processing_msg_id = context.user_data.get("active_upload_msg_id")
            if processing_msg_id:
                try:
                    processing_msg = await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=processing_msg_id, 
                        text=f"📥 {filename}\n\n📄 در حال پردازش..."
                    )
                except: pass
            
            if not processing_msg:
                processing_msg = await update.message.reply_text(f"📥 {filename}\n\n📄 در حال پردازش...")
                context.user_data["active_upload_msg_id"] = processing_msg.message_id

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
        except:
            await _safe_edit_or_reply(update, processing_msg, "❌ مشکلی در دریافت فایل پیش آمد.")
            return

        if is_audio:
            await _handle_audio_doc_inline(update, context, user, project_id, current_chat_id, doc, file_path, filename, ext, explicit_upload_requested, processing_msg)
            return

        # ─── Process Decision ───
        from app.rag import _read_file
        file_text = ""
        is_large = file_size > 500 * 1024
        try:
            file_text = await asyncio.to_thread(_read_file, file_path)
            if len(file_text) > 10000: is_large = True
        except: is_large = True

        if is_large and not (user.is_admin or user.is_pro):
            await _send_pro_restriction_message(update, context)
            return

        use_rag = explicit_upload_requested or is_large or (ext == "pdf" and file_size > 100 * 1024)

        if use_rag:
            await _perform_rag_indexing(update, context, user, project_id, current_chat_id, doc, file_path, filename, file_size, ext, explicit_upload_requested, processing_msg)
        else:
            await _perform_direct_extraction(update, context, user, current_chat_id, doc, file_path, filename, file_text, ext, processing_msg)

    except Exception:
        logger.exception("Upload failed")
        await _safe_edit_or_reply(update, processing_msg, "❌ خطایی در پردازش رخ داد.")
    finally:
        _unregister_user_task(chat_id, task)
        await _finish_album_update(update, context, handle_message)

async def _safe_edit_or_reply(update, msg, text):
    try:
        if msg: await msg.edit_text(text)
        else: await update.message.reply_text(text)
    except: pass

async def _perform_direct_extraction(update: Update, context: ContextTypes.DEFAULT_TYPE, user, chat_id, doc, file_path, filename, text, ext, processing_msg):
    async with async_session() as db:
        if not chat_id:
            chat = Chat(title="💬 چت جدید", model_id=user.current_model_id, user_preference_id=user.id)
            db.add(chat); await db.commit(); await db.refresh(chat)
            chat_id = chat.id; user.current_chat_id = chat.id; await db.commit()
            
        uploaded_file = await _record_uploaded_file(db, user=user, chat_id=chat_id, filename=filename, file_type=ext, size_bytes=doc.file_size, storage_path=file_path, status="completed")
        uploaded_file_id = uploaded_file.id
        msg_content = f"[فایل: {filename} (ID={uploaded_file_id})]"
        db.add(Message(chat_id=chat_id, role="user", content=msg_content))
        await db.commit()

    mg_id = update.message.media_group_id
    if mg_id:
        await _register_album_update(update, extracted_text=text, file_id=uploaded_file_id)
    else:
        if "pending_files_queue" not in context.user_data: context.user_data["pending_files_queue"] = []
        context.user_data["pending_files_queue"].append({"filename": filename, "text": text[:10000], "id": uploaded_file_id})
        
        caption = update.message.caption
        if caption:
            await handle_message(update, context, forced_text=caption)
        else:
            q_len = len(context.user_data["pending_files_queue"])
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 پردازش و پاسخ", callback_data="process_queue")]])
            await processing_msg.edit_text(f"✅ {q_len} فایل آماده شد. باز هم می‌فرستی یا پردازش کنم؟", reply_markup=kb)

async def _perform_rag_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE, user, project_id, chat_id, doc, file_path, filename, file_size, ext, explicit_upload_requested, processing_msg):
    from app.rag import _read_file
    try:
        file_text = await asyncio.to_thread(_read_file, file_path)
        estimated_tokens = _estimate_text_tokens(file_text)
    except:
        estimated_tokens = max(1, file_size // 4)

    async with async_session() as db:
        user = await get_user(db, user.id)
        if not chat_id and not project_id:
            chat = Chat(title="💬 چت جدید", model_id=user.current_model_id, user_preference_id=user.id)
            db.add(chat); await db.commit(); await db.refresh(chat)
            chat_id = chat.id; user.current_chat_id = chat.id; await db.commit()
            
        uploaded_file = await _record_uploaded_file(db, user=user, chat_id=chat_id, project_id=project_id, filename=filename, file_type=ext, size_bytes=file_size, storage_path=file_path, status="stored")
        uploaded_file_id = uploaded_file.id
        
        emb_config = (await db.execute(select(EmbeddingConfig).where(EmbeddingConfig.is_active == True))).scalar_one_or_none()
        cost = _embedding_cost_usd(emb_config, estimated_tokens)
        
        from app.models import Document
        doc_record = Document(project_id=project_id, chat_id=chat_id if not project_id else None, filename=filename, file_type=ext, file_path=file_path)
        db.add(doc_record)
        
        usage = await _create_usage_event(db, user=user, chat_id=chat_id, operation_type="rag_embedding", uploaded_file_id=uploaded_file_id, estimated_cost_usd=cost, request_id=f"tg:{update.update_id}:rag:{doc.file_unique_id}")
        usage.status = "authorized"; await db.commit(); await db.refresh(doc_record)

    mg_id = update.message.media_group_id
    if mg_id:
        await _register_album_update(update, file_id=uploaded_file_id)
    else:
        if "pending_files_queue" not in context.user_data: context.user_data["pending_files_queue"] = []
        context.user_data["pending_files_queue"].append({"filename": filename, "id": uploaded_file_id, "rag": True})
        
        caption = update.message.caption
        if caption:
            await handle_message(update, context, forced_text=caption)
        else:
            q_len = len(context.user_data["pending_files_queue"])
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 پردازش و پاسخ", callback_data="process_queue")]])
            await processing_msg.edit_text(f"✅ {q_len} فایل آماده شد (شامل فایل سنگین).", reply_markup=kb)

    asyncio.create_task(_background_index_with_notification(bot=context.bot, chat_id=update.effective_chat.id, project_id=project_id, document_id=doc_record.id, file_path=file_path, uid=user.telegram_id, update_id=update.update_id, file_unique_id=doc.file_unique_id, estimated_cost=cost, estimated_tokens=estimated_tokens, filename=filename, api_key=emb_config.api_key if emb_config else None, model=emb_config.model if emb_config else None, provider=emb_config.provider if emb_config else "google", base_url=emb_config.base_url if emb_config else None, processing_msg_id=processing_msg.message_id, target_chat_id=chat_id if not project_id else None))

async def _handle_audio_doc_inline(update, context, user, project_id, chat_id, doc, file_path, filename, ext, explicit_upload, processing_msg):
    mime_type = (doc.mime_type or "audio/mp4").strip() or "audio/mp4"
    estimated_audio_seconds = _estimate_audio_duration_from_size(doc.file_size)
    async with async_session() as db: transcription_config = await _get_or_create_transcription_config(db)
    estimated_in_tokens = _estimate_audio_tokens(estimated_audio_seconds); estimated_out_tokens = 512
    cost = _transcription_cost_usd(transcription_config, estimated_in_tokens, estimated_out_tokens)
    transcript = await _execute_voice_transcription(update, context, uid=user.telegram_id, voice_file_id=doc.file_id, voice_file_unique_id=doc.file_unique_id, duration=estimated_audio_seconds, mime_type=mime_type, project_id=project_id, explicit_upload_requested=explicit_upload, project_upload_mode=False, processing_msg=processing_msg, transcription_config=transcription_config, estimated_cost=cost, estimated_in_tokens=estimated_in_tokens, estimated_out_tokens=estimated_out_tokens, voice_file_size=doc.file_size)
    if transcript and explicit_upload:
        transcript_path = file_path + ".txt"
        with open(transcript_path, "w", encoding="utf-8") as f: f.write(transcript)
        async with async_session() as db:
            emb = (await db.execute(select(EmbeddingConfig).where(EmbeddingConfig.is_active == True))).scalar_one_or_none()
            doc_record = Document(project_id=project_id, filename=filename, file_type="audio", file_path=file_path)
            db.add(doc_record); await db.commit(); await db.refresh(doc_record)
            asyncio.create_task(_background_index_with_notification(bot=context.bot, chat_id=chat_id, project_id=project_id, document_id=doc_record.id, file_path=transcript_path, uid=user.telegram_id, update_id=update.update_id, file_unique_id=doc.file_unique_id, estimated_cost=0, estimated_tokens=_estimate_text_tokens(transcript), filename=filename, api_key=emb.api_key if emb else None, model=emb.model if emb else None, provider=emb.provider if emb else "google", base_url=emb.base_url if emb else None, processing_msg_id=processing_msg.message_id))
