
ALBUM_STATUS_MSG = {} # mg_id -> Message object

async def _handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle file uploads."""
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
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ""
        mg_id = update.message.media_group_id

        async with async_session() as db:
            user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            if not await _ensure_onboarding_or_prompt(update, context, user=user): return
            project_id = user.current_project_id
            current_chat_id = user.current_chat_id
            project_upload_mode = bool(context.user_data.get("project_upload_mode"))
            explicit_upload_requested = bool(context.user_data.get("awaiting_project_file_upload")) or project_upload_mode

        # Album logic
        processing_msg = None
        if mg_id:
            async with ALBUM_LOCK:
                if mg_id in ALBUM_STATUS_MSG: processing_msg = ALBUM_STATUS_MSG[mg_id]
                else:
                    processing_msg = await update.message.reply_text("📥 در حال دریافت فایل‌ها...")
                    ALBUM_STATUS_MSG[mg_id] = processing_msg
        else:
            processing_msg = await update.message.reply_text(f"📥 {filename}\n\n📄 در حال پردازش...")

        # Format check
        is_audio = ext in DOCUMENT_AUDIO_EXTENSIONS
        if not is_audio and ext not in {"pdf", "txt", "md", "csv", "docx", "xlsx", "pptx", "html", "jpg", "jpeg", "png", "webp", "json", "py"}:
            await _safe_edit_or_reply(update, processing_msg, f"⚠️ فرمت {ext} پشتیبانی نمیشه.")
            return

        # Download
        abs_dest_dir = os.path.abspath("./uploads/chat_files")
        os.makedirs(abs_dest_dir, exist_ok=True)
        file_path = os.path.join(abs_dest_dir, f"{int(time.time())}_{filename}")
        await _download_telegram_file(context, doc.file_id, file_path)

        if is_audio:
            # (Keep old audio logic here, I will move it in next turn)
            pass

        # Use RAG if large or explicit
        from app.rag import _read_file
        file_text = ""
        is_large = file_size > 500 * 1024
        try:
            file_text = await asyncio.to_thread(_read_file, file_path)
            if len(file_text) > 10000: is_large = True
        except: is_large = True

        use_rag = explicit_upload_requested or is_large or (ext == "pdf" and file_size > 100 * 1024)

        if use_rag:
            # Indexing...
            pass
        else:
            # Direct...
            pass


        if is_audio_document:
            processing_msg = await update.message.reply_text(f"🎙 {filename}\n\n⏳ در حال تبدیل صوت به متن...")
            mime_type = (doc.mime_type or "audio/mp4").strip() or "audio/mp4"
            estimated_audio_seconds = _estimate_audio_duration_from_size(file_size)
            estimated_in_tokens = _estimate_audio_tokens(estimated_audio_seconds) + _estimate_text_tokens(VOICE_TRANSCRIPTION_PROMPT)
            estimated_out_tokens = max(64, estimated_in_tokens // 6)
            async with async_session() as gate_db:
                transcription_config = await _get_or_create_transcription_config(gate_db)
                if not transcription_config.is_active:
                    await processing_msg.edit_text("تبدیل صوت به متن در حال حاضر غیرفعاله.")
                    return
                if not (transcription_config.api_key or "").strip():
                    await processing_msg.edit_text("کلید API برای تبدیل صوت به متن تنظیم نشده.")
                    return
                gate_user = await get_user(gate_db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
            estimated_cost = _transcription_cost_usd(transcription_config, estimated_in_tokens, estimated_out_tokens)
            if not _has_credit_for_cost(gate_user, estimated_cost):
                gate_user.pending_action_payload = {
                    "action_type": "audio_document_transcription",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {
                        "doc_file_id": doc.file_id,
                        "filename": filename,
                        "mime_type": (doc.mime_type or "audio/mp4").strip() or "audio/mp4",
                        "file_size": file_size,
                        "project_id": project_id,
                        "explicit_upload_requested": explicit_upload_requested,
                    }
                }
                await gate_db.commit()
                await processing_msg.edit_text(
                    _insufficient_credit_text(
                        needed=estimated_cost,
                        balance=_credit_balance(gate_user),
                        action_label="تبدیل فایل صوتی",
                    ),
                    reply_markup=_insufficient_credit_kb()
                )
                return

            try:
                # Absolute path for storage
                abs_dest_dir = os.path.abspath(f"./uploads/project_{project_id}") if (project_id and explicit_upload_requested) else os.path.abspath("./uploads/chat_files")
                os.makedirs(abs_dest_dir, exist_ok=True)
                file_path = os.path.join(abs_dest_dir, filename)

                await _download_telegram_file(context, doc.file_id, file_path)

                # For audio, we need to read it back
                if is_audio_document:
                    with open(file_path, "rb") as fp:
                        audio_bytes = fp.read()
            except Exception as e:
                logger.error(f"Download error: {str(e)}")
                err_detail = f"\n(Error: {str(e)})" if uid == ADMIN_ID else ""
                platform_name = "بله" if _is_bale_platform() else "تلگرام"
                await processing_msg.edit_text(f"❌ مشکلی در دریافت فایل از {platform_name} پیش آمد.{err_detail}")
                return

            uploaded_file_id = None
            usage_event_id = None
            async with async_session() as db:
                user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                uploaded_file = await _record_uploaded_file(
                    db,
                    user=user,
                    chat_id=current_chat_id,
                    project_id=project_id,
                    telegram_file_id=doc.file_id,
                    telegram_file_unique_id=doc.file_unique_id,
                    filename=filename,
                    mime_type=mime_type,
                    file_type=ext or "audio",
                    size_bytes=file_size,
                    storage_path=file_path,
                    caption=update.message.caption or None,
                    status="stored",
                    metadata={"source": "telegram_document_audio"},
                )
                uploaded_file_id = uploaded_file.id
                usage_event = await _create_usage_event(
                    db,
                    user=user,
                    chat_id=current_chat_id,
                    message_id=None,
                    uploaded_file_id=uploaded_file_id,
                    operation_type="voice_transcription",
                    provider_name=transcription_config.provider,
                    model=None,
                    estimated_cost_usd=estimated_cost,
                    request_id=f"telegram:{update.update_id}:audio_doc:{doc.file_unique_id}",
                    metadata={
                        "audio_mime_type": mime_type,
                        "audio_file_size_bytes": file_size,
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
                        uploaded_file.processed_at = datetime.now(timezone.utc)
                    await db.commit()

                logger.error(f"Voice transcription error for audio document: {str(exc)}")
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
                        uploaded_file.processed_at = datetime.now(timezone.utc)
                    await db.commit()
                await processing_msg.edit_text("❌ متن قابل استفاده‌ای از فایل صوتی استخراج نشد.")
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
                charged, current_balance = await _charge_credit(
                    db,
                    user=user,
                    amount_usd=actual_cost,
                    entry_type="voice_transcription",
                    reason="telegram audio document transcription",
                    usage_event_id=usage_event.id if usage_event else None,
                    idempotency_key=f"usage:{usage_event.id}:charge" if usage_event else None,
                    metadata={
                        "usage_event_id": usage_event.id if usage_event else None,
                        "audio_file_unique_id": doc.file_unique_id,
                        "transcription_model": transcription_config.model,
                        "input_tokens": usage_input_tokens,
                        "output_tokens": usage_output_tokens,
                    },
                )
                if not charged:
                    if usage_event:
                        usage_event.status = "billing_failed"
                        usage_event.error = "insufficient credit during audio document transcription charge"
                    await db.commit()
                    await processing_msg.edit_text(
                        _insufficient_credit_text(
                            needed=actual_cost,
                            balance=current_balance,
                            action_label="ثبت هزینه تبدیل صوت",
                        ),
                        reply_markup=_insufficient_credit_kb()
                    )
                    return
                if uploaded_file:
                    uploaded_file.status = "processed"
                    uploaded_file.processed_at = datetime.now(timezone.utc)
                await db.commit()

            if project_id and explicit_upload_requested:
                transcript_path = f"{file_path}.transcript.txt"
                with open(transcript_path, "w", encoding="utf-8") as f:
                    f.write(transcript)
                try:
                    async with async_session() as db:
                        user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                        if not await user_can_access_project(db, user, int(project_id)):
                            await processing_msg.edit_text("❌ این پروژه در دسترس تو نیست.")
                            return
                        emb = await _get_emb_config(db)
                        estimated_tokens = _estimate_text_tokens(transcript)
                        estimated_embed_cost = _embedding_cost_usd(emb, estimated_tokens)
                        if not _has_credit_for_cost(user, estimated_embed_cost):
                            user.pending_action_payload = {
                                "action_type": "document_embedding",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "payload": {
                                    "doc_file_id": doc.file_id,
                                    "filename": filename,
                                    "project_id": project_id,
                                    "explicit_upload_requested": explicit_upload_requested,
                                }
                            }
                            await db.commit()
                            await processing_msg.edit_text(
                                _insufficient_credit_text(
                                    needed=estimated_embed_cost,
                                    balance=_credit_balance(user),
                                    action_label="ایندکس فایل صوتی",
                                ),
                                reply_markup=_insufficient_credit_kb()
                            )
                            return

                        api_key = emb.api_key if emb else None
                        model_name = emb.model if emb else None
                        provider = emb.provider if emb else "google"
                        base_url = emb.base_url if emb else None
                        
                        # Create record first to get real ID
                        doc_record = Document(
                            project_id=project_id,
                            filename=filename,
                            file_type=ext or "audio",
                            file_path=file_path,
                            chunk_count=0,
                        )
                        db.add(doc_record)
                        await db.commit()
                        await db.refresh(doc_record)

                        # Start background indexing
                        asyncio.create_task(
                            _background_index_with_notification(
                                bot=context.bot,
                                chat_id=chat_id,
                                project_id=project_id,
                                document_id=doc_record.id,
                                file_path=transcript_path, # Use transcript path for audio
                                uid=uid,
                                update_id=update.update_id,
                                file_unique_id=doc.file_unique_id,
                                estimated_cost=estimated_embed_cost,
                                estimated_tokens=estimated_tokens,
                                filename=filename,
                                api_key=api_key,
                                model=model_name,
                                provider=provider,
                                base_url=base_url,
                                processing_msg_id=processing_msg.message_id,
                            )
                        )
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    retry_kb = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🔄 تلاش مجدد", callback_data=_retry_upload_callback_data(project_id, filename))]]
                    )
                    logger.error(f"Processing error: {str(e)}")
                    await processing_msg.edit_text("❌ خطایی در پردازش فایل رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=retry_kb)
                    return
            else:
                await _send_or_edit_formatted(processing_msg, _voice_ack_text(transcript))
                await _process_chat_text_turn(
                    update,
                    uid=uid,
                    content=transcript,
                    uploaded_file_id=uploaded_file_id,
                    status_message_obj=processing_msg,
                )
            return

        SUPPORTED_KB_EXTS = {"pdf", "txt", "md", "csv", "docx", "xlsx", "pptx", "html", "jpg", "jpeg", "png", "webp"}
        if ext not in SUPPORTED_KB_EXTS:
            # For non-supported formats, just describe the file to the AI
            async with async_session() as db:
                if current_chat_id:
                    db.add(Message(
                        chat_id=current_chat_id,
                        role="user",
                        content=f"[فایل ارسال شده: {filename} ({size_mb:.1f}MB) — فرمت {ext} پشتیبانی نمیشه]"
                    ))
                    await db.commit()
            await update.message.reply_text(f"⚠️ فرمت {ext} برای Knowledge Base پشتیبانی نمیشه\n\nفقط: فایل‌های متنی، آفیس و عکس\n\nاگه سوال درباره فایل داری مستقیم بپرس")
            return

        if True: # Always use RAG
            # ========================================
            # Index into Knowledge Base (RAG)
            # ========================================
            processing_msg = await update.message.reply_text(f"📥 {filename}\n\n📄 در حال پردازش...")

            # Download file
            try:
                # Absolute path for storage
                abs_dest_dir = os.path.abspath(f"./uploads/project_{project_id}") if (project_id and explicit_upload_requested) else os.path.abspath("./uploads/chat_files")
                os.makedirs(abs_dest_dir, exist_ok=True)
                file_path = os.path.join(abs_dest_dir, filename)

                await _download_telegram_file(context, doc.file_id, file_path)
            except Exception as e:
                logger.error(f"Download error: {str(e)}")
                err_detail = f"\n(Error: {str(e)})" if uid == ADMIN_ID else ""
                platform_name = "بله" if _is_bale_platform() else "تلگرام"
                await processing_msg.edit_text(f"❌ مشکلی در دریافت فایل از {platform_name} پیش آمد.{err_detail}")
                return

            # Index into RAG
            try:
                from app.rag import index_document, _read_file

                estimated_tokens = 0
                try:
                    # Run _read_file in a separate thread so it doesn't block the async event loop
                    file_text = await asyncio.to_thread(_read_file, file_path)
                    estimated_tokens = _estimate_text_tokens(file_text)
                except Exception:
                    estimated_tokens = max(1, file_size // 4)

                uploaded_file_id = None
                async with async_session() as db:
                    user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                    
                    if not current_chat_id and not project_id:
                        # Auto-create chat if they don't have one
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
                        current_chat_id = chat.id

                    if project_id and not await user_can_access_project(db, user, int(project_id)):
                        await processing_msg.edit_text("❌ این پروژه در دسترس تو نیست.")
                        return
                    uploaded_file = await _record_uploaded_file(
                        db,
                        user=user,
                        chat_id=current_chat_id,
                        project_id=project_id,
                        telegram_file_id=doc.file_id,
                        telegram_file_unique_id=doc.file_unique_id,
                        filename=filename,
                        mime_type=doc.mime_type,
                        file_type=ext,
                        size_bytes=file_size,
                        storage_path=file_path,
                        caption=update.message.caption or None,
                        status="stored",
                        metadata={"source": "telegram_project_document"},
                    )
                    uploaded_file_id = uploaded_file.id
                    emb_config = (await db.execute(select(EmbeddingConfig).where(EmbeddingConfig.is_active == True))).scalar_one_or_none()
                    estimated_cost = _embedding_cost_usd(emb_config, estimated_tokens)
                    if not _has_credit_for_cost(user, estimated_cost):
                        user.pending_action_payload = {
                            "action_type": "document_embedding",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "payload": {
                                "doc_file_id": doc.file_id,
                                "filename": filename,
                                "project_id": project_id,
                                "explicit_upload_requested": explicit_upload_requested,
                            }
                        }
                        await db.commit()
                        await processing_msg.edit_text(
                            _insufficient_credit_text(
                                needed=estimated_cost,
                                balance=_credit_balance(user),
                                action_label="ایندکس فایل",
                            ),
                            reply_markup=_insufficient_credit_kb()
                        )
                        return
                    api_key = emb_config.api_key if emb_config else None
                    model = emb_config.model if emb_config else None
                    provider = emb_config.provider if emb_config else "google"
                    base_url = emb_config.base_url if emb_config else None
                    
                    # Create record first to get real ID
                    from app.models import Document
                    doc_record = Document(
                        project_id=project_id,
                        chat_id=current_chat_id if not project_id else None,
                        filename=filename,
                        file_type=ext,
                        file_path=file_path,
                        chunk_count=0,
                    )
                    db.add(doc_record)
                    
                    usage_event = await _create_usage_event(
                        db,
                        user=user,
                        chat_id=current_chat_id,
                        message_id=None,
                        operation_type="rag_embedding",
                        uploaded_file_id=uploaded_file_id,
                        provider_name=emb_config.provider if emb_config else None,
                        model=None,
                        estimated_cost_usd=estimated_cost,
                        request_id=f"telegram:{update.update_id}:rag:{project_id if project_id else f'chat_{current_chat_id}'}:{doc_record.id}:{doc.file_unique_id}",
                        metadata={
                            "project_id": project_id,
                            "filename": filename,
                            "estimated_tokens": estimated_tokens,
                            "embedding_model": model,
                        },
                    )
                    usage_event.status = "authorized"
                    await db.commit()
                    await db.refresh(doc_record)

                # Start background indexing
                asyncio.create_task(
                    _background_index_with_notification(
                        bot=context.bot,
                        chat_id=chat_id,
                        project_id=project_id,
                        document_id=doc_record.id,
                        file_path=file_path,
                        uid=uid,
                        update_id=update.update_id,
                        file_unique_id=doc.file_unique_id,
                        estimated_cost=estimated_cost,
                        estimated_tokens=estimated_tokens,
                        filename=filename,
                        api_key=api_key,
                        model=model,
                        provider=provider,
                        base_url=base_url,
                        processing_msg_id=processing_msg.message_id,
                        target_chat_id=current_chat_id if not project_id else None
                    )
                )

                if project_upload_mode:
                    await update.message.reply_text("آپلود دریافت شد.", reply_markup=upload_mode_kb())

                return
            except Exception as e:
                import traceback
                traceback.print_exc()
                retry_kb = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔄 تلاش مجدد", callback_data=_retry_upload_callback_data(project_id, filename))]]
                )
                logger.error(f"Processing error: {str(e)}")
                await processing_msg.edit_text("❌ خطایی در پردازش فایل رخ داد. لطفاً دوباره تلاش کنید.", reply_markup=retry_kb)
                return
        else:
            # ========================================
            # NOT IN PROJECT → Just extract text and add to chat context
            # ========================================
            file_caption = update.message.caption or ""
            processing_msg = await update.message.reply_text(f"📥 {filename}\n\n📄 در حال خواندن...")

            # Download file
            try:
                # Absolute path for storage
                abs_dest_dir = os.path.abspath("./uploads/chat_files")
                os.makedirs(abs_dest_dir, exist_ok=True)
                file_path = os.path.join(abs_dest_dir, filename)

                await _download_telegram_file(context, doc.file_id, file_path)
            except Exception as e:
                logger.error(f"Download error: {str(e)}")
                err_detail = f"\n(Error: {str(e)})" if uid == ADMIN_ID else ""
                platform_name = "بله" if _is_bale_platform() else "تلگرام"
                await processing_msg.edit_text(f"❌ مشکلی در دریافت فایل از {platform_name} پیش آمد.{err_detail}")
                return

            # Extract text
            try:
                from app.rag import _read_file
                text = _read_file(file_path)
                # Truncate to reasonable size for chat
                if len(text) > 10000:
                    text = text[:10000] + "\n... (فایل ادامه داره)"
            except Exception as e:
                text = f"[خطا در خواندن فایل: {str(e)}]"

            async with async_session() as db:
                user = await get_user(db, uid)
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
                uploaded_file = await _record_uploaded_file(
                    db,
                    user=user,
                    chat_id=chat_id,
                    project_id=None,
                    telegram_file_id=doc.file_id,
                    telegram_file_unique_id=doc.file_unique_id,
                    filename=filename,
                    mime_type=doc.mime_type,
                    file_type=ext,
                    size_bytes=file_size,
                    storage_path=file_path,
                    caption=file_caption or None,
                    status="processed",
                    metadata={"source": "telegram_chat_document"},
                )
                await db.commit()
                uploaded_file_id = uploaded_file.id

            if file_caption and not update.message.media_group_id:
                # ═══ Caption = question → Answer directly with file content ═══
                # We reuse processing_msg as status_message_obj for smooth transition
                # try:
                #     await processing_msg.delete()
                # except Exception:
                #     pass

                # If it's an image, include vision tag
                is_img = any(filename.lower().endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp"))
                if is_img:
                    msg_content = f"[عکس ارسال شده: ID={uploaded_file_id}]\n{file_caption}"
                else:
                    msg_content = file_caption

                # Add file + question as user message
                async with async_session() as db:
                    user_msg = Message(
                        chat_id=chat_id,
                        role="user",
                        content=msg_content,
                    )
                    db.add(user_msg)
                    await db.commit()
                    await db.refresh(user_msg)

                # Stream reply
                async with async_session() as db:
                    user = await get_user(db, uid, update.effective_user.first_name or "", update.effective_user.username or "")
                    model_id = user.current_model_id
                    if model_id:
                        provider, model = await get_provider_for_model(db, model_id)
                        if not provider or not model:
                            provider, model = await get_default_model(db)
                    else:
                        provider, model = await get_default_model(db)

                    if not provider or not model:
                        await update.message.reply_text("مدلی تنظیم نشده")
                        return

                    current_chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()
                    if not current_chat:
                        await update.message.reply_text("چت پیدا نشد")
                        return
                    system_content = await get_effective_system_prompt(db, chat=current_chat, user=user, include_tool_guidance=False)
                    user_display = user.preferred_name or user.first_name or uid
                    system_content = f"{system_content}\n\nThe user's name is {user_display}. Address them by their name sometimes."

                    # Only add text context if it's NOT an image (vision will handle image)
                    if not is_img:
                        system_content += (
                            f"\n\nUser uploaded file '{filename}'. Use this extracted file content to answer:\n"
                            f"{text}"
                        )

                    # RAG
                    project_id = user.current_project_id
                    if project_id or chat_id:
                        emb = await _get_emb_config(db); docs = await _search_with_config(project_id, file_caption, emb_config=emb, n_results=5, chat_id=chat_id)
                        if docs:
                            ctx = "\n\n---\n\n".join([d["content"] for d in docs])
                            system_content += f"\n\nRelevant documents context:\n{ctx}"

                    # Build history (last 40 messages)
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

                    supports_vis = await asyncio.to_thread(model_supports_image_input, model)
                    llm_messages = await _resolve_vision_messages(db, llm_messages, supports_vis)
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
                            chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none(),
                            provider=provider,
                            model=model,
                            llm_messages=llm_messages,
                            proj_label=proj_label,
                            allow_tools=True,
                            uploaded_file_id=uploaded_file_id,
                            status_message_obj=processing_msg,
                        )
                    except Exception as e2:
                        await update.message.reply_text(f"❌ {str(e2)}")
                        return

                    await _save_assistant_message_and_post_actions(
                        update,
                        db,
                        uid=uid,
                        chat=(await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none(),
                        model=model,
                        llm_messages=llm_messages,
                        assistant_text=full_reply,
                        user_text=file_caption,
                    )
                await _mark_update_completed(update)
            else:
                # ═══ No caption → Save file, ask what they want ═══
                # Save file content to user_data for follow-up question
                _clear_pending_inputs(context)

                # If it's an image, include vision tag
                is_img = any(filename.lower().endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp"))
                if is_img:
                    msg_content = f"[عکس ارسال شده: ID={uploaded_file_id}]"
                else:
                    msg_content = f"[فایل: {filename}]"

                context.user_data["pending_file"] = {
                    "filename": filename,
                    "text": text[:8000],  # truncate for memory
                    "chat_id": chat_id,
                    "uploaded_file_id": uploaded_file_id,
                }
                async with async_session() as db:
                    db.add(Message(
                        chat_id=chat_id,
                        role="user",
                        content=msg_content
                    ))
                    await db.commit()

                if is_img:
                    reply_text = (
                        "عکس رو به صورت فایل گرفتم.\n"
                        "می‌تونم توصیفش کنم، متن داخلش رو بخونم یا به سوالت درباره‌اش جواب بدم. دوست داری از کجا شروع کنم؟"
                    )
                else:
                    reply_text = (
                        f"فایل {filename} رو گرفتم.\n"
                        "می‌تونم خلاصه‌اش کنم، نکته‌های مهمش رو دربیارم، ترجمه کنم یا متنش رو استخراج کنم. دوست داری کدومش رو انجام بدم؟"
                    )

                await processing_msg.edit_text(reply_text)
                await _mark_update_completed(update)
    finally:
        _unregister_user_task(chat_id, task)
        await _finish_album_update(update, context, handle_message)


# ═══════════════════════════════════════
#  HELPER: Vision helpers
# ═══════════════════════════════════════
def _encode_image_to_base64(file_path: str) -> str:
    """Encode an image file to base64 string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _build_vision_content(text: str, image_b64: str) -> list:
    """Build OpenAI-compatible vision content parts."""
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ]


# ═══════════════════════════════════════
#  PHOTO HANDLER — Image with/without caption
# ═══════════════════════════════════════
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
