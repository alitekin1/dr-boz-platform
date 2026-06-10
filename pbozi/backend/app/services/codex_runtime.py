import asyncio
import base64
import json
import os
import re
import shlex
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CodexAccount, Provider
from app.services.codex_capacity_service import select_codex_account_for_subscription


OPENAI_COMPATIBLE_PROVIDER_KIND = "openai_compatible"
CODEX_SUBSCRIPTION_PROVIDER_KIND = "codex_subscription"
CODEX_ACCOUNTS_DIR = Path(os.getenv("CODEX_ACCOUNTS_DIR", "./codex_accounts")).resolve()
CODEX_WORKSPACES_DIR = Path(os.getenv("CODEX_WORKSPACES_DIR", "/tmp/bozgpt_codex_workspaces")).resolve()
CODEX_EXEC_TIMEOUT_SECONDS = int(os.getenv("CODEX_EXEC_TIMEOUT_SECONDS", "90"))
CODEX_STATUS_TIMEOUT_SECONDS = int(os.getenv("CODEX_STATUS_TIMEOUT_SECONDS", "60"))
CODEX_MODEL_PRESETS = [
    {
        "name": "gpt-5.5",
        "display_name": "GPT-5.5 Pro",
        "context_window": 272000,
        "pricing_input": 5.0,
        "pricing_output": 30.0,
    },
    {
        "name": "gpt-5.4",
        "display_name": "GPT-5.4 Pro",
        "context_window": 272000,
        "pricing_input": 2.5,
        "pricing_output": 15.0,
    },
    {
        "name": "gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini",
        "context_window": 272000,
        "pricing_input": 0.75,
        "pricing_output": 4.5,
    },
    {
        "name": "gpt-5.3-codex",
        "display_name": "GPT-5.3 Pro",
        "context_window": 272000,
        "pricing_input": 1.75,
        "pricing_output": 14.0,
    },
    {
        "name": "gpt-5.3-codex-spark",
        "display_name": "GPT-5.3 Spark",
        "context_window": 272000,
        "pricing_input": 0.0,
        "pricing_output": 0.0,
    },
]


def normalize_provider_kind(value: str | None) -> str:
    kind = (value or OPENAI_COMPATIBLE_PROVIDER_KIND).strip().lower()
    if kind in {"openai-compatible", "openai compatible", "openai"}:
        return OPENAI_COMPATIBLE_PROVIDER_KIND
    if kind in {"codex", "openai_codex", "openai-codex"}:
        return CODEX_SUBSCRIPTION_PROVIDER_KIND
    return kind or OPENAI_COMPATIBLE_PROVIDER_KIND


def is_codex_subscription_provider(provider: Provider | None) -> bool:
    return normalize_provider_kind(getattr(provider, "kind", None)) == CODEX_SUBSCRIPTION_PROVIDER_KIND


def build_codex_home(account_id: int | str | None = None) -> str:
    suffix = str(account_id or uuid.uuid4().hex)
    safe_suffix = re.sub(r"[^A-Za-z0-9_.-]+", "_", suffix).strip("._") or uuid.uuid4().hex
    return str(CODEX_ACCOUNTS_DIR / f"acct_{safe_suffix}")


def ensure_codex_home(path: str) -> str:
    normalized = str(Path(path).resolve())
    Path(normalized).mkdir(parents=True, exist_ok=True)
    return normalized


def build_codex_workspace(account: Any) -> str:
    account_key = getattr(account, "id", None) or getattr(account, "codex_home", None) or uuid.uuid4().hex
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(account_key)).strip("._") or uuid.uuid4().hex
    workspace = (CODEX_WORKSPACES_DIR / f"acct_{safe_key}").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return str(workspace)


def build_codex_process_env(codex_home: str) -> dict[str, str]:
    allowed_keys = {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "USER",
        "USERNAME",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed_keys and value}
    env["PATH"] = env.get("PATH") or os.defpath
    env["CODEX_HOME"] = codex_home
    env["HOME"] = codex_home
    return env


def build_codex_login_command(account: Any) -> dict[str, Any]:
    codex_home = ensure_codex_home(str(account.codex_home))
    argv = ["codex", "login", "--device-auth"]
    return {
        "argv": argv,
        "env": {"CODEX_HOME": codex_home},
        "shell": f"CODEX_HOME={shlex.quote(codex_home)} {' '.join(shlex.quote(part) for part in argv)}",
    }


def build_codex_exec_argv(model_name: str, thread_id: str | None = None, image_files: list[str] | None = None) -> list[str]:
    base = [
        "codex",
        "--ask-for-approval",
        "never",
        "--search",
    ]
    
    if thread_id:
        sub = [
            "exec",
            "resume",
            "--json",
            "--model",
            model_name,
            "--skip-git-repo-check",
            "--ignore-rules",
            thread_id,
            "-",
        ]
    else:
        sub = [
            "exec",
            "--json",
            "--model",
            model_name,
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "--ignore-rules",
            "-",
        ]
    
    if image_files:
        for img_path in image_files:
            sub.extend(["--image", img_path])
    
    return base + sub


def build_codex_status_argv() -> list[str]:
    return [
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--json",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ignore-rules",
        "/status",
    ]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def select_codex_account(db: AsyncSession, provider: Provider | None = None, user_id: int | None = None) -> CodexAccount | None:
    if user_id is not None:
        return await select_codex_account_for_subscription(db, provider=provider, user_id=user_id)

    now = _utc_now()
    conditions = [
        CodexAccount.is_active == True,
        CodexAccount.status == "active",
        CodexAccount.auth_status == "authenticated",
        or_(CodexAccount.cooldown_until == None, CodexAccount.cooldown_until <= now),
    ]
    if provider is not None and getattr(provider, "id", None) is not None:
        provider_config = getattr(provider, "config_json", None)
        account_ids = []
        if isinstance(provider_config, dict) and isinstance(provider_config.get("account_ids"), list):
            account_ids = [int(item) for item in provider_config["account_ids"] if str(item).isdigit()]
        if account_ids:
            conditions.append(CodexAccount.id.in_(account_ids))
        else:
            conditions.append(or_(CodexAccount.provider_id == provider.id, CodexAccount.provider_id == None))

    result = await db.execute(
        select(CodexAccount)
        .where(*conditions)
        .order_by(CodexAccount.last_used_at.is_not(None), CodexAccount.last_used_at, CodexAccount.id)
    )
    return result.scalars().first()


def _extract_images_from_messages(messages: list[dict]) -> list[str]:
    """Extract base64 images from messages and save as temp files.
    
    Returns a list of file paths to the saved images.
    """
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
                    fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="codex_img_")
                    try:
                        os.write(fd, image_bytes)
                    finally:
                        os.close(fd)
                    image_paths.append(tmp_path)
                except Exception:
                    continue
    
    return image_paths


def messages_to_codex_prompt(messages: list[dict]) -> str:
    parts: list[str] = []
    image_index = 0
    for message in messages:
        role = str(message.get("role") or "user")
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


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _extract_usage_from_jsonl(stdout: str) -> dict[str, int]:
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


def sanitize_codex_limit_status_text(text: str, max_chars: int = 4000) -> str:
    sanitized = text or ""
    patterns = [
        r"sk-[A-Za-z0-9_\-]{20,}",
        r"(access[_ -]?token\s*[:=]\s*)[A-Za-z0-9._\-]{20,}",
        r"(refresh[_ -]?token\s*[:=]\s*)[A-Za-z0-9._\-]{20,}",
        r"(api[_ -]?key\s*[:=]\s*)[A-Za-z0-9._\-]{20,}",
    ]
    for pattern in patterns:
        sanitized = re.sub(pattern, lambda match: f"{match.group(1) if match.lastindex else ''}[redacted]", sanitized, flags=re.IGNORECASE)
    sanitized = sanitized.strip()
    if len(sanitized) > max_chars:
        sanitized = sanitized[: max(0, max_chars - 20)].rstrip() + "\n...[truncated]"
    return sanitized


async def refresh_codex_limit_status(account: CodexAccount) -> dict[str, Any]:
    codex_home = ensure_codex_home(account.codex_home)
    workspace = build_codex_workspace(account)
    env = build_codex_process_env(codex_home)
    proc = await asyncio.create_subprocess_exec(
        *build_codex_status_argv(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=workspace,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=CODEX_STATUS_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError("Codex status check timed out")

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    raw_text = _extract_last_message_from_jsonl(stdout) or stdout.strip() or stderr.strip()
    status_text = sanitize_codex_limit_status_text(raw_text)
    return {
        "checked_at": _utc_now().isoformat(),
        "status_text": status_text,
        "usage": _extract_usage_from_jsonl(stdout),
        "returncode": proc.returncode,
        "stderr": sanitize_codex_limit_status_text(stderr, max_chars=1000),
    }


def merge_codex_usage_metadata(metadata: dict[str, Any] | None, run_usage: dict[str, Any], model_name: str) -> dict[str, Any]:
    next_metadata = dict(metadata or {})
    usage = dict(next_metadata.get("usage") or {})
    by_model = dict(usage.get("by_model") or {})
    model_usage = dict(by_model.get(model_name) or {})
    token_keys = [
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ]

    usage["request_count"] = _coerce_int(usage.get("request_count")) + 1
    model_usage["request_count"] = _coerce_int(model_usage.get("request_count")) + 1
    for key in token_keys:
        value = _coerce_int(run_usage.get(key))
        usage[key] = _coerce_int(usage.get(key)) + value
        model_usage[key] = _coerce_int(model_usage.get(key)) + value

    last_run = {
        "model": model_name,
        "at": _utc_now().isoformat(),
        **{key: _coerce_int(run_usage.get(key)) for key in token_keys},
    }
    usage["last_run"] = last_run
    by_model[model_name] = model_usage
    usage["by_model"] = by_model
    next_metadata["usage"] = usage
    return next_metadata


def calculate_codex_billable_usage(
    usage_logs: list[dict[str, Any] | None],
    estimated_app_input_tokens: int,
    default_output_tokens: int,
) -> dict[str, Any]:
    provider_usage = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }
    other_input_tokens = 0
    other_output_tokens = 0
    saw_codex_usage = False

    for usage in usage_logs:
        if not isinstance(usage, dict):
            continue
        input_tokens = _coerce_int(
            usage.get("input_tokens")
            if usage.get("input_tokens") is not None
            else usage.get("prompt_tokens")
        )
        output_tokens = _coerce_int(
            usage.get("output_tokens")
            if usage.get("output_tokens") is not None
            else usage.get("completion_tokens")
        )
        if usage.get("usage_source") == "codex_cli":
            saw_codex_usage = True
            provider_usage["input_tokens"] += input_tokens
            provider_usage["cached_input_tokens"] += _coerce_int(usage.get("cached_input_tokens"))
            provider_usage["output_tokens"] += output_tokens
            provider_usage["reasoning_output_tokens"] += _coerce_int(usage.get("reasoning_output_tokens"))
            provider_usage["total_tokens"] += _coerce_int(usage.get("total_tokens")) or (input_tokens + output_tokens)
        else:
            other_input_tokens += input_tokens
            other_output_tokens += output_tokens

    if saw_codex_usage:
        codex_billable_input = min(
            provider_usage["input_tokens"],
            max(0, _coerce_int(estimated_app_input_tokens)),
        )
        codex_billable_output = provider_usage["output_tokens"] or _coerce_int(default_output_tokens)
        usage_source = "codex_cli_billable_app_input"
    else:
        codex_billable_input = max(0, _coerce_int(estimated_app_input_tokens))
        codex_billable_output = _coerce_int(default_output_tokens)
        usage_source = "estimated"

    return {
        "input_tokens": codex_billable_input + other_input_tokens,
        "output_tokens": codex_billable_output + other_output_tokens,
        "usage_source": usage_source,
        "provider_usage": provider_usage if saw_codex_usage else None,
    }


async def run_codex_exec(
    account: CodexAccount,
    model_name: str,
    prompt: str,
    thread_id: str | None = None,
    image_files: list[str] | None = None,
) -> dict[str, Any]:
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


async def check_codex_login_status(account: CodexAccount) -> dict[str, Any]:
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
