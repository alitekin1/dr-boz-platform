import json
import asyncio
import os
import re
from html import escape
from typing import AsyncGenerator, Any, Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, create_model, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.database import get_session, async_session
from app.llm import get_default_model, get_provider_for_model, get_chat_tools, execute_tool_call, request_chat_completion, _extract_codex_tool_requests, resolve_multimodal_tags_in_messages
from app.agent.agent import get_agent_executor
from app.models import Chat, Message as DBMessage, Tool
from app.services.codex_runtime import is_codex_subscription_provider
from app.agent.tools import tools_list as static_tools, SearchProjectInput
from langchain_core.tools import StructuredTool
from langchain_core.messages import ToolMessage, HumanMessage

router = APIRouter(tags=["agent"])

class AgentChatRequest(BaseModel):
    message: str
    thread_id: str = "default_thread"
    model_id: int | None = None
    chat_id: int | None = None
    message_id: int | None = None
    system_prompt: Optional[str] = None

class RobustEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, "content"):
            return o.content
        if hasattr(o, "dict"):
            try: return o.dict()
            except: pass
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)

def safe_json_dumps(obj):
    return json.dumps(obj, cls=RobustEncoder, ensure_ascii=False)

def create_pydantic_model_from_schema(name: str, schema: dict):
    if not isinstance(schema, dict):
        return create_model(name, kwargs=(dict, Field(default_factory=dict)))
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    fields = {}
    for key, prop in properties.items():
        t = str
        ptype = prop.get("type", "string")
        if ptype == "integer": t = int
        elif ptype == "number": t = float
        elif ptype == "boolean": t = bool
        
        description = prop.get("description", "")
        if key in required:
            fields[key] = (t, Field(..., description=description))
        else:
            fields[key] = (t, Field(default=None, description=description))
    if not fields:
        return create_model(name, kwargs=(dict, Field(default_factory=dict)))
    return create_model(name, **fields)

def create_dynamic_tool(tool_spec: dict, chat_id: int | None, message_id: int | None, provider_name: str, model_name: str):
    tool_obj = tool_spec["tool"]
    binding_id = tool_spec["binding_id"]
    
    schema = tool_obj.input_schema if isinstance(tool_obj.input_schema, dict) else {}
    model_name_cls = "".join(x.capitalize() for x in tool_obj.name.split("_")) + "Input"
    DynamicSchema = create_pydantic_model_from_schema(model_name_cls, schema)
    
    async def tool_func(**kwargs):
        async with async_session() as db:
            try:
                _, result = await execute_tool_call(
                    db,
                    tool=tool_obj,
                    binding_id=binding_id,
                    chat_id=chat_id,
                    message_id=message_id,
                    provider_name=provider_name,
                    model_name=model_name,
                    external_call_id=None,
                    arguments=kwargs
                )
                return json.dumps(result, cls=RobustEncoder, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"error": str(e), "status": "failed"})

    return StructuredTool.from_function(
        coroutine=tool_func,
        name=tool_obj.name,
        description=tool_obj.description or f"Execute {tool_obj.name}",
        args_schema=DynamicSchema,
    )


async def _build_codex_tool_guidance(tool_specs: list[dict]) -> str:
    if not tool_specs:
        return (
            "Available custom server tools for this chat: none.\n"
            "Do not claim that server-side PDF, image, file, or web tools are available unless listed here."
        )

    def _sanitize(text: str | None, fallback: str, limit: int = 160) -> str:
        t = (text or "").strip()
        if not t:
            t = fallback
        t = t.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        t = re.sub(r"\s+", " ", t).strip()
        return t[:limit]

    def _xml_example(tool_obj) -> str:
        schema = tool_obj.input_schema if isinstance(tool_obj.input_schema, dict) else {}
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        keys = list(props.keys())[:3]
        if not keys:
            return f"<{tool_obj.name} />"
        if len(keys) == 1:
            return f'<{tool_obj.name} {keys[0]}="..." />'
        children = "".join(f"<{k}>...</{k}>" for k in keys)
        return f"<{tool_obj.name}>{children}</{tool_obj.name}>"

    lines = [
        "Available custom server tools for this chat:",
        "When a listed tool is required, output only its XML request tag. The server will execute it and ask you for the final answer with TOOL_RESULT.",
    ]
    for spec in tool_specs[:12]:
        tool = spec["tool"]
        name = _sanitize(tool.name, fallback="tool", limit=64)
        description = _sanitize(tool.description, fallback="No description provided.", limit=220)
        usage = _xml_example(tool)
        lines.append(f"- {name}: {description} Usage: {usage}")
    if any(spec["tool"].name == "pdf_generator" for spec in tool_specs):
        lines.append("PDF generation is available in this chat through pdf_generator. If the user asks for a PDF, use it instead of saying PDF creation is unavailable.")
    if any(spec["tool"].name in ("search_project", "search_project_queries") for spec in tool_specs):
        lines.append(
            "\nIMPORTANT: When answering questions about project documents, ALWAYS use search_project or search_project_queries FIRST. "
            "Do NOT rely on memory or general knowledge for facts contained in the uploaded files. "
            "Use search_project_queries with 3-5 different query variations to get comprehensive coverage of the topic. "
            "Base your answer ONLY on the search results returned."
        )
    return "\n".join(lines)


async def stream_codex_direct_completion(
    message: str,
    provider,
    model,
    system_prompt: str,
    max_retries: int = 3,
    user_id: int | None = None,
    chat_id: int | None = None,
) -> AsyncGenerator[dict, None]:
    attempt = 0

    async with async_session() as db:
        chat = None
        if chat_id is not None:
            chat = await db.get(Chat, chat_id)

        history_messages: list[dict] = []
        if chat:
            result = await db.execute(
                select(DBMessage)
                .where(DBMessage.chat_id == chat.id)
                .order_by(DBMessage.created_at.desc(), DBMessage.id.desc())
                .limit(20)
            )
            stored = list(reversed(result.scalars().all()))
            history_messages = [
                {"role": m.role, "content": m.content}
                for m in stored
                if m.role in {"user", "assistant"} and m.content
            ]

        tool_specs = await get_chat_tools(db, chat) if chat else []

        project_files_text = ""
        if chat and chat.project_id:
            from app.models import Document
            doc_result = await db.execute(
                select(Document).where(Document.project_id == chat.project_id)
            )
            docs = doc_result.scalars().all()
            if docs:
                file_lines = []
                for d in docs:
                    actual_status = d.status or "pending"
                    if (d.chunk_count or 0) > 0 and actual_status in ("pending", "processing"):
                        actual_status = "indexed"
                    file_lines.append(f"- {d.filename} ({actual_status}, {d.chunk_count or 0} chunks)")
                project_files_text = (
                    "\n\nPROJECT FILES:\n"
                    "The following files are uploaded to the current project. "
                    "When the user asks what files you have access to, refer to this list. "
                    "Do NOT list files from your local workspace directory.\n"
                    + "\n".join(file_lines)
                )

        messages: list[dict] = []
        if project_files_text:
            system_prompt = system_prompt + project_files_text

        codex_tool_protocol = (
            "\n\n### Custom Server Tools Protocol:\n"
            "The server may provide extra custom tools that are not in your native tool list.\n"
            "To use these custom tools, you MUST output an XML tag exactly as shown in the available tool usage examples. "
            "The server will intercept this tag, execute the tool, and return the TOOL_RESULT to you.\n"
            "CRITICAL: Continue using your standard tool call format for your native operations. "
            "Do NOT use self-closing tags for native operations, and do NOT use native tool calls for the custom server tools.\n\n"
            "Anti-hallucination rules for custom server tools:\n"
            "- If a custom server tool is NOT in your available tools list below, you MUST NOT pretend to use it or simulate its output.\n"
            "- NEVER output raw tool call markup (XML tags, JSON blocks, or tool call syntax) in your visible response to the user. "
            "These are internal protocol elements and must never appear in user-facing text.\n"
            "- If you need to create a file (Excel, PDF, Word, etc.) but the tool is not available, say so honestly. "
            "Offer to prepare the content as text that the user can later convert themselves.\n"
            "- If a tool execution fails, report the failure honestly. Do not claim success when the tool returned an error.\n"
            "- Never show internal server paths (like /home/user or /tmp) as download links to the user. "
            "Only share download links or file_ids that the server tool result explicitly provides."
        )
        codex_tool_guidance = await _build_codex_tool_guidance(tool_specs)
        enhanced_system_prompt = f"{system_prompt}{codex_tool_protocol}\n\n{codex_tool_guidance}"

        if enhanced_system_prompt:
            messages.append({"role": "system", "content": enhanced_system_prompt})
        messages.extend(history_messages)

        if isinstance(message, list):
            resolved_current = {"role": "user", "content": message}
        else:
            resolved_current = {"role": "user", "content": message}

        if history_messages and history_messages[-1].get("role") == "user":
            messages[-1] = resolved_current
        else:
            messages.append(resolved_current)

        messages = await resolve_multimodal_tags_in_messages(db, messages)

    max_tool_iterations = 10
    tool_iteration = 0

    while attempt <= max_retries:
        try:
            response = await request_chat_completion(
                provider,
                model.name,
                messages,
                stream=False,
                tools=None,
                user_id=user_id,
                chat_id=chat_id,
            )
            assistant_message = response.get("message") or {}
            content_val = assistant_message.get("content", "")
            if isinstance(content_val, list):
                text_parts = [
                    item.get("text", "")
                    for item in content_val
                    if isinstance(item, dict) and item.get("type") == "text"
                ]
                content_val = "".join(text_parts)

            if content_val:
                messages.append({"role": "assistant", "content": content_val})

            tool_requests = _extract_codex_tool_requests(content_val) if content_val else []
            if tool_requests and tool_specs and tool_iteration < max_tool_iterations:
                tool_iteration += 1
                tool_request = tool_requests[0]
                tool_name = tool_request.get("name")
                args = tool_request.get("arguments") or {}

                matching_spec = next((spec for spec in tool_specs if spec["tool"].name == tool_name), None)
                if matching_spec:
                    yield {"data": safe_json_dumps({"type": "tool_start", "tool": tool_name})}
                    try:
                        async with async_session() as tool_db:
                            tool_record, tool_result = await execute_tool_call(
                                tool_db,
                                tool=matching_spec["tool"],
                                binding_id=matching_spec["binding_id"],
                                chat_id=chat_id,
                                message_id=None,
                                provider_name=provider.name,
                                model_name=model.name,
                                external_call_id=f"codex-agent-{re.sub(r'[^A-Za-z0-9]', '', content_val[:8])}",
                                arguments=args,
                            )
                    except Exception as tool_exc:
                        tool_result = {"ok": False, "error": str(tool_exc)[:500]}
                        logger = __import__("logging").getLogger(__name__)
                        logger.warning(f"Codex tool '{tool_name}' execution failed: {tool_exc}")
                    yield {"data": safe_json_dumps({"type": "tool_end", "tool": tool_name, "output": json.dumps(tool_result, ensure_ascii=False)})}
                    result_text = json.dumps(tool_result, ensure_ascii=False)
                    messages.append({"role": "user", "content": f"TOOL_RESULT ({tool_name}):\n{result_text}\n\nNow produce your final answer based on this result."})
                    continue

                yield {"data": safe_json_dumps({"type": "content", "content": content_val})}
                usage = response.get("usage")
                if usage:
                    yield {"data": safe_json_dumps({"type": "usage", "usage": usage})}

            yield {"data": safe_json_dumps({"type": "done"})}
            return

            if content_val:
                yield {"data": safe_json_dumps({"type": "content", "content": content_val})}

            usage = response.get("usage")
            if usage:
                yield {"data": safe_json_dumps({"type": "usage", "usage": usage})}

            yield {"data": safe_json_dumps({"type": "done"})}
            return
        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                yield {"data": safe_json_dumps({"type": "error", "error": f"Agent error after {max_retries} retries: {str(e)}", "retry_count": attempt})}
            else:
                print(f"Codex direct completion retry {attempt} due to: {e}")
                await asyncio.sleep(0.5)

async def event_generator(
    message: str, 
    thread_id: str, 
    provider, 
    model, 
    chat_id: int | None = None,
    message_id: int | None = None,
    system_prompt: Optional[str] = None,
    user_id: int | None = None,
    project_id: int | None = None,
) -> AsyncGenerator[dict, None]:
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    
    custom_tools = []
    resolved_user_id = user_id
    chat = None
    if chat_id:
        async with async_session() as db:
            result = await db.execute(select(Chat).where(Chat.id == chat_id))
            chat = result.scalar_one_or_none()
            if chat:
                resolved_user_id = resolved_user_id or chat.user_preference_id
                # Use project_id from caller, fallback to chat.project_id
                effective_project_id = project_id or chat.project_id
                # Add project search tool if in a project
                if effective_project_id:
                    from app.rag import search_documents
                    from app.llm import get_emb_config
                    from app.models import Document

                    emb = await get_emb_config(db)
                    api_key = emb.api_key if emb else None
                    model_name = emb.model if emb else None
                    provider_emb = emb.provider if emb else "google"
                    base_url = emb.base_url if emb else None

                    async def project_search_func(query: str, n_results: int = 5):
                        try:
                            results = await asyncio.to_thread(
                                search_documents,
                                effective_project_id,
                                query,
                                n_results=n_results,
                                api_key=api_key,
                                model=model_name,
                                provider=provider_emb,
                                base_url=base_url
                            )
                            return json.dumps(results, ensure_ascii=False)
                        except Exception as e:
                            return json.dumps({"error": str(e)})

                    async def list_project_files_func():
                        try:
                            async with async_session() as db_inner:
                                result = await db_inner.execute(
                                    select(Document).where(Document.project_id == effective_project_id)
                                )
                                docs = result.scalars().all()
                                files = []
                                for d in docs:
                                    actual_status = d.status or "pending"
                                    if (d.chunk_count or 0) > 0 and actual_status in ("pending", "processing"):
                                        actual_status = "indexed"
                                    files.append({
                                        "id": d.id,
                                        "filename": d.filename,
                                        "status": actual_status,
                                        "chunk_count": d.chunk_count or 0,
                                        "created_at": str(d.created_at)
                                    })
                                return json.dumps(files, ensure_ascii=False)
                        except Exception as e:
                            return json.dumps({"error": str(e)})

                    custom_tools.append(StructuredTool.from_function(
                        coroutine=project_search_func,
                        name="search_project_context",
                        description="Search for relevant information, context, and data within the current project's documents and knowledge base. Use this whenever you need to answer questions based on the content of uploaded files.",
                        args_schema=SearchProjectInput,
                    ))

                    custom_tools.append(StructuredTool.from_function(
                        coroutine=list_project_files_func,
                        name="list_project_files",
                        description="List all files currently uploaded to this project. Use this to see what documents are available or to answer questions about what files you have access to.",
                    ))
                tool_specs = await get_chat_tools(db, chat)
                for spec in tool_specs:
                    try:
                        custom_tools.append(create_dynamic_tool(spec, chat_id, message_id, provider.name, model.name))
                    except Exception as e:
                        print(f"Error creating dynamic tool {spec['tool'].name}: {e}")

    max_retries = 3
    attempt = 0
    
    # Base instructions
    disabled_builtin_tool_names: set[str] = set()
    async with async_session() as db:
        disabled_result = await db.execute(select(Tool.name).where(Tool.is_builtin == True, Tool.is_active == False))
        disabled_builtin_tool_names = set(disabled_result.scalars().all())

    is_codex = is_codex_subscription_provider(provider)

    if is_codex:
        base_instructions = (
            "You are an expert AI agent.\n"
            "Respond to the user's request accurately and helpfully.\n"
            "Use your internal knowledge and capabilities to provide the best possible answer.\n"
            "Do not output tool-call JSON, XML, or fenced code blocks as a substitute for an answer.\n"
        )
    else:
        base_instructions = (
            "You are an expert AI agent with advanced reasoning and tool-use capabilities.\n"
            "STRICT GUIDELINES:\n"
            "1. Tool Retry Limit: If a tool fails, you may retry ONCE with corrected parameters. If it fails again, report the error to the user and stop. Do NOT retry indefinitely.\n"
            "2. Deliverables: When asked for reports or comparisons, produce a comprehensive text analysis first, then use only currently enabled tools when a tool materially improves the deliverable.\n"
            "3. Disabled Tools: If a tool is disabled or not present in the current tool list, DO NOT mention it as an available capability and DO NOT attempt to use it.\n"
            "4. Visuals: ALWAYS use the 'run_python' tool for plotting data charts and graphs. NEVER use image generation tools for data charts. Save plots as PNG with clear filenames. Keep run_python send_to_chat=false for charts that will be embedded into a PDF; final PDF files created by run_python will still be delivered. Set send_to_chat=true only when the user explicitly wants chart/image files sent directly in chat.\n"
            "5. Formatting: Format your final response clearly using Markdown, with appropriate line breaks, bullet points, and spacing. NEVER output a giant wall of text. NEVER use Markdown tables unless specifically requested by the user; use lists or bold text instead for better display on mobile apps like Telegram. \n"
            "6. No Narrating: DO NOT 'think out loud' or narrate your internal steps (e.g., 'Let me fix that', 'I will search for...'). Provide only the final answer or result to the user. Do NOT explain what tools you are using.\n"
            "7. Autonomy: Chain tool calls together and deliver the final result without asking for intermediate permissions.\n"
            "8. Tool Calling: To use a tool, you MUST use the native tool calling feature. DO NOT simply output a JSON block in your message text; instead, trigger the tool call properly.\n"
            "9. Reporting Capabilities: If the user asks about your skills, abilities, or what you can do, ONLY list the tools and the exact skills listed under the 'AVAILABLE SKILLS' section below. DO NOT invent or hallucinate other capabilities.\n"
            "10. Max Tool Calls: You have a maximum of 15 tool calls per conversation turn. If you reach this limit, stop using tools and provide your best answer with the information you have.\n"
        )
    
    full_system_prompt = base_instructions
    
    if system_prompt:
        full_system_prompt += f"\nADDITIONAL CONTEXT:\n{system_prompt}"
    if disabled_builtin_tool_names and not is_codex:
        disabled_list = "\n".join(f"- {name}" for name in sorted(disabled_builtin_tool_names))
        full_system_prompt += (
            "\n\nDISABLED TOOLS:\n"
            "The following tools are disabled. Do not list them as available capabilities, advertise them to the user, or call them.\n"
            f"{disabled_list}\n"
            "If older context mentions one of these tools, the disabled state wins."
        )

    # Skills are already resolved in the system_prompt via @skills placeholder
    # in PromptService._get_skills_text(). Do not inject them again here.

    if is_codex_subscription_provider(provider):
        async for event in stream_codex_direct_completion(
            message,
            provider,
            model,
            full_system_prompt,
            max_retries=max_retries,
            user_id=resolved_user_id,
            chat_id=chat_id,
        ):
            yield event
        return

    while attempt <= max_retries:
        try:
            agent_executor = get_agent_executor(
                model_name=model.name,
                api_key=provider.api_key,
                base_url=provider.base_url,
                custom_tools=custom_tools,
                disabled_tool_names=disabled_builtin_tool_names,
                system_prompt=full_system_prompt,
            )
            
            # State Repair: Detect and fix poisoned state (AIMessage with tool_calls but no ToolMessage)
            # This happens if a previous attempt was interrupted after tool calls but before results.
            try:
                state = await agent_executor.aget_state(config)
                if state.values and "messages" in state.values and state.values["messages"]:
                    last_msg = state.values["messages"][-1]
                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        repair_messages = [
                            ToolMessage(
                                tool_call_id=tc["id"],
                                content=f"Error: Previous attempt was interrupted. Please retry the tool call if needed.",
                            )
                            for tc in last_msg.tool_calls
                        ]
                        await agent_executor.aupdate_state(config, {"messages": repair_messages})
                elif chat_id:
                    # Thread is empty in memory, but we might have history in DB (e.g. file uploads)
                    async with async_session() as db_hist:
                        hist_result = await db_hist.execute(
                            select(DBMessage)
                            .where(DBMessage.chat_id == chat_id)
                            .order_by(DBMessage.created_at.desc(), DBMessage.id.desc())
                            .limit(20)
                        )
                        stored = list(reversed(hist_result.scalars().all()))
                        if stored:
                            from langchain_core.messages import AIMessage
                            history_msgs = []
                            history_msg_ids = []  # Track DB ids corresponding to each history_msg
                            for m in stored:
                                if m.role == "user":
                                    # Resolve tags in history too!
                                    h_resolved = await resolve_multimodal_tags_in_messages(db_hist, [{"role": "user", "content": m.content}])
                                    history_msgs.append(HumanMessage(content=h_resolved[0]["content"]))
                                    history_msg_ids.append(m.id)
                                elif m.role == "assistant":
                                    history_msgs.append(AIMessage(content=m.content))
                                    history_msg_ids.append(m.id)
                            
                            if history_msgs:
                                # Filter out the current message to avoid duplication
                                if message_id:
                                    history_msgs = [hm for i, hm in enumerate(history_msgs) if history_msg_ids[i] != message_id]
                                
                                if history_msgs:
                                    await agent_executor.aupdate_state(config, {"messages": history_msgs})

            except Exception as e:
                print(f"Non-critical error repairing state or loading history: {e}")
            
            # Build input messages
            temp_msgs = [{"role": "user", "content": message}]
            async with async_session() as db_res:
                resolved_temp = await resolve_multimodal_tags_in_messages(db_res, temp_msgs)
            final_content = resolved_temp[0]["content"]
            
            input_messages = [HumanMessage(content=final_content)]
            
            async for event in agent_executor.astream_events(
                {"messages": input_messages}, 
                config, 
                version="v2"
            ):
                kind = event["event"]
                data = event.get("data", {})
                
                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        content_val = chunk.content
                        if isinstance(content_val, list):
                            text_parts = [b.get("text", "") for b in content_val if isinstance(b, dict) and b.get("type") == "text"]
                            content_val = "".join(text_parts)
                        if content_val:
                            yield {"data": safe_json_dumps({"type": "content", "content": content_val})}
                
                elif kind == "on_chat_model_end":
                    output = data.get("output")
                    usage = None
                    if output:
                        if hasattr(output, "usage_metadata"):
                            usage = output.usage_metadata
                        elif isinstance(output, dict):
                            usage = output.get("usage_metadata")
                    
                    if usage:
                        yield {"data": safe_json_dumps({"type": "usage", "usage": usage})}
                    
                elif kind == "on_tool_start":
                    yield {"data": safe_json_dumps({"type": "tool_start", "tool": event.get("name", "tool")})}
                    
                elif kind == "on_tool_end":
                    output = data.get("output")
                    yield {"data": safe_json_dumps({"type": "tool_end", "tool": event.get("name", "tool"), "output": output})}
                    
                elif kind == "on_tool_error":
                    error = data.get("error")
                    error_msg = str(error) if error else "Unknown tool error"
                    print(f"[TOOL ERROR] {event.get('name')}: {error_msg}")
                    yield {"data": safe_json_dumps({"type": "tool_end", "tool": event.get("name", "tool"), "output": f"Error: {error_msg}"})}
                    
                elif kind == "on_chain_error":
                    error = data.get("error")
                    error_msg = str(error) if error else "Unknown chain error"
                    print(f"[CHAIN ERROR] {error_msg}")
                    yield {"data": safe_json_dumps({"type": "error", "error": error_msg})}
            
            try:
                final_state = await agent_executor.aget_state(config)
                final_messages = final_state.values.get("messages", [])
                for msg in reversed(final_messages):
                    um = getattr(msg, "usage_metadata", None)
                    if um:
                        yield {"data": safe_json_dumps({"type": "usage", "usage": um})}
                        break
            except Exception:
                pass

            yield {"data": safe_json_dumps({"type": "done"})}
            return
            
        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                yield {"data": safe_json_dumps({"type": "error", "error": f"Agent error after {max_retries} retries: {str(e)}", "retry_count": attempt})}
            else:
                print(f"Agent retry {attempt} due to: {e}")
                await asyncio.sleep(0.5)

@router.post("/agent/chat")
async def agent_chat(request: AgentChatRequest, db: AsyncSession = Depends(get_session)):
    if request.model_id:
        provider, model = await get_provider_for_model(db, request.model_id)
        if not provider or not model:
            provider, model = await get_default_model(db)
    else:
        provider, model = await get_default_model(db)
        
    if not provider or not model:
        raise HTTPException(status_code=400, detail="No model configured.")
        
    return EventSourceResponse(event_generator(
        request.message, 
        request.thread_id, 
        provider, 
        model,
        chat_id=request.chat_id,
        message_id=request.message_id,
        system_prompt=request.system_prompt
    ))
