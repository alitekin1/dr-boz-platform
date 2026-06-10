"""Codex App-Server JSON-RPC client.

Communicates with Codex CLI via the app-server protocol over stdio.
This replaces the text-based `codex exec --json` approach with structured
JSON-RPC, eliminating tool hallucination leaks.

Protocol:
1. Spawn: codex app-server --listen stdio://
2. Initialize handshake (JSON-RPC request -> response)
3. Send notifications (e.g. turn/start)
4. Receive notifications (agent message deltas, turn completed)
5. Handle requests (approval, user input)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


JsonRpcId = str | int


@dataclass
class _PendingRequest:
    resolve: Callable[[Any], None]
    reject: Callable[[Exception], None]
    timer: asyncio.TimerHandle


@dataclass
class CodexTurnResult:
    text: str | None = None
    thread_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    aborted: bool = False
    error: str | None = None


class CodexAppServerClient:
    """JSON-RPC client for Codex app-server over stdio."""

    def __init__(
        self,
        *,
        model_name: str,
        workspace: str | None = None,
        env: dict[str, str] | None = None,
        request_timeout: float = 120.0,
    ) -> None:
        self.model_name = model_name
        self.workspace = workspace or os.getcwd()
        self.env = env or dict(os.environ)
        self.request_timeout = request_timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._counter = 0
        self._pending: dict[str, _PendingRequest] = {}
        self._notification_handlers: list[Callable[[str, Any], Coroutine[Any, Any, None]]] = []
        self._request_handlers: list[Callable[[str, Any], Coroutine[Any, Any, Any]]] = []
        self._read_task: asyncio.Task[None] | None = None
        self._closed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> dict[str, Any]:
        """Spawn codex app-server and perform initialize handshake."""
        if self._proc is not None:
            return {}

        argv = [
            "codex",
            "app-server",
            "--listen", "stdio://",
            "-c", f'model="{self.model_name}"',
        ]

        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
            cwd=self.workspace,
        )

        if not self._proc.stdin or not self._proc.stdout:
            raise RuntimeError("codex app-server stdio pipes unavailable")

        # Start stdout reader
        self._read_task = asyncio.create_task(self._read_loop())

        # Initialize handshake
        result = await self._request(
            "initialize",
            {
                "protocolVersion": "1.0",
                "clientInfo": {"name": "jgpti", "version": "1.0.0"},
                "capabilities": {},
            },
            timeout=30.0,
        )
        await self._notify("initialized", {})
        logger.info("Codex app-server connected: %s", result)
        return result if isinstance(result, dict) else {}

    async def close(self) -> None:
        """Close connection and cleanup."""
        if self._closed:
            return
        self._closed = True

        # Cancel pending requests
        for pending in list(self._pending.values()):
            pending.reject(RuntimeError("codex app-server closed"))
            pending.timer.cancel()
        self._pending.clear()

        # Stop reader
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Kill process
        if self._proc and self._proc.returncode is None:
            self._proc.kill()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            # Drain stderr to avoid zombie pipes
            if self._proc.stderr:
                try:
                    await asyncio.wait_for(self._proc.stderr.read(), timeout=1.0)
                except Exception:
                    pass
        self._proc = None

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------

    async def start_turn(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        system_prompt: str | None = None,
    ) -> CodexTurnResult:
        """Start a conversation turn and collect the result."""
        result_text = ""
        completed_event = asyncio.Event()
        aborted = False
        usage: dict[str, int] = {}
        error: str | None = None
        current_thread_id = thread_id

        # Build input items
        input_items: list[dict[str, Any]] = []
        if system_prompt:
            input_items.append({"type": "text", "text": system_prompt})
        input_items.append({"type": "text", "text": prompt})

        payload: dict[str, Any] = {"input": input_items}
        if thread_id:
            payload["threadId"] = thread_id

        async def on_notification(method: str, params: Any) -> None:
            nonlocal result_text, aborted, usage, error, current_thread_id
            method_lower = method.lower()
            found_thread_id = _extract_thread_id(params)
            if not found_thread_id and "thread" in method_lower and isinstance(params, dict):
                raw_id = params.get("id")
                if isinstance(raw_id, str) and raw_id.strip():
                    found_thread_id = raw_id.strip()
            if found_thread_id:
                current_thread_id = found_thread_id

            if method_lower == "item/agentmessage/delta":
                text = _extract_delta_text(params)
                if text:
                    result_text += text
                return

            if method_lower == "item/completed":
                text = _extract_completed_text(params)
                if text:
                    result_text = text  # snapshot replaces streaming
                return

            if method_lower == "turn/completed":
                usage = _extract_usage(params)
                completed_event.set()
                return

            if method_lower in {"turn/failed", "turn.failed"}:
                error = _extract_error(params)
                completed_event.set()
                return

            if method_lower in {"turn/interrupted", "turn.interrupted"}:
                aborted = True
                completed_event.set()
                return

        async def on_request(method: str, params: Any) -> Any:
            method_lower = method.lower()

            # Auto-approve execution and file change requests
            if "requestapproval" in method_lower:
                logger.info("Auto-approving: %s", method)
                return {"decision": "accept"}

            # Handle user input requests (should not happen in web chat)
            if "requestuserinput" in method_lower:
                logger.warning("Unexpected user input request from Codex: %s", method)
                return {"text": "continue"}

            return None

        self.add_notification_handler(on_notification)
        self.add_request_handler(on_request)

        try:
            # Send turn/start
            await self._notify("turn/start", payload)

            # Wait for turn to complete (with timeout)
            try:
                await asyncio.wait_for(completed_event.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                logger.warning("Codex turn timed out")
                aborted = True
                await self._notify("turn/interrupt", {})
                try:
                    await asyncio.wait_for(completed_event.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    pass

        finally:
            self._notification_handlers.remove(on_notification)
            self._request_handlers.remove(on_request)

        return CodexTurnResult(
            text=result_text.strip() or None,
            thread_id=current_thread_id,
            usage=usage,
            aborted=aborted,
            error=error,
        )

    async def steer(self, text: str, *, thread_id: str, turn_id: str | None = None) -> None:
        """Send a steer message during an active turn."""
        payload: dict[str, Any] = {"threadId": thread_id, "input": [{"type": "text", "text": text}]}
        if turn_id:
            payload["expectedTurnId"] = turn_id
        await self._notify("turn/steer", payload)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def add_notification_handler(
        self, handler: Callable[[str, Any], Coroutine[Any, Any, None]]
    ) -> None:
        self._notification_handlers.append(handler)

    def add_request_handler(
        self, handler: Callable[[str, Any], Coroutine[Any, Any, Any]]
    ) -> None:
        self._request_handlers.append(handler)

    # ------------------------------------------------------------------
    # Internal I/O
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Read JSON-RPC lines from stdout and dispatch."""
        if not self._proc or not self._proc.stdout:
            return
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    logger.info("Codex stdout EOF")
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue
                logger.debug("Codex recv: %s", line_str[:500])
                try:
                    envelope = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.debug("Ignoring non-JSON line: %s", line_str[:200])
                    continue
                await self._dispatch(envelope)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Codex stdout read error: %s", exc)
        finally:
            # Flush pending on disconnect
            for pending in list(self._pending.values()):
                pending.reject(RuntimeError("codex app-server disconnected"))
                pending.timer.cancel()
            self._pending.clear()

    async def _dispatch(self, envelope: dict[str, Any]) -> None:
        msg_id = envelope.get("id")
        method = envelope.get("method")
        params = envelope.get("params", {})
        result = envelope.get("result")
        error = envelope.get("error")

        # Response to our request
        if msg_id is not None and method is None:
            req_id = str(msg_id)
            pending = self._pending.pop(req_id, None)
            if pending:
                pending.timer.cancel()
                if error:
                    pending.reject(RuntimeError(f"JSON-RPC error: {error}"))
                else:
                    pending.resolve(result)
            return

        # Request from server (we need to respond)
        if msg_id is not None and method is not None:
            response: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
            try:
                for handler in self._request_handlers:
                    try:
                        handler_result = await handler(method, params)
                        if handler_result is not None:
                            response["result"] = handler_result
                            break
                    except Exception as exc:
                        logger.warning("Request handler error: %s", exc)
                        response["error"] = {"code": -32000, "message": str(exc)}
                        break
                else:
                    # No handler claimed it
                    response["error"] = {"code": -32601, "message": f"Method not found: {method}"}
            except Exception as exc:
                response["error"] = {"code": -32000, "message": str(exc)}
            self._write(response)
            return

        # Notification from server (no id, no response needed)
        if msg_id is None and method is not None:
            for handler in self._notification_handlers:
                try:
                    await handler(method, params)
                except Exception as exc:
                    logger.warning("Notification handler error: %s", exc)
            return

    def _write(self, envelope: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("codex app-server not connected")
        payload = json.dumps(envelope, ensure_ascii=False) + "\n"
        self._proc.stdin.write(payload.encode("utf-8"))
        # In Python asyncio, we need to drain - but for simplicity with codex
        # we can use a task to avoid blocking
        asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        if self._proc and self._proc.stdin:
            try:
                await self._proc.stdin.drain()
            except Exception:
                pass

    async def _request(self, method: str, params: Any, *, timeout: float | None = None) -> Any:
        self._counter += 1
        req_id = f"rpc-{self._counter}"
        envelope = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}

        loop = asyncio.get_event_loop()
        future: asyncio.Future[Any] = loop.create_future()

        def on_timeout() -> None:
            pending = self._pending.pop(req_id, None)
            if pending and not future.done():
                future.set_exception(TimeoutError(f"codex app-server timeout: {method}"))

        timer = loop.call_later(timeout or self.request_timeout, on_timeout)
        self._pending[req_id] = _PendingRequest(
            resolve=lambda val: future.set_result(val) if not future.done() else None,
            reject=lambda exc: future.set_exception(exc) if not future.done() else None,
            timer=timer,
        )

        self._write(envelope)
        return await future

    async def _notify(self, method: str, params: Any) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_delta_text(params: Any) -> str | None:
    if not isinstance(params, dict):
        return None
    item = params.get("item") or {}
    if isinstance(item, dict):
        content = item.get("content") or item.get("text")
        if isinstance(content, str):
            return content
    delta = params.get("delta")
    if isinstance(delta, str):
        return delta
    return None


def _extract_completed_text(params: Any) -> str | None:
    if not isinstance(params, dict):
        return None
    item = params.get("item") or {}
    if not isinstance(item, dict):
        return None
    if item.get("type") not in {"agent_message", "message"}:
        return None
    content = item.get("content") or item.get("text")
    if isinstance(content, str):
        return content
    return None


def _extract_usage(params: Any) -> dict[str, int]:
    if not isinstance(params, dict):
        return {}
    usage = params.get("usage") or {}
    if not isinstance(usage, dict):
        return {}
    return {
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "total_tokens": int(usage.get("total_tokens", 0) or 0),
    }


def _extract_error(params: Any) -> str | None:
    if not isinstance(params, dict):
        return None
    error_obj = params.get("error")
    if isinstance(error_obj, dict):
        message = error_obj.get("message")
        if isinstance(message, str):
            # Codex sometimes nests JSON errors as strings
            try:
                nested = json.loads(message)
                if isinstance(nested, dict):
                    nested_msg = nested.get("error", {}).get("message")
                    if isinstance(nested_msg, str):
                        return nested_msg
            except (ValueError, TypeError):
                pass
            return message
    message = params.get("message")
    if isinstance(message, str):
        return message
    return None


def _extract_thread_id(params: Any) -> str | None:
    if not isinstance(params, dict):
        return None
    for key in ("threadId", "thread_id"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("thread", "turn", "session"):
        nested = params.get(key)
        found = _extract_thread_id(nested)
        if found:
            return found
    return None
