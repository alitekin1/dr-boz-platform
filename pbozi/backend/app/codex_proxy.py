import asyncio
import base64
import json
import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.database import async_session
from app.models import Chat, Provider, UserPreference
from app.services.codex_runtime import (
    build_codex_exec_argv,
    build_codex_process_env,
    build_codex_workspace,
    ensure_codex_home,
    is_codex_subscription_provider,
)
from app.services.codex_capacity_service import (
    CodexCapacityError,
    record_codex_account_usage,
)
from app.llm import select_codex_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/codex-proxy/v1", tags=["codex-proxy"])

CODEX_EXEC_TIMEOUT_SECONDS = int(os.getenv("CODEX_EXEC_TIMEOUT_SECONDS", "120"))


class MessageContent(BaseModel):
    type: str
    text: str | None = None
    image_url: dict | None = None


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict] | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    user: str | None = None


def _extract_images_from_messages(messages: list[dict]) -> list[str]:
    """Extract base64 images from messages and save as temp files."""
    image_paths: list[str] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "image_url":
                continue
            image_url = item.get("image_url", {})
            if isinstance(image_url, dict):
                url = image_url.get("url", "")
            elif isinstance(image_url, str):
                url = image_url
            else:
                continue

            if not url:
                continue

            if url.startswith("data:"):
                header, _, b64_data = url.partition(",")
                if not b64_data:
                    continue

                mime_match = re.match(r"data:(image/\w+)", header)
                if mime_match:
                    mime_type = mime_match.group(1)
                    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
                    ext = ext_map.get(mime_type, ".jpg")
                else:
                    ext = ".jpg"

                try:
                    image_bytes = base64.b64decode(b64_data)
                    fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="codex_proxy_img_")
                    try:
                        os.write(fd, image_bytes)
                    finally:
                        os.close(fd)
                    image_paths.append(tmp_path)
                except Exception:
                    continue

    return image_paths


def _messages_to_codex_prompt(messages: list[dict]) -> str:
    """Convert OpenAI messages to Codex CLI text prompt."""
    parts: list[str] = []
    image_index = 0
    for message in messages:
        role = str(message.get("role") or "user")
        if role == "system":
            continue
        content = message.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text_parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text_parts.append(str(item.get("text") or ""))
                elif item.get("type") == "image_url":
                    image_index += 1
                    text_parts.append(f"[Image {image_index}]")
            text = "\n".join(part for part in text_parts if part)
        else:
            text = json.dumps(content, ensure_ascii=False)
        if text.strip():
            parts.append(f"{role}:\n{text.strip()}")
    return "\n\n".join(parts).strip()


def _extract_last_message_from_jsonl(stdout: str) -> str:
    last_message = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or event.get("msg") or {}
        if isinstance(message, dict):
            content = message.get("content") or message.get("text")
            if isinstance(content, str) and content.strip():
                last_message = content.strip()
        if event.get("type") in {"agent_message", "message"}:
            content = event.get("content") or event.get("text")
            if isinstance(content, str) and content.strip():
                last_message = content.strip()
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict):
            if item.get("type") in {"agent_message", "message"}:
                content = item.get("content") or item.get("text")
                if isinstance(content, str) and content.strip():
                    last_message = content.strip()
    return last_message


def _extract_thread_id_from_jsonl(stdout: str) -> str | None:
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "thread.started":
            return event.get("thread_id")
    return None


def _extract_usage_from_jsonl(stdout: str) -> dict[str, int]:
    import asyncio

    def _coerce_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    usage: dict[str, int] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        event_usage = event.get("usage")
        if event.get("type") == "turn.completed" and isinstance(event_usage, dict):
            usage = {
                "input_tokens": _coerce_int(event_usage.get("input_tokens")),
                "cached_input_tokens": _coerce_int(event_usage.get("cached_input_tokens")),
                "output_tokens": _coerce_int(event_usage.get("output_tokens")),
                "reasoning_output_tokens": _coerce_int(event_usage.get("reasoning_output_tokens")),
            }
            usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return usage


async def _run_codex_exec(account, model_name: str, prompt: str, thread_id: str | None = None, image_files: list[str] | None = None) -> dict[str, Any]:
    import asyncio

    codex_home = ensure_codex_home(account.codex_home)
    workspace = build_codex_workspace(account)
    env = build_codex_process_env(codex_home)
    argv = build_codex_exec_argv(model_name, thread_id=thread_id, image_files=image_files)

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=workspace,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(prompt.encode("utf-8")),
            timeout=CODEX_EXEC_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError("Codex CLI timed out")

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        message = (stderr or stdout or f"Codex CLI exited with status {proc.returncode}").strip()
        raise RuntimeError(message[:1000])

    content = _extract_last_message_from_jsonl(stdout) or stdout.strip()
    return {
        "content": content,
        "usage": _extract_usage_from_jsonl(stdout),
        "thread_id": _extract_thread_id_from_jsonl(stdout) or thread_id,
        "stdout": stdout,
        "stderr": stderr,
    }


async def _check_codex_login_status(account) -> dict[str, Any]:
    import asyncio

    codex_home = ensure_codex_home(account.codex_home)
    workspace = build_codex_workspace(account)
    env = build_codex_process_env(codex_home)
    proc = await asyncio.create_subprocess_exec(
        "codex",
        "login",
        "status",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=workspace,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30)
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    combined = f"{stdout}\n{stderr}".lower()
    is_authenticated = proc.returncode == 0 and any(token in combined for token in ("logged in", "authenticated", "chatgpt"))
    return {
        "is_authenticated": is_authenticated,
        "auth_status": "authenticated" if is_authenticated else "pending",
        "stdout": stdout,
        "stderr": stderr,
    }


async def _stream_codex_exec(account, model_name: str, prompt: str, thread_id: str | None = None, image_files: list[str] | None = None):
    """Run Codex CLI and yield SSE events as output arrives."""
    codex_home = ensure_codex_home(account.codex_home)
    workspace = build_codex_workspace(account)
    env = build_codex_process_env(codex_home)
    argv = build_codex_exec_argv(model_name, thread_id=thread_id, image_files=image_files)

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=workspace,
    )

    proc.stdin.write(prompt.encode("utf-8"))
    await proc.stdin.drain()
    proc.stdin.close()

    request_id = f"codex-proxy-{uuid.uuid4().hex[:8]}"
    full_content = ""
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    thread_id_out = None
    stderr_lines = []

    try:
        async def _read_stdout(queue: asyncio.Queue):
            nonlocal full_content, total_usage, thread_id_out
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str or not line_str.startswith("{"):
                    continue
                try:
                    event = json.loads(line_str)
                except ValueError:
                    continue

                event_type = event.get("type", "")

                if event_type == "thread.started":
                    thread_id_out = event.get("thread_id")

                content = ""
                message = event.get("message") or event.get("msg") or {}
                if isinstance(message, dict):
                    content = message.get("content") or message.get("text") or ""
                if not content and event_type in {"agent_message", "message"}:
                    content = event.get("content") or event.get("text") or ""
                item = event.get("item")
                if not content and event_type == "item.completed" and isinstance(item, dict):
                    if item.get("type") in {"agent_message", "message"}:
                        content = item.get("content") or item.get("text") or ""

                if isinstance(content, str) and content.strip():
                    full_content += content
                    await queue.put({
                        "id": request_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}],
                    })

                if event_type == "turn.completed":
                    event_usage = event.get("usage")
                    if isinstance(event_usage, dict):
                        def _coerce(v):
                            try:
                                return int(v or 0)
                            except (TypeError, ValueError):
                                return 0
                        total_usage["input_tokens"] = _coerce(event_usage.get("input_tokens"))
                        total_usage["output_tokens"] = _coerce(event_usage.get("output_tokens"))
                        total_usage["total_tokens"] = total_usage["input_tokens"] + total_usage["output_tokens"]

            await queue.put(None)

        async def _read_stderr():
            nonlocal stderr_lines
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                stderr_lines.append(line.decode("utf-8", errors="replace"))

        queue: asyncio.Queue = asyncio.Queue()
        stdout_task = asyncio.create_task(_read_stdout(queue))
        stderr_task = asyncio.create_task(_read_stderr())

        try:
            while True:
                item = await asyncio.wait_for(queue.get(), timeout=CODEX_EXEC_TIMEOUT_SECONDS)
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            yield f"data: {json.dumps({'error': {'message': 'Codex CLI timed out', 'type': 'timeout'}})}\n\n"
            return

        await stdout_task
        await stderr_task

        returncode = proc.returncode
        if returncode != 0:
            error_msg = ("".join(stderr_lines) or full_content or f"Codex CLI exited with status {returncode}").strip()[:1000]
            yield f"data: {json.dumps({'error': {'message': error_msg, 'type': 'codex_error'}})}\n\n"
            return

    except Exception as exc:
        yield f"data: {json.dumps({'error': {'message': str(exc)[:1000], 'type': 'internal_error'}})}\n\n"
        return

    yield f"data: {json.dumps({'id': request_id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': model_name, 'choices': [{'index': 0, 'delta': {'content': ''}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': total_usage['input_tokens'], 'completion_tokens': total_usage['output_tokens'], 'total_tokens': total_usage['total_tokens']}})}\n\n"
    yield "data: [DONE]\n\n"

    if total_usage["total_tokens"] > 0:
        try:
            async with async_session() as db:
                from app.models import CodexAccount
                acct = await db.get(CodexAccount, account.id)
                if acct:
                    record_codex_account_usage(acct, total_usage)
                    await db.commit()
        except Exception:
            pass


async def _log_request(
    request_id: str,
    model: str,
    account_id: int | None,
    status: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    duration_ms: int,
    has_image: bool,
    image_count: int,
    error_message: str | None = None,
):
    try:
        async with async_session() as db:
            from app.models import CodexProxyRequestLog
            db.add(CodexProxyRequestLog(
                request_id=request_id,
                model=model,
                account_id=account_id,
                status=status,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
                has_image=has_image,
                image_count=image_count,
                error_message=error_message,
            ))
            await db.commit()
    except Exception as exc:
        logger.warning(f"Failed to log codex proxy request: {exc}")


@router.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint backed by Codex CLI."""
    start_time = time.time()
    messages = [m.model_dump(exclude_none=True) for m in request.messages]

    image_files = _extract_images_from_messages(messages)
    prompt = _messages_to_codex_prompt(messages)
    has_image = len(image_files) > 0

    if not prompt:
        raise HTTPException(status_code=400, detail="No text prompt found in messages")

    async with async_session() as db:
        account = await select_codex_account(db, provider=None)
        if not account:
            raise HTTPException(status_code=503, detail="No authenticated Codex account available")

        try:
            status = await _check_codex_login_status(account)
            if not status["is_authenticated"]:
                account.auth_status = status["auth_status"]
                account.last_error = (status.get("stderr") or status.get("stdout") or "Not authenticated")[:1000]
                await db.commit()
                raise HTTPException(status_code=503, detail="Codex account is not authenticated")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Codex status check failed: {str(exc)}")

    thread_id = None
    request_id = f"codex-proxy-{uuid.uuid4().hex[:8]}"

    if request.stream:
        return StreamingResponse(
            _stream_codex_exec_with_logging(account, request.model, prompt, thread_id=thread_id, image_files=image_files, request_id=request_id, has_image=has_image, image_count=len(image_files), start_time=start_time),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        full_content = ""
        total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        error_detail = None

        async for line in _stream_codex_exec(account, request.model, prompt, thread_id=thread_id, image_files=image_files):
            line_str = line.strip()
            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    if "error" in data:
                        error_detail = data["error"].get("message", "Unknown error")
                        break
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if delta.get("content"):
                            full_content += delta["content"]
                        if choices[0].get("finish_reason") == "stop":
                            usage = data.get("usage")
                            if usage:
                                total_usage = usage
                except json.JSONDecodeError:
                    continue

        duration_ms = int((time.time() - start_time) * 1000)

        if error_detail:
            await _log_request(
                request_id=request_id,
                model=request.model,
                account_id=account.id,
                status="error",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                duration_ms=duration_ms,
                has_image=has_image,
                image_count=len(image_files),
                error_message=error_detail,
            )
            raise HTTPException(status_code=502, detail=f"Codex CLI error: {error_detail}")

        await _log_request(
            request_id=request_id,
            model=request.model,
            account_id=account.id,
            status="success",
            prompt_tokens=total_usage.get("input_tokens", 0),
            completion_tokens=total_usage.get("output_tokens", 0),
            total_tokens=total_usage.get("total_tokens", 0),
            duration_ms=duration_ms,
            has_image=has_image,
            image_count=len(image_files),
        )

        return {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": total_usage.get("input_tokens", 0),
                "completion_tokens": total_usage.get("output_tokens", 0),
                "total_tokens": total_usage.get("total_tokens", 0),
            },
        }


async def _stream_codex_exec_with_logging(account, model_name: str, prompt: str, thread_id: str | None = None, image_files: list[str] | None = None, request_id: str = "", has_image: bool = False, image_count: int = 0, start_time: float = 0):
    """Streaming wrapper that logs after the stream completes."""
    full_content = ""
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    error_detail = None

    async for line in _stream_codex_exec(account, model_name, prompt, thread_id=thread_id, image_files=image_files):
        yield line
        line_str = line.strip()
        if line_str.startswith("data: "):
            data_str = line_str[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                if "error" in data:
                    error_detail = data["error"].get("message", "Unknown error")
                    break
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    if delta.get("content"):
                        full_content += delta["content"]
                    if choices[0].get("finish_reason") == "stop":
                        usage = data.get("usage")
                        if usage:
                            total_usage = usage
            except json.JSONDecodeError:
                continue

    duration_ms = int((time.time() - start_time) * 1000)

    await _log_request(
        request_id=request_id,
        model=model_name,
        account_id=account.id,
        status="error" if error_detail else "success",
        prompt_tokens=total_usage.get("input_tokens", 0),
        completion_tokens=total_usage.get("output_tokens", 0),
        total_tokens=total_usage.get("total_tokens", 0),
        duration_ms=duration_ms,
        has_image=has_image,
        image_count=image_count,
        error_message=error_detail,
    )
