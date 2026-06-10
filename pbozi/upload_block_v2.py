async def _handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads.
    
    Consolidates albums. Uses direct extraction for small files (<500KB or <10k chars) 
    and Knowledge Base indexing (RAG) for large files or explicit project uploads.
    """
    await _register_album_update(update)
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    doc = update.message.document

    if not doc:
        await update.message.reply_text("فایل رو بفرست 📄")
        return
    
    if not await _claim_update_once(update):
        return

    task = _register_user_task(chat_id)
    try:
        filename = doc.file_name or "document"
        file_size = doc.file_size or 0
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        mg_id = update.message.media_group_id

        async with async_session() as db:
            user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            if not await _ensure_onboarding_or_prompt(update, context, user=user):
                return
            project_id = user.current_project_id
            current_chat_id = user.current_chat_id
            project_upload_mode = bool(context.user_data.get("project_upload_mode"))
            explicit_upload_requested = bool(context.user_data.get("awaiting_project_file_upload")) or project_upload_mode

        # ─── Album & Processing Message ───
        processing_msg = None
        if mg_id:
            async with ALBUM_LOCK:
                if mg_id in ALBUM_STATUS_MSG:
                    processing_msg = ALBUM_STATUS_MSG[mg_id]
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
        except Exception:
            await _safe_edit_or_reply(update, processing_msg, "❌ مشکلی در دریافت فایل پیش آمد.")
            return

        if is_audio:
            await _handle_audio_doc_inline(update, context, user, project_id, current_chat_id, doc, file_path, filename, ext, explicit_upload_requested, processing_msg)
            return

        # ─── Process: Direct vs RAG ───
        from app.rag import _read_file
        file_text = ""
        is_large = file_size > 500 * 1024 # > 500KB
        try:
            file_text = await asyncio.to_thread(_read_file, file_path)
            if len(file_text) > 10000: is_large = True
        except: is_large = True

        if is_large and not (user.is_admin or user.is_pro):
            await _send_pro_restriction_message(update, context)
            return

        # DECISION: RAG or Direct?
        use_rag = explicit_upload_requested or is_large or (ext == "pdf" and file_size > 100 * 1024)

        if use_rag:
            if not mg_id: await processing_msg.edit_text(f"📥 {filename}\n\n🧠 در حال ایندکس در حافظه...")
            await _perform_rag_indexing(update, context, user, project_id, current_chat_id, doc, file_path, filename, file_size, ext, explicit_upload_requested, processing_msg)
        else:
            if not mg_id: await processing_msg.edit_text(f"📥 {filename}\n\n✅ خوانده شد.")
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
        context.user_data["pending_file"] = {"filename": filename, "text": text[:10000], "chat_id": chat_id, "uploaded_file_id": uploaded_file_id}
        caption = update.message.caption
        if caption:
            await handle_message(update, context, forced_text=caption)
        else:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 پردازش و پاسخ", callback_data=f"process_file_{uploaded_file_id}")]])
            await processing_msg.edit_text(f"✅ فایل {filename} دریافت شد. چه سوالی داری؟", reply_markup=kb)

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

    asyncio.create_task(_background_index_with_notification(bot=context.bot, chat_id=update.effective_chat.id, project_id=project_id, document_id=doc_record.id, file_path=file_path, uid=user.telegram_id, update_id=update.update_id, file_unique_id=doc.file_unique_id, estimated_cost=cost, estimated_tokens=estimated_tokens, filename=filename, api_key=emb_config.api_key if emb_config else None, model=emb_config.model if emb_config else None, provider=emb_config.provider if emb_config else "google", base_url=emb_config.base_url if emb_config else None, processing_msg_id=processing_msg.message_id, target_chat_id=chat_id if not project_id else None))

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
