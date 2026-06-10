import os
import base64
import json
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.database import get_session
from app.models import Project, Chat, Message, Document, UserPreference
from app.schemas import ProjectCreate, ProjectOut, ProjectShareOut, ProjectUpdate, ChatCreate, ChatOut, MessageOut, ChatRequest
from pydantic import BaseModel
from app.llm import (
    LLMProviderError,
    execute_tool_call,
    extract_reasoning_metadata,
    generate_title,
    get_chat_tools,
    get_default_model,
    get_effective_system_prompt,
    get_emb_config,
    get_provider_for_model,
    merge_reasoning_metadata,
    request_chat_completion,
    resolve_model_for_completion,
    resolve_multimodal_tags_in_messages,
    suggest_models_for_input_capability,
)
from app.rag import index_document, search_documents, delete_document
from app.services.project_sharing import PROJECT_SHARE_START_PREFIX, ensure_project_share_token, list_visible_projects
from app.config import BOT_PLATFORM

router = APIRouter(tags=["main"])

UPLOAD_DIR = "./uploads"
GENERATED_PDF_DIR = os.path.abspath(os.path.join(UPLOAD_DIR, "generated_pdfs"))
GENERATED_PDF_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
GENERATED_PDF_TTL_SECONDS = 24 * 60 * 60
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_PDF_DIR, exist_ok=True)


def _tool_call_payload(tool_call):
    return {
        "id": tool_call.id,
        "tool_name": tool_call.tool.name if getattr(tool_call, "tool", None) else None,
        "status": tool_call.status,
        "arguments": tool_call.arguments,
        "result": tool_call.result,
        "error": tool_call.error,
    }


def _cleanup_expired_generated_pdfs(*, now: datetime | None = None) -> int:
    if not os.path.isdir(GENERATED_PDF_DIR):
        return 0
    current_time = now or datetime.now(timezone.utc)
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


# ---- Projects ----
@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    telegram_user_id: int | None = None,
    root_only: bool = False,
    db: AsyncSession = Depends(get_session)
):
    if telegram_user_id is None:
        from app.services.project_sharing import list_group_public_projects
        projects = await list_group_public_projects(db)
    else:
        user = (
            await db.execute(select(UserPreference).where(UserPreference.telegram_user_id == telegram_user_id))
        ).scalar_one_or_none()
        if not user:
            return []
        from app.services.project_sharing import list_visible_projects
        projects = await list_visible_projects(db, user)

    # root_only filter
    if root_only:
        projects = [p for p in projects if p.shared_from_project_id is None]

    if not projects:
        return []

    project_ids = [p.id for p in projects]

    # Fetch import counts
    import_counts_res = await db.execute(
        select(Project.shared_from_project_id, func.count(Project.id))
        .where(Project.shared_from_project_id.in_(project_ids))
        .group_by(Project.shared_from_project_id)
    )
    import_counts = {row[0]: row[1] for row in import_counts_res.all()}

    # Convert to ProjectOut with import_count
    result = []
    for p in projects:
        p_out = ProjectOut.model_validate(p)
        p_out.import_count = import_counts.get(p.id, 0)
        result.append(p_out)
    
    return result


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_session)):
    project = Project(**data.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, data: ProjectUpdate, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    updates = data.model_dump(exclude_unset=True)
    if "name" in updates and not (updates["name"] or "").strip():
        raise HTTPException(400, "Project name cannot be empty")
    for key, value in updates.items():
        setattr(project, key, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/projects/{project_id}/share", response_model=ProjectShareOut)
async def share_project(
    project_id: int,
    bot_username: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    token = await ensure_project_share_token(db, project)
    telegram_url = None
    if bot_username:
        username = bot_username.strip().lstrip("@")
        if username:
            base = "https://ble.ir" if (BOT_PLATFORM or "").strip().lower() == "bale" else "https://t.me"
            telegram_url = f"{base}/{username}?start={PROJECT_SHARE_START_PREFIX}{token}"
    return ProjectShareOut(project_id=project.id, share_token=token, telegram_url=telegram_url)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    await db.delete(project)
    await db.commit()
    return {"ok": True}


@router.get("/projects/{project_id}/imports", response_model=list[ProjectOut])
async def list_project_imports(project_id: int, db: AsyncSession = Depends(get_session)):
    # Verify source project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Project not found")

    # Fetch imported projects
    result = await db.execute(
        select(Project).where(Project.shared_from_project_id == project_id)
        .order_by(Project.created_at.desc())
    )
    imported_projects = result.scalars().all()
    
    if not imported_projects:
        return []

    project_ids = [p.id for p in imported_projects]

    # Fetch import counts for THESE projects (nested imports)
    import_counts_res = await db.execute(
        select(Project.shared_from_project_id, func.count(Project.id))
        .where(Project.shared_from_project_id.in_(project_ids))
        .group_by(Project.shared_from_project_id)
    )
    import_counts = {row[0]: row[1] for row in import_counts_res.all()}

    # Convert to ProjectOut with import_count
    result_out = []
    for p in imported_projects:
        p_out = ProjectOut.model_validate(p)
        p_out.import_count = import_counts.get(p.id, 0)
        result_out.append(p_out)
    
    return result_out


# ---- Chats ----
async def _resolve_user_id(
    db: AsyncSession,
    user_id: int | None = None,
    telegram_user_id: int | None = None,
) -> int | None:
    if user_id:
        return user_id
    if telegram_user_id:
        result = await db.execute(select(UserPreference.id).where(UserPreference.telegram_user_id == telegram_user_id))
        return result.scalar_one_or_none()
    return None


@router.get("/chats", response_model=list[ChatOut])
async def list_chats(
    project_id: int | None = None,
    user_id: int | None = None,
    telegram_user_id: int | None = None,
    db: AsyncSession = Depends(get_session)
):
    query = select(Chat).options(selectinload(Chat.project))
    
    # Enforce strict user isolation
    resolved_user_id = await _resolve_user_id(db, user_id, telegram_user_id)
    
    if not resolved_user_id:
        # No user identification provided -> return empty list for safety
        return []
        
    # ONLY show chats belonging to this specific user
    # This prevents admins from seeing everyone's history in their own chat UI
    query = query.where(Chat.user_preference_id == resolved_user_id)

    if project_id is None:
        query = query.where(Chat.project_id.is_(None))
    else:
        project_result = await db.execute(select(Project.id).where(Project.id == project_id))
        if project_result.scalar_one_or_none() is None:
            raise HTTPException(404, "Project not found")
        query = query.where(Chat.project_id == project_id)
    
    query = query.order_by(Chat.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/chats", response_model=ChatOut, status_code=201)
async def create_chat(data: ChatCreate, db: AsyncSession = Depends(get_session)):
    if data.project_id is not None:
        project_result = await db.execute(select(Project.id).where(Project.id == data.project_id))
        if project_result.scalar_one_or_none() is None:
            raise HTTPException(404, "Project not found")
            
    # Ensure a chat MUST be associated with a user
    if data.user_preference_id is None:
        raise HTTPException(400, "user_preference_id is required")

    user_result = await db.execute(select(UserPreference.id).where(UserPreference.id == data.user_preference_id))
    if user_result.scalar_one_or_none() is None:
        raise HTTPException(404, "User not found")

    chat = Chat(**data.model_dump())
    db.add(chat)
    await db.commit()
    await db.refresh(chat, attribute_names=["project"])
    return chat


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: int, 
    user_id: int | None = None,
    telegram_user_id: int | None = None,
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(404, "Chat not found")
        
    # Verify ownership
    resolved_user_id = await _resolve_user_id(db, user_id, telegram_user_id)
    if chat.user_preference_id != resolved_user_id:
        raise HTTPException(403, "Access denied")

    await db.delete(chat)
    await db.commit()
    return {"ok": True}


# ---- Messages ----
@router.get("/chats/{chat_id}/messages", response_model=list[MessageOut])
async def list_messages(
    chat_id: int, 
    user_id: int | None = None,
    telegram_user_id: int | None = None,
    db: AsyncSession = Depends(get_session)
):
    # Verify chat ownership
    chat_result = await db.execute(select(Chat.user_preference_id).where(Chat.id == chat_id))
    owner_id = chat_result.scalar_one_or_none()
    if owner_id is None:
        raise HTTPException(404, "Chat not found")
        
    resolved_user_id = await _resolve_user_id(db, user_id, telegram_user_id)
    if owner_id != resolved_user_id:
        raise HTTPException(403, "Access denied")

    result = await db.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    return result.scalars().all()


@router.post("/chats/{chat_id}/messages")
async def send_message(
    chat_id: int,
    data: ChatRequest,
    db: AsyncSession = Depends(get_session),
):
    # Get chat
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat:
        raise HTTPException(404, "Chat not found")

    # Resolve user context for personalization (optional for web clients)
    resolved_user: UserPreference | None = None
    if data.user_id is not None and data.telegram_user_id is not None:
        raise HTTPException(400, "Provide either user_id or telegram_user_id, not both")

    if data.user_id is not None:
        resolved_user = await db.get(UserPreference, data.user_id)
        if not resolved_user:
            raise HTTPException(404, "User not found")
    elif data.telegram_user_id is not None:
        user_result = await db.execute(select(UserPreference).where(UserPreference.telegram_user_id == data.telegram_user_id))
        resolved_user = user_result.scalar_one_or_none()
        if not resolved_user:
            raise HTTPException(404, "User not found")
    elif chat.user_preference_id is not None:
        resolved_user = await db.get(UserPreference, chat.user_preference_id)
        
    # Verify ownership IF user context is provided
    if resolved_user and chat.user_preference_id != resolved_user.id:
        raise HTTPException(403, "Access denied")

    if resolved_user and chat.user_preference_id in {None, resolved_user.id}:
        if chat.user_preference_id is None:
            chat.user_preference_id = resolved_user.id
            await db.commit()
            await db.refresh(chat)
    elif resolved_user and chat.user_preference_id not in {None, resolved_user.id}:
        raise HTTPException(400, "Chat is already linked to a different user")

    # Pro check for projects
    if chat.project_id and resolved_user:
        if not (resolved_user.is_admin or resolved_user.is_pro):
            raise HTTPException(403, "Project features require Pro status. Please upgrade by charging your account.")

    # Determine model
    model_id = data.model_id or chat.model_id
    if model_id:
        provider, model = await get_provider_for_model(db, model_id)
        if not model:
            provider, model = await get_default_model(db)
    else:
        provider, model = await get_default_model(db)

    if not model:
        raise HTTPException(400, "No model configured. Admin must add a provider and model first.")

    # Save user message
    user_msg = Message(chat_id=chat_id, role="user", content=data.content)
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    # Build message history (last 40 messages)
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .limit(20)
    )
    all_messages = list(reversed(result.scalars().all()))
    llm_messages = [{"role": m.role, "content": m.content} for m in all_messages]

    # System prompt from DB + dynamic tool guidance
    system_content = await get_effective_system_prompt(db, chat=chat, user=resolved_user)
    system_content = f"{system_content}\n\nThe user is interacting via the web interface."

    # RAG: if chat has a project, search relevant documents
    context_text = ""
    if chat.project_id:
        emb = await get_emb_config(db)
        api_key = emb.api_key if emb else None
        model_name = emb.model if emb else None
        docs = search_documents(chat.project_id, data.content, n_results=5, api_key=api_key, model=model_name)
        if docs:
            context_parts = [d["content"] for d in docs]
            context_text = "\n\n---\n\n".join(context_parts)
            system_content += f"\n\nRelevant documents context:\n{context_text}"

    llm_messages.insert(0, {"role": "system", "content": system_content})
    llm_messages = await resolve_multimodal_tags_in_messages(db, llm_messages)

    tool_specs = await get_chat_tools(db, chat)

    # Call LLM
    try:
        provider, model, routing = await resolve_model_for_completion(
            db,
            selected_provider=provider,
            selected_model=model,
            messages=llm_messages,
        )
        if not provider or not model:
            raise HTTPException(400, "No executable model configured for this chat.")
        
        usage_logs = []
        if routing and routing.get("router_usage"):
            usage_logs.append(routing["router_usage"])

        executed_tool_calls = []
        initial_reasoning = None
        followup_reasoning = None
        reply = ""
        for iteration in range(20):
            response = await request_chat_completion(
                provider,
                model.name,
                llm_messages,
                tools=[spec["openai"] for spec in tool_specs] or None,
                user_id=resolved_user.id if resolved_user else None,
                chat_id=chat.id,
            )
            if iteration == 0:
                initial_reasoning = extract_reasoning_metadata(response)
            else:
                followup_reasoning = merge_reasoning_metadata(followup_reasoning, extract_reasoning_metadata(response))
            
            response_message = response.get("message") or {}
            usage_logs.append(response.get("usage"))
            tool_calls = response_message.get("tool_calls") or []
            
            if not tool_calls:
                reply = response_message.get("content") or ""
                break
                
            llm_messages.append(
                {
                    "role": "assistant",
                    "content": response_message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )

            for tool_call_data in tool_calls[:5]:
                function = tool_call_data.get("function") or {}
                tool_name = function.get("name")
                if not tool_name:
                    continue
                matching_spec = next((spec for spec in tool_specs if spec["tool"].name == tool_name), None)
                if not matching_spec:
                    continue
                raw_arguments = function.get("arguments") or "{}"
                try:
                    parsed_arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    parsed_arguments = {"raw": raw_arguments}
                tool_record, result = await execute_tool_call(
                    db,
                    tool=matching_spec["tool"],
                    binding_id=matching_spec["binding_id"],
                    chat_id=chat.id,
                    message_id=user_msg.id,
                    provider_name=provider.name,
                    model_name=model.name,
                    external_call_id=tool_call_data.get("id"),
                    arguments=parsed_arguments,
                )
                await db.refresh(tool_record, attribute_names=["tool"])
                executed_tool_calls.append(tool_record)
                
                # Strip large markdown from LLM context to save tokens, but keep it in tool_record for UI
                llm_result = dict(result)
                if tool_name == "image_generator":
                    llm_result.pop("markdown", None)
                    llm_result.pop("saved_image_paths", None)
                    llm_result["message"] = "Image generated and displayed to user in UI."
                elif tool_name == "pdf_generator":
                    llm_result.pop("pdf_base64", None)
                    
                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_data.get("id"),
                        "content": json.dumps(llm_result, ensure_ascii=False),
                    }
                )
        else:
            reply = "⚠️ پردازش به دلیل طولانی شدن بیش از حد متوقف شد. لطفاً بخشی از درخواست خود را تغییر دهید."
            
        reasoning = merge_reasoning_metadata(initial_reasoning, followup_reasoning)
    except LLMProviderError as e:
        if e.code == "unsupported_image_input":
            suggested_models = await suggest_models_for_input_capability(
                db,
                need_image_input=True,
                exclude_model_id=model.id,
            )
            raise HTTPException(
                422,
                {
                    "error_code": "unsupported_image_input",
                    "message": f"Selected model '{model.display_name or model.name}' does not support image input.",
                    "selected_model": {
                        "id": model.id,
                        "name": model.name,
                        "display_name": model.display_name,
                    },
                    "suggested_models": suggested_models,
                    "provider_error": e.provider_message or str(e),
                    "action_hint": "Switch to a vision-capable model from the suggestions.",
                },
            )
        raise HTTPException(502, f"LLM error: {str(e)}")
    except Exception as e:
        raise HTTPException(502, f"LLM error: {str(e)}")

    # Save assistant message
    assistant_msg = Message(chat_id=chat_id, role="assistant", content=reply)
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    # Generate title if still untitled
    if chat.title in {"New Chat", "💬 چت جدید"}:
        title = await generate_title(db, model.id, llm_messages)
        chat.title = title
        await db.commit()

    # Extract delivered files from tool calls (send_file, pdf_generator, chart_generator)
    delivered_files = []
    for tc in executed_tool_calls:
        if tc.result and tc.result.get("ok"):
            tool_name = tc.tool.name if hasattr(tc, "tool") else ""
            if tool_name == "send_file" and tc.result.get("storage_path"):
                delivered_files.append({
                    "file_path": tc.result["storage_path"],
                    "file_name": os.path.basename(tc.result["storage_path"]),
                    "tool": "send_file",
                })
            elif tool_name == "pdf_generator" and tc.result.get("saved_path"):
                delivered_files.append({
                    "file_path": tc.result["saved_path"],
                    "file_name": tc.result.get("filename", "output.pdf"),
                    "tool": "pdf_generator",
                })
            elif tool_name == "chart_generator" and tc.result.get("file_path"):
                delivered_files.append({
                    "file_path": tc.result["file_path"],
                    "file_name": os.path.basename(tc.result["file_path"]),
                    "tool": "chart_generator",
                })

    return {
        "message": {
            "id": assistant_msg.id,
            "chat_id": chat_id,
            "role": "assistant",
            "content": reply,
            "reasoning_summary": (reasoning or {}).get("summary"),
            "reasoning_stages": (reasoning or {}).get("stages") or [],
        },
        "title": chat.title,
        "context_used": bool(context_text),
        "tool_calls": [_tool_call_payload(tool_call) for tool_call in executed_tool_calls],
        "delivered_files": delivered_files,
        "reasoning": reasoning,
        "routing": routing,
    }


@router.get("/generated-pdfs/{filename}")
async def download_generated_pdf(filename: str):
    _cleanup_expired_generated_pdfs()
    normalized_name = (filename or "").strip()
    if (
        not normalized_name
        or not normalized_name.lower().endswith(".pdf")
        or "/" in normalized_name
        or "\\" in normalized_name
        or not GENERATED_PDF_FILENAME_RE.match(normalized_name)
    ):
        raise HTTPException(400, "Invalid PDF filename")

    file_path = os.path.abspath(os.path.join(GENERATED_PDF_DIR, normalized_name))
    if not file_path.startswith(f"{GENERATED_PDF_DIR}{os.sep}"):
        raise HTTPException(400, "Invalid PDF filename")
    if not os.path.isfile(file_path):
        raise HTTPException(404, "Generated PDF not found")
    return FileResponse(file_path, media_type="application/pdf", filename=normalized_name)


@router.get("/files/deliver/{filename:path}")
async def deliver_file(filename: str):
    normalized = (filename or "").strip()
    if not normalized or ".." in normalized:
        raise HTTPException(400, "Invalid filename")

    UPLOAD_DIR = os.path.abspath("./uploads")
    file_path = os.path.abspath(os.path.join(UPLOAD_DIR, normalized))
    if not file_path.startswith(f"{UPLOAD_DIR}{os.sep}"):
        raise HTTPException(400, "Invalid file path")
    if not os.path.isfile(file_path):
        raise HTTPException(404, "File not found")

    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".html": "text/html",
        ".json": "application/json",
        ".py": "text/x-python",
        ".js": "application/javascript",
        ".ts": "text/typescript",
    }
    ext = os.path.splitext(file_path)[1].lower()
    media_type = mime_map.get(ext, "application/octet-stream")
    return FileResponse(file_path, media_type=media_type, filename=os.path.basename(file_path))


# ---- Document Upload ----
@router.post("/projects/{project_id}/documents/upload")
async def upload_project_file(
    project_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    SUPPORTED_KB_EXTS = {".pdf", ".txt", ".md", ".csv", ".docx", ".xlsx", ".pptx", ".html", ".jpg", ".jpeg", ".png", ".webp"}
    if ext not in SUPPORTED_KB_EXTS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    # Save file
    project_dir = os.path.join(UPLOAD_DIR, f"project_{project_id}")
    os.makedirs(project_dir, exist_ok=True)
    file_path = os.path.join(project_dir, file.filename)
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Create document record
    doc = Document(
        project_id=project_id,
        filename=file.filename,
        file_type=ext.lstrip("."),
        file_path=file_path,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    from app.services.rag_service import background_index_document
    # Index into ChromaDB in background
    try:
        emb = await get_emb_config(db)
        api_key = emb.api_key if emb else None
        model_name = emb.model if emb else None
        provider = emb.provider if emb else "google"
        base_url = emb.base_url if emb else None
        
        background_tasks.add_task(
            background_index_document,
            project_id,
            doc.id,
            file_path,
            api_key=api_key,
            model=model_name,
            provider=provider,
            base_url=base_url
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error starting background indexing: {e}")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "chunk_count": 0,
        "status": "processing",
    }


@router.get("/projects/{project_id}/documents")
async def list_documents(project_id: int, db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(Document).where(Document.project_id == project_id)
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_type": d.file_type,
            "chunk_count": d.chunk_count,
            "status": d.status,
            "error": d.error,
            "created_at": d.created_at,
        }
        for d in docs
    ]


@router.delete("/projects/{project_id}/documents/{document_id}")
async def delete_document_endpoint(
    project_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_session),
):
    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    # Find document
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.project_id == project_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Delete from filesystem if exists
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass

    # Delete from ChromaDB
    try:
        emb = await get_emb_config(db)
        api_key = emb.api_key if emb else None
        model_name = emb.model if emb else None
        provider = emb.provider if emb else "google"
        base_url = emb.base_url if emb else None
        delete_document(project_id, document_id, api_key=api_key, model=model_name, provider=provider, base_url=base_url)
    except Exception:
        pass

    # Delete from DB
    await db.delete(doc)
    await db.commit()

    return {"ok": True}


# ---- Base64 Document Upload (for Telegram bot) ----
class Base64Upload(BaseModel):
    filename: str
    content: str  # base64 encoded
    file_type: str  # pdf, txt, md

@router.post("/projects/{project_id}/documents/upload-base64")
async def upload_document_base64(
    project_id: int,
    data: Base64Upload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    if data.file_type not in ("pdf", "txt", "md"):
        raise HTTPException(400, f"Unsupported file type: {data.file_type}")

    # Decode and save file
    project_dir = os.path.join(UPLOAD_DIR, f"project_{project_id}")
    os.makedirs(project_dir, exist_ok=True)
    file_path = os.path.join(project_dir, data.filename)
    with open(file_path, "wb") as f:
        f.write(base64.b64decode(data.content))

    # Create document record
    doc = Document(
        project_id=project_id,
        filename=data.filename,
        file_type=data.file_type,
        file_path=file_path,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    from app.services.rag_service import background_index_document
    # Index into ChromaDB in background
    try:
        emb = await get_emb_config(db)
        api_key = emb.api_key if emb else None
        model_name = emb.model if emb else None
        provider = emb.provider if emb else "google"
        base_url = emb.base_url if emb else None
        
        background_tasks.add_task(
            background_index_document,
            project_id,
            doc.id,
            file_path,
            api_key=api_key,
            model=model_name,
            provider=provider,
            base_url=base_url
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error starting background indexing: {e}")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "chunk_count": 0,
        "status": "processing",
    }
