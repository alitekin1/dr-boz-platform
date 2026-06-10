import logging
import asyncio
import ast
import base64
import json
import os
import re
import shutil
import tempfile
import uuid
import html
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from urllib.parse import quote

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import TITLE_GENERATOR_PROMPT, WEB_SEARCH_API_KEY, WEB_SEARCH_API_URL, WEB_SEARCH_MODEL, WEB_SEARCH_PROVIDER
from app.models import (
    Chat,
    EmbeddingConfig,
    Message,
    Model as DBModel,
    Provider,
    Project,
    Skill,
    SubscriptionPlan,
    SystemPrompt,
    TranscriptionConfig,
    Tool,
    ToolBinding,
    ToolCall,
    UserPreference,
    UserSubscription,
    WebSearchConfig,
)
from app.services.project_sharing import build_project_instructions_prompt
from app.services.codex_runtime import (
    _extract_images_from_messages,
    check_codex_login_status,
    is_codex_subscription_provider,
    merge_codex_usage_metadata,
    messages_to_codex_prompt,
    run_codex_exec,
    select_codex_account,
)
from app.services.codex_capacity_service import (
    CodexCapacityError,
    record_codex_account_usage,
    resolve_codex_capacity_selection,
)
from app.services.prompt_service import PromptService


class CalculatorError(ValueError):
    pass


PDF_GENERATOR_MAX_SOURCE_CHARS = 120_000
PDF_GENERATOR_LATEX_TIMEOUT_SECONDS = 90
PDF_GENERATOR_MAX_BASE64_BYTES = 1_500_000
PDF_GENERATOR_TTL_SECONDS = 24 * 60 * 60
PDF_GENERATOR_OUTPUT_DIR = os.path.abspath(os.path.join(".", "uploads", "generated_pdfs"))
PDF_GENERATOR_FONT_FILENAME = "Vazirmatn-Regular.ttf"
PDF_GENERATOR_FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "fonts", PDF_GENERATOR_FONT_FILENAME)
PDF_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
PDF_FALLBACK_PAGE_WIDTH = 595
PDF_FALLBACK_PAGE_HEIGHT = 842
PDF_FALLBACK_MARGIN_X = 50
PDF_FALLBACK_MARGIN_Y = 50
PDF_FALLBACK_FONT_SIZE = 12
PDF_FALLBACK_LINE_HEIGHT = 16


class SafeCalculatorEvaluator(ast.NodeVisitor):
    ALLOWED_BINARY = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
    }
    ALLOWED_UNARY = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp):
        op = type(node.op)
        if op not in self.ALLOWED_BINARY:
            raise CalculatorError("Unsupported operator")
        left = self.visit(node.left)
        right = self.visit(node.right)
        if abs(left) > 10**12 or abs(right) > 10**12:
            raise CalculatorError("Numbers are too large")
        if op is ast.Pow and abs(right) > 10:
            raise CalculatorError("Exponent is too large")
        return self.ALLOWED_BINARY[op](left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        op = type(node.op)
        if op not in self.ALLOWED_UNARY:
            raise CalculatorError("Unsupported unary operator")
        return self.ALLOWED_UNARY[op](self.visit(node.operand))

    def visit_Constant(self, node: ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise CalculatorError("Only numbers are allowed")
        return node.value

    def generic_visit(self, node):
        raise CalculatorError("Unsupported expression")


BUILTIN_TOOLS: dict[str, dict[str, Any]] = {
    "image_generator": {
        "display_name": "Image Generator",
        "description": "Generate an image from a text description using OpenRouter's google/gemini-3-pro-image-preview model. Returns the generated image markdown or URL.",
        "kind": "builtin",
        "implementation_key": "builtin:image_generator",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A detailed text description of the image to generate.",
                }
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
        "handler": "run_image_generator_tool",
    },
    "calculator": {
        "display_name": "Calculator",
        "description": "Safely evaluate arithmetic expressions. Use for math instead of guessing.",
        "kind": "builtin",
        "implementation_key": "builtin:calculator",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression using numbers, parentheses, +, -, *, /, //, %, and **.",
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        "handler": "run_calculator_tool",
    },
    "web_search": {
        "display_name": "Web Search",
        "description": "Search the web for up-to-date information and return a concise answer with source links.",
        "kind": "builtin",
        "implementation_key": "builtin:web_search",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "handler": "run_web_search_tool",
    },
    "pdf_generator": {
        "display_name": "PDF Generator",
        "description": (
            "Generate a PDF using XeLaTeX with RTL Persian support and Vazirmatn font. "
            "Supports full LaTeX documents and math."
        ),
        "kind": "builtin",
        "implementation_key": "builtin:pdf_generator",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "LaTeX source text. In body mode this is injected inside the document body; "
                        "in full_document mode this must be a complete LaTeX document."
                    ),
                },
                "latex_mode": {
                    "type": "string",
                    "enum": ["body", "full_document"],
                    "description": "body wraps content in an RTL Vazirmatn template; full_document compiles content as-is.",
                },
                "title": {
                    "type": "string",
                    "description": "Optional title used only in body mode.",
                },
                "rtl": {
                    "type": "boolean",
                    "description": "When true (default), wraps body mode content in an RTL environment.",
                },
                "output_filename": {
                    "type": "string",
                    "description": "Optional output PDF filename.",
                },
                "return_base64": {
                    "type": "boolean",
                    "description": "Optional. Include base64 PDF content for small files.",
                },
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        "handler": "run_pdf_generator_tool",
    },
    "save_user_preference": {
        "display_name": "Save User Preference",
        "description": (
            "Save a specific user preference to improve future interactions. "
            "Use this when the user explicitly states a preference or how they want you to behave."
        ),
        "kind": "builtin",
        "implementation_key": "builtin:save_user_preference",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "preference_text": {
                    "type": "string",
                    "description": "A concise description of the preference to save.",
                }
            },
            "required": ["preference_text"],
            "additionalProperties": False,
        },
        "handler": "run_save_user_preference_tool",
    },
    "search_project": {
        "display_name": "Search Project",
        "description": "Search for relevant information within the current project's knowledge base (indexed documents). Use this tool whenever you need to find facts or context from the user's uploaded files in this project.",
        "kind": "builtin",
        "implementation_key": "builtin:search_project",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "n_results": {"type": "integer", "description": "Number of results to return", "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "handler": "run_search_project_tool",
    },
    "search_project_queries": {
        "display_name": "Search Project Queries",
        "description": "Run multiple semantic searches against the project's knowledge base at once. Use this when you need to find information across different aspects of a topic. Returns combined results from all queries.",
        "kind": "builtin",
        "implementation_key": "builtin:search_project_queries",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 2-5 search queries to run in parallel against the project documents.",
                },
                "n_results": {"type": "integer", "description": "Number of results per query", "default": 5},
            },
            "required": ["queries"],
            "additionalProperties": False,
        },
        "handler": "run_search_project_queries_tool",
    },
    "list_project_files": {
        "display_name": "List Project Files",
        "description": "List all files currently uploaded to the current project. Use this to see what documents are available in the project's knowledge base.",
        "kind": "builtin",
        "implementation_key": "builtin:list_project_files",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "handler": "run_list_project_files_tool",
    },
    "read_skill": {
        "display_name": "Read Skill",
        "description": "Read the SKILL.md instructions and file list for an active skill. Use this before applying a relevant skill.",
        "kind": "builtin",
        "implementation_key": "builtin:read_skill",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The exact active skill name shown in @skills.",
                }
            },
            "required": ["skill_name"],
            "additionalProperties": False,
        },
        "handler": "run_read_skill_tool",
    },
    "read_skill_file": {
        "display_name": "Read Skill File",
        "description": "Read a UTF-8 supporting file from an active skill directory using a relative path from that skill directory.",
        "kind": "builtin",
        "implementation_key": "builtin:read_skill_file",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "The exact active skill name shown in @skills.",
                },
                "relative_path": {
                    "type": "string",
                    "description": "Path relative to the skill directory, for example references/usage.md.",
                },
            },
            "required": ["skill_name", "relative_path"],
            "additionalProperties": False,
        },
        "handler": "run_read_skill_file_tool",
    },
    "send_file": {
        "display_name": "ارسال فایل",
        "description": "Upload a file from the server to the user. Provide the path to the file.",
        "kind": "builtin",
        "implementation_key": "builtin:send_file",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute or relative path to the file.",
                }
            },
            "required": ["file_path"],
            "additionalProperties": False,
        },
        "handler": "run_send_file_tool",
    },
    "chart_generator": {
        "display_name": "Chart Generator",
        "description": "Generate a chart or graph (bar, line, pie, scatter, histogram) from data and save it as a PNG image. Use for data visualization requests.",
        "kind": "builtin",
        "implementation_key": "builtin:chart_generator",
        "implementation_config": None,
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "pie", "scatter", "histogram"],
                    "description": "Type of chart to generate",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the chart",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Labels for x-axis or pie slices",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Numeric data values",
                },
                "x_label": {
                    "type": "string",
                    "description": "X-axis label",
                },
                "y_label": {
                    "type": "string",
                    "description": "Y-axis label",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (must end with .png)",
                },
                "colors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional color names or hex codes",
                },
            },
            "required": ["chart_type", "title", "values"],
            "additionalProperties": False,
        },
        "handler": "run_chart_generator_tool",
    },
}


class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        provider_message: str | None = None,
    ):
        text = (message or "LLM request failed").strip() or "LLM request failed"
        super().__init__(text)
        self.message = text
        self.status_code = status_code
        self.code = (code or "").strip().lower() or None
        self.provider_message = (provider_message or "").strip() or None

    def __str__(self) -> str:
        return self.message


AUTO_ROUTER_MODEL_TYPE = "auto_router"
NORMAL_MODEL_TYPE = "normal"
AUTO_ROUTER_CONFIG_KEY = "auto_router"
AUTO_ROUTER_MODEL_ID_FIELDS = (
    "router_model_id",
    "easy_model_id",
    "medium_model_id",
    "hard_model_id",
    "vision_model_id",
    "research_model_id",
    "fallback_model_id",
)
AUTO_ROUTER_TARGET_FIELDS = (
    "easy_model_id",
    "medium_model_id",
    "hard_model_id",
    "vision_model_id",
    "research_model_id",
    "fallback_model_id",
)


def _model_capabilities(model: DBModel | Any | None) -> dict[str, Any]:
    capabilities = getattr(model, "capabilities", None)
    return capabilities if isinstance(capabilities, dict) else {}


def is_auto_router_model(model: DBModel | Any | None) -> bool:
    capabilities = _model_capabilities(model)
    return capabilities.get("model_type") == AUTO_ROUTER_MODEL_TYPE


def get_auto_router_config(model_or_capabilities: DBModel | dict[str, Any] | Any | None) -> dict[str, Any]:
    capabilities = model_or_capabilities if isinstance(model_or_capabilities, dict) else _model_capabilities(model_or_capabilities)
    config = capabilities.get(AUTO_ROUTER_CONFIG_KEY)
    return config if isinstance(config, dict) else {}


def _coerce_model_id(value: Any) -> int | None:
    if value in {None, "", 0, "0"}:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def parse_auto_router_decision(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        payload = raw
    else:
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        if "{" in text and "}" in text:
            text = text[text.find("{") : text.rfind("}") + 1]
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            payload = {}

    difficulty = str(payload.get("difficulty") or "medium").strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    task_type = str(payload.get("task_type") or "other").strip().lower()
    allowed_task_types = {"chat", "writing", "coding", "analysis", "research", "vision", "math", "file_generation", "other"}
    if task_type not in allowed_task_types:
        task_type = "other"

    matched_criteria = payload.get("matched_criteria")
    if not isinstance(matched_criteria, list):
        matched_criteria = []
    matched_criteria = [str(item).strip()[:80] for item in matched_criteria if str(item).strip()][:8]

    return {
        "difficulty": difficulty,
        "task_type": task_type,
        "needs_vision": bool(payload.get("needs_vision")),
        "needs_research": bool(payload.get("needs_research")),
        "matched_criteria": matched_criteria,
        "reason": str(payload.get("reason") or "").strip()[:300],
    }


def select_auto_router_target_id(config: dict[str, Any], decision: dict[str, Any]) -> int | None:
    if not isinstance(config, dict):
        return None

    if decision.get("needs_vision"):
        target_id = _coerce_model_id(config.get("vision_model_id"))
        if target_id:
            return target_id

    if decision.get("needs_research"):
        target_id = _coerce_model_id(config.get("research_model_id"))
        if target_id:
            return target_id

    difficulty = str(decision.get("difficulty") or "medium").lower()
    difficulty_key = f"{difficulty}_model_id" if difficulty in {"easy", "medium", "hard"} else "medium_model_id"
    target_id = _coerce_model_id(config.get(difficulty_key))
    if target_id:
        return target_id

    fallback_id = _coerce_model_id(config.get("fallback_model_id"))
    if fallback_id:
        return fallback_id

    for field in AUTO_ROUTER_TARGET_FIELDS:
        target_id = _coerce_model_id(config.get(field))
        if target_id:
            return target_id
    return None


async def validate_auto_router_config(
    db: AsyncSession,
    config: dict[str, Any] | None,
    *,
    current_model_id: int | None = None,
) -> list[str]:
    if not isinstance(config, dict):
        return ["auto_router config is required"]

    errors: list[str] = []
    configured_ids = {
        field: _coerce_model_id(config.get(field))
        for field in AUTO_ROUTER_MODEL_ID_FIELDS
    }

    if not configured_ids["router_model_id"]:
        errors.append("router_model_id is required")

    if not any(configured_ids[field] for field in AUTO_ROUTER_TARGET_FIELDS):
        errors.append("at least one target model is required")

    requested_ids = {model_id for model_id in configured_ids.values() if model_id}
    if current_model_id is not None and current_model_id in requested_ids:
        errors.append("auto router cannot target itself")

    if not requested_ids:
        return errors

    result = await db.execute(
        select(DBModel, Provider)
        .join(Provider, Provider.id == DBModel.provider_id)
        .where(DBModel.id.in_(requested_ids), DBModel.is_active == True, Provider.is_active == True)
    )
    models_by_id = {int(model.id): model for model, _provider in result.all()}

    for field, model_id in configured_ids.items():
        if not model_id:
            continue
        model = models_by_id.get(model_id)
        if model is None or is_auto_router_model(model):
            errors.append(f"{field} must target an active normal model")

    return errors


AUTO_ROUTER_SYSTEM_PROMPT = """
You are a fast routing classifier for JGPTi. Classify the user's latest request so the backend can choose the best model.

Return only valid JSON with these keys:
- difficulty: "easy", "medium", or "hard"
- task_type: "chat", "writing", "coding", "analysis", "research", "vision", "math", "file_generation", or "other"
- needs_vision: boolean
- needs_research: boolean
- matched_criteria: short array of strings
- reason: one short sentence

Use these criteria:
- easy: short factual answer, translation, rewrite, simple explanation, low-risk single-step response.
- medium: multi-step general reasoning, structured writing, moderate analysis, file-aware answer, routine planning.
- hard: complex coding, deep analysis, mathematical derivation, long synthesis, high-accuracy or many-step work.
- needs_vision: image input exists or the user asks to inspect/understand a picture, chart, screenshot, or visual layout.
- needs_research: current events, prices, laws, schedules, product comparisons, source-heavy research, or external factual verification.
- file_generation: user asks to create a PDF, spreadsheet, chart, presentation, document, or other file artifact.
""".strip()


def _stringify_message_content_for_routing(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "").strip().lower()
            if part_type == "text":
                parts.append(str(part.get("text") or ""))
            elif part_type == "image_url":
                parts.append("[image input]")
        return "\n".join(part for part in parts if part)
    return str(content or "")


def build_auto_router_messages(messages: list[dict]) -> list[dict[str, str]]:
    recent = messages[-8:]
    lines: list[str] = []
    for message in recent:
        role = str(message.get("role") or "unknown")
        if role == "system":
            continue
        content = _stringify_message_content_for_routing(message.get("content")).strip()
        if content:
            lines.append(f"{role}: {content[:4000]}")
    if messages_include_image_input(messages):
        lines.append("input_flags: image_input=true")
    payload = "\n\n".join(lines)[-12000:]
    return [
        {"role": "system", "content": AUTO_ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": payload or "Classify an empty user request as easy chat."},
    ]


async def _get_active_normal_provider_model(db: AsyncSession, model_id: int | None) -> tuple[Provider | None, DBModel | None]:
    if not model_id:
        return None, None
    result = await db.execute(
        select(DBModel, Provider)
        .join(Provider, Provider.id == DBModel.provider_id)
        .where(DBModel.id == model_id, DBModel.is_active == True, Provider.is_active == True)
    )
    row = result.first()
    if not row:
        return None, None
    model, provider = row
    if is_auto_router_model(model):
        return None, None
    return provider, model


async def _first_valid_auto_router_target(db: AsyncSession, config: dict[str, Any]) -> tuple[Provider | None, DBModel | None]:
    for field in AUTO_ROUTER_TARGET_FIELDS:
        provider, model = await _get_active_normal_provider_model(db, _coerce_model_id(config.get(field)))
        if provider and model:
            return provider, model
    return None, None


async def resolve_model_for_completion(
    db: AsyncSession,
    *,
    selected_provider: Provider | None,
    selected_model: DBModel | None,
    messages: list[dict],
) -> tuple[Provider | None, DBModel | None, dict[str, Any] | None]:
    if not selected_model or not is_auto_router_model(selected_model):
        return selected_provider, selected_model, None

    config = get_auto_router_config(selected_model)
    router_provider, router_model = await _get_active_normal_provider_model(db, _coerce_model_id(config.get("router_model_id")))
    decision = parse_auto_router_decision({})
    router_error: str | None = None

    router_usage: dict[str, Any] | None = None

    if router_provider and router_model:
        try:
            response = await request_chat_completion(
                router_provider,
                router_model.name,
                build_auto_router_messages(messages),
            )
            response_message = response.get("message") or {}
            decision = parse_auto_router_decision(response_message.get("content") or "")
            router_usage = response.get("usage")
        except Exception as exc:
            router_error = str(exc)[:300]
            logging.getLogger(__name__).warning("Auto router classification failed: %s", exc)
    else:
        router_error = "router_model_id is not an active normal model"

    target_id = select_auto_router_target_id(config, decision)
    target_provider, target_model = await _get_active_normal_provider_model(db, target_id)
    if not target_provider or not target_model:
        target_provider, target_model = await _first_valid_auto_router_target(db, config)

    if not target_provider or not target_model:
        raise LLMProviderError(
            "Auto router has no active target model configured",
            code="auto_router_no_target",
        )

    routing = {
        "selected_model_id": selected_model.id,
        "selected_model_name": selected_model.name,
        "router_model_id": router_model.id if router_model else None,
        "router_model_name": router_model.name if router_model else None,
        "target_model_id": target_model.id,
        "target_model_name": target_model.name,
        "decision": decision,
        "router_error": router_error,
        "router_usage": router_usage,
    }
    return target_provider, target_model, routing


def messages_include_image_input(messages: list[dict]) -> bool:
    """Check if any message includes image or file input parts."""
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            p_type = str(part.get("type") or "").strip().lower()
            if p_type in ("image_url", "file"):
                return True
    return False


_IMAGE_TAG_PATTERN = re.compile(r"\[عکس ارسال شده: ID=(\d+)\]")
_FILE_TAG_PATTERN = re.compile(r"\[فایل: .*? \(ID=(\d+)\)\]")


async def resolve_multimodal_tags_in_messages(
    db: AsyncSession,
    messages: list[dict],
) -> list[dict]:
    """Resolve image and file tags like [عکس ارسال شده: ID=123] or [فایل: test.pdf (ID=123)]
    in messages to base64 format.
    
    Returns a new list of messages with resolved multimodal content.
    """
    from app.models import UploadedFile
    
    resolved = []
    for msg in messages:
        if msg.get("role") != "user" or not isinstance(msg.get("content"), str):
            resolved.append(msg)
            continue
        
        content_str = msg["content"]
        image_matches = list(_IMAGE_TAG_PATTERN.finditer(content_str))
        file_matches = list(_FILE_TAG_PATTERN.finditer(content_str))
        
        if not image_matches and not file_matches:
            resolved.append(msg)
            continue
        
        # Strip all tags from the text
        clean_text = content_str
        clean_text = _IMAGE_TAG_PATTERN.sub("", clean_text)
        clean_text = _FILE_TAG_PATTERN.sub("", clean_text)
        clean_text = clean_text.strip()
        
        content_parts = []
        
        # Combine and sort all matches by position to preserve relative order if needed, 
        # though usually we just append them.
        all_matches = []
        for m in image_matches:
            all_matches.append(("image", m))
        for m in file_matches:
            all_matches.append(("file", m))
        
        # Sort by start position
        all_matches.sort(key=lambda x: x[1].start())

        for kind, match in all_matches:
            file_id = int(match.group(1))
            try:
                uploaded_file = await db.get(UploadedFile, file_id)
                if not uploaded_file or not uploaded_file.storage_path:
                    continue
                
                path = uploaded_file.storage_path
                if not os.path.isabs(path):
                    for base in [".", "backend"]:
                        p = os.path.abspath(os.path.join(base, path))
                        if os.path.exists(p):
                            path = p
                            break
                    else:
                        path = os.path.abspath(path)
                
                if not os.path.exists(path):
                    continue
                
                if os.path.getsize(path) > 50 * 1024 * 1024: # ZAL supports up to 50MB
                    continue
                
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                
                mime = uploaded_file.mime_type or "application/octet-stream"
                filename = uploaded_file.filename or "file"
                
                # Fallback image detection by filename extension when mime_type is missing
                if not uploaded_file.mime_type:
                    lower_name = filename.lower()
                    if lower_name.endswith((".jpg", ".jpeg")):
                        mime = "image/jpeg"
                    elif lower_name.endswith(".png"):
                        mime = "image/png"
                    elif lower_name.endswith(".gif"):
                        mime = "image/gif"
                    elif lower_name.endswith(".webp"):
                        mime = "image/webp"
                
                if kind == "image" or mime.startswith("image/"):
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                        },
                    })
                else:
                    # General file
                    content_parts.append({
                        "type": "file",
                        "file": {
                            "file_data": f"data:{mime};base64,{b64}",
                            "filename": filename,
                        },
                    })
            except Exception:
                continue
        
        if content_parts:
            if clean_text:
                content_parts.insert(0, {"type": "text", "text": clean_text})
            resolved.append({"role": "user", "content": content_parts})
        else:
            resolved.append(msg)
    
    return resolved


async def resolve_image_tags_in_messages(
    db: AsyncSession,
    messages: list[dict],
) -> list[dict]:
    """Legacy wrapper for resolve_multimodal_tags_in_messages."""
    return await resolve_multimodal_tags_in_messages(db, messages)


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def _model_image_support_from_capabilities(capabilities: Any) -> bool | None:
    if not isinstance(capabilities, dict):
        return None
    keys = (
        "image_input",
        "supports_image_input",
        "vision",
        "supports_vision",
        "multimodal_input",
    )
    for key in keys:
        if key not in capabilities:
            continue
        value = _coerce_optional_bool(capabilities.get(key))
        if value is not None:
            return value
    return None


def _infer_image_support_from_model_name(value: str | None) -> bool | None:
    name = (value or "").strip().lower()
    if not name:
        return None

    positive_hints = (
        "vision",
        "image",
        "multimodal",
        "-vl",
        "gpt-4o",
        "omni",
        "claude-3",
        "claude-4",
        "gemini",
        "pixtral",
        "llava",
        "glm-4v",
        "gpt-4-turbo",
        "gpt-5",
        "o1-",
        "o3-",
        "flash",
        "pro",
        "mini",
    )
    if any(hint in name for hint in positive_hints):
        return True

    negative_hints = (
        "text-only",
        "text_only",
        "instruct",
    )
    if any(hint in name for hint in negative_hints):
        return False

    # If it's a known smart model but not explicitly marked, we can't be sure
    return None


def model_supports_image_input(model: DBModel | None, *, infer_from_name: bool = True) -> bool | None:
    if model is None:
        return None
    
    explicit = _model_image_support_from_capabilities(getattr(model, "capabilities", None))
    
    if not infer_from_name:
        return explicit
        
    display_name = getattr(model, "display_name", None)
    name = getattr(model, "name", None)
    inferred = _infer_image_support_from_model_name(display_name) or _infer_image_support_from_model_name(name)
    
    # If explicit says False, we respect that unless inferred says True (fallback for missing caps)
    # But wait, if inferred is True, we definitely want to try vision.
    res = None
    if inferred is True:
        res = True
    elif explicit is not None:
        res = explicit
    else:
        res = inferred
        
    logging.getLogger(__name__).info(f"Vision support check for model {name} (display: {display_name}): explicit={explicit}, inferred={inferred} -> result={res}")
    return res


async def suggest_models_for_input_capability(
    db: AsyncSession,
    *,
    need_image_input: bool,
    exclude_model_id: int | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if not need_image_input:
        return []

    result = await db.execute(
        select(DBModel, Provider)
        .join(Provider, Provider.id == DBModel.provider_id)
        .where(DBModel.is_active == True, Provider.is_active == True)
        .order_by(Provider.name, DBModel.display_name, DBModel.name)
    )
    rows = result.all()
    scored: list[tuple[int, dict[str, Any]]] = []
    for model, provider in rows:
        if exclude_model_id is not None and int(model.id) == int(exclude_model_id):
            continue

        explicit = model_supports_image_input(model, infer_from_name=False)
        inferred = _infer_image_support_from_model_name(model.display_name or model.name)
        if explicit is False:
            continue
        if explicit is not True and inferred is not True:
            continue

        score = 100 if explicit is True else 40
        confidence = "explicit" if explicit is True else "inferred"
        scored.append(
            (
                score,
                {
                    "id": model.id,
                    "name": model.name,
                    "display_name": model.display_name or model.name,
                    "provider_id": provider.id,
                    "provider_name": provider.name,
                    "supports_image_input": True,
                    "confidence": confidence,
                },
            )
        )

    scored.sort(key=lambda item: (-item[0], str(item[1]["provider_name"]).lower(), str(item[1]["display_name"]).lower()))
    return [item[1] for item in scored[: max(1, limit)]]


def _extract_provider_error_fields(payload: Any) -> tuple[str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None

    error_block = payload.get("error")
    if isinstance(error_block, dict):
        message = error_block.get("message") or error_block.get("detail") or error_block.get("error")
        code = error_block.get("code") or error_block.get("type")
        return str(message).strip() if message is not None else None, str(code).strip() if code is not None else None
    if isinstance(error_block, str):
        return error_block.strip() or None, None

    for key in ("message", "detail", "error_message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), None
    return None, None


def _looks_like_unsupported_multimodal_error(
    provider_message: str | None,
    provider_code: str | None,
    *,
    had_multimodal_input: bool,
) -> bool:
    if not had_multimodal_input:
        return False
    haystack = " ".join([provider_message or "", provider_code or ""]).strip().lower()
    if not haystack:
        return False
    hints = (
        "does not support image",
        "doesn't support image",
        "image input is not supported",
        "image_url",
        "vision is not supported",
        "multimodal is not supported",
        "supports text only",
        "input modality image is not supported",
        "input modality file is not supported",
        "unsupported modality",
        "file input is not supported",
    )
    return any(hint in haystack for hint in hints)


async def ensure_builtin_tools(db: AsyncSession):
    for name, definition in BUILTIN_TOOLS.items():
        result = await db.execute(select(Tool).where(Tool.name == name))
        tool = result.scalar_one_or_none()
        if tool:
            changed = False
            for field in ("display_name", "description", "kind", "implementation_key", "implementation_config", "input_schema"):
                value = definition[field]
                if getattr(tool, field) != value:
                    setattr(tool, field, value)
                    changed = True
            if not tool.is_builtin:
                tool.is_builtin = True
                changed = True
            if changed:
                tool.updated_at = datetime.now(timezone.utc)
        else:
            db.add(
                Tool(
                    name=name,
                    display_name=definition["display_name"],
                    description=definition["description"],
                    kind=definition["kind"],
                    implementation_key=definition["implementation_key"],
                    implementation_config=definition["implementation_config"],
                    input_schema=definition["input_schema"],
                    is_active=True,
                    is_builtin=True,
                )
            )
    await db.commit()


async def ensure_builtin_tool_bindings(db: AsyncSession):
    await ensure_builtin_tools(db)
    result = await db.execute(select(Tool).where(Tool.name.in_(list(BUILTIN_TOOLS.keys()))))
    builtin_tools = result.scalars().all()
    for tool in builtin_tools:
        binding_result = await db.execute(select(ToolBinding).where(ToolBinding.tool_id == tool.id))
        existing_bindings = binding_result.scalars().all()
        if existing_bindings:
            continue
        db.add(ToolBinding(tool_id=tool.id, scope_type="global", scope_id=None, is_enabled=True))
    await db.commit()


async def call_llm(provider: Provider, model_name: str, messages: list[dict], stream: bool = False, tools: list[dict] | None = None) -> str:
    response = await request_chat_completion(provider, model_name, messages, stream=stream, tools=tools)
    message = response.get("message") or {}
    return message.get("content") or ""


def _normalize_reasoning_text(value: Any, *, max_length: int = 320) -> str | None:
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return None
    if len(text) > max_length:
        text = f"{text[: max(1, max_length - 3)].rstrip()}..."
    return text


def _dedupe_reasoning_chunks(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        normalized = _normalize_reasoning_text(item)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _extract_reasoning_summary_chunks(value: Any) -> list[str]:
    chunks: list[str] = []
    if isinstance(value, str):
        normalized = _normalize_reasoning_text(value)
        if normalized:
            chunks.append(normalized)
        return chunks

    if isinstance(value, list):
        for item in value[:12]:
            chunks.extend(_extract_reasoning_summary_chunks(item))
        return _dedupe_reasoning_chunks(chunks)

    if not isinstance(value, dict):
        return []

    for key in ("summary", "summary_text", "text", "label", "title"):
        if key in value:
            chunks.extend(_extract_reasoning_summary_chunks(value.get(key)))

    if "parts" in value:
        chunks.extend(_extract_reasoning_summary_chunks(value.get("parts")))
    if "items" in value:
        chunks.extend(_extract_reasoning_summary_chunks(value.get("items")))
    return _dedupe_reasoning_chunks(chunks)


_REASONING_SPLIT_PATTERN = re.compile(
    r"\s*(?:\n+|;|\u2022|\u2023|->|=>|\u2192|\bthen\b|\bnext\b|\bafter that\b|\bfinally\b)\s*",
    flags=re.IGNORECASE,
)
_REASONING_TOPIC_STOPWORDS = {
    "about",
    "across",
    "after",
    "also",
    "because",
    "between",
    "could",
    "first",
    "into",
    "just",
    "many",
    "more",
    "most",
    "next",
    "only",
    "over",
    "some",
    "such",
    "than",
    "that",
    "then",
    "this",
    "through",
    "under",
    "using",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
}


def _split_reasoning_summary_into_stages(summary: str) -> list[str]:
    normalized = _normalize_reasoning_text(summary, max_length=800)
    if not normalized:
        return []
    parts = [part.strip(" -:,.") for part in _REASONING_SPLIT_PATTERN.split(normalized) if part.strip()]
    if len(parts) <= 1:
        return [normalized]
    return _dedupe_reasoning_chunks(parts[:8])


def _reasoning_topic_from_summary(summary: str) -> str:
    normalized = _normalize_reasoning_text(summary, max_length=140)
    if not normalized:
        return "Reasoning"
    if ":" in normalized:
        head, _, _ = normalized.partition(":")
        head_words = [w for w in head.split() if w]
        if 1 <= len(head_words) <= 7:
            return head.strip()

    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-']*", normalized)
    topic_words: list[str] = []
    for word in words:
        lower = word.lower()
        if len(lower) < 3 or lower in _REASONING_TOPIC_STOPWORDS:
            continue
        topic_words.append(word)
        if len(topic_words) >= 6:
            break
    if topic_words:
        return " ".join(topic_words)
    return " ".join(normalized.split()[:6]).strip() or "Reasoning"


def _extract_topics_from_reasoning_content(reasoning_content: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-']*", reasoning_content.lower())
    counts: dict[str, int] = {}
    for word in words:
        if len(word) < 4 or word in _REASONING_TOPIC_STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    if not counts:
        return []
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:4]]


def extract_reasoning_metadata(completion_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(completion_payload, dict):
        return None

    message = completion_payload.get("message")
    raw = completion_payload.get("raw")
    if not isinstance(message, dict):
        message = {}
    if not isinstance(raw, dict):
        raw = {}

    fragments: list[str] = []
    fragments.extend(_extract_reasoning_summary_chunks(message.get("reasoning_summary")))
    fragments.extend(_extract_reasoning_summary_chunks(message.get("thinking_summary")))

    reasoning_block = message.get("reasoning")
    if isinstance(reasoning_block, dict):
        fragments.extend(_extract_reasoning_summary_chunks(reasoning_block.get("summary")))
        fragments.extend(_extract_reasoning_summary_chunks(reasoning_block.get("high_level_summary")))
        fragments.extend(_extract_reasoning_summary_chunks(reasoning_block.get("content_summary")))
    else:
        fragments.extend(_extract_reasoning_summary_chunks(reasoning_block))

    response_output = raw.get("output")
    if isinstance(response_output, list):
        for item in response_output[:12]:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type not in {"reasoning", "reasoning_summary", "thinking"}:
                continue
            fragments.extend(_extract_reasoning_summary_chunks(item.get("summary")))

    fragments = _dedupe_reasoning_chunks(fragments)
    stages: list[str] = []
    if len(fragments) <= 1:
        single = fragments[0] if fragments else ""
        if single:
            stages = _split_reasoning_summary_into_stages(single)
    else:
        stages = fragments[:8]

    if not stages and fragments:
        stages = fragments[:1]

    if not stages:
        raw_reasoning_content = _normalize_reasoning_text(message.get("reasoning_content"), max_length=6000)
        if raw_reasoning_content:
            topics = _extract_topics_from_reasoning_content(raw_reasoning_content)
            if topics:
                stages = [f"Model considered {topic}" for topic in topics]
                fragments = [f"Reasoning covered: {', '.join(topics)}."]
            else:
                stages = ["Model reasoned internally before composing the answer."]
                fragments = stages[:]

    if not stages:
        return None

    stage_items: list[dict[str, Any]] = []
    for index, stage_text in enumerate(stages[:6], start=1):
        normalized_stage = _normalize_reasoning_text(stage_text, max_length=240)
        if not normalized_stage:
            continue
        stage_items.append(
            {
                "index": index,
                "topic": _reasoning_topic_from_summary(normalized_stage),
                "summary": normalized_stage,
            }
        )

    if not stage_items:
        return None

    summary = _normalize_reasoning_text(
        fragments[0] if fragments else "Model reasoned internally before answering.",
        max_length=360,
    ) or "Model reasoned internally before answering."
    return {
        "available": True,
        "summary": summary,
        "stages": stage_items,
    }


def merge_reasoning_metadata(*items: dict[str, Any] | None) -> dict[str, Any] | None:
    valid = [item for item in items if isinstance(item, dict) and item.get("available")]
    if not valid:
        return None

    summaries: list[str] = []
    merged_stages: list[dict[str, Any]] = []
    seen_stage_keys: set[str] = set()

    for item in valid:
        summary = _normalize_reasoning_text(item.get("summary"), max_length=360)
        if summary:
            summaries.append(summary)

        for stage in item.get("stages") or []:
            if not isinstance(stage, dict):
                continue
            stage_summary = _normalize_reasoning_text(stage.get("summary"), max_length=240)
            if not stage_summary:
                continue
            stage_key = stage_summary.lower()
            if stage_key in seen_stage_keys:
                continue
            seen_stage_keys.add(stage_key)
            merged_stages.append(
                {
                    "index": len(merged_stages) + 1,
                    "topic": _reasoning_topic_from_summary(stage.get("topic") or stage_summary),
                    "summary": stage_summary,
                }
            )
            if len(merged_stages) >= 6:
                break
        if len(merged_stages) >= 6:
            break

    if not merged_stages and summaries:
        summary = summaries[0]
        merged_stages = [
            {
                "index": 1,
                "topic": _reasoning_topic_from_summary(summary),
                "summary": summary,
            }
        ]

    if not merged_stages:
        return None

    summary = summaries[0] if summaries else merged_stages[0]["summary"]
    return {
        "available": True,
        "summary": summary,
        "stages": merged_stages,
    }


_CODEX_TOOL_ALIASES = {
    "search_web": "web_search",
    "google_search": "web_search",
    "web_searching": "web_search",
    "image_generation": "image_generator",
    "generate_image": "image_generator",
    "search_documents": "search_project",
    "document_search": "search_project",
    "list_files": "list_project_files",
    "generate_pdf": "pdf_generator",
}

_CODEX_TOOL_ARG_ALIASES = {
    "read_skill": {"name": "skill_name"},
    "read_skill_file": {"name": "skill_name", "path": "relative_path"},
}

_CODEX_TOOL_TEXT_ARGUMENTS = {
    "calculator": "expression",
    "image_generator": "prompt",
    "web_search": "query",
    "pdf_generator": "content",
    "save_user_preference": "preference_text",
    "search_project": "query",
    "search_project_queries": "queries",
    "read_skill": "skill_name",
    "read_skill_file": "skill_name",
    "send_file": "file_path",
}


def _normalize_codex_tool_name(name: Any) -> str:
    raw = str(name or "").strip()
    return _CODEX_TOOL_ALIASES.get(raw, raw)


def _normalize_codex_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        normalized = dict(arguments)
    else:
        normalized = {}
    aliases = _CODEX_TOOL_ARG_ALIASES.get(tool_name) or {}
    for source, target in aliases.items():
        if source in normalized and target not in normalized:
            normalized[target] = normalized.pop(source)
    return normalized


def _find_json_object_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _codex_tool_request_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    candidates = []
    if payload.get("name"):
        candidates.append(payload)
    if isinstance(payload.get("tool_call"), dict):
        candidates.append(payload["tool_call"])
    if isinstance(payload.get("tool_calls"), list):
        candidates.extend(item for item in payload["tool_calls"] if isinstance(item, dict))
    
    # Also support direct tool names as keys, e.g. {"web_search": {"query": "..."}}
    for k, v in payload.items():
        if isinstance(v, dict) and k in BUILTIN_TOOLS and k not in {"tool_call", "tool_calls"}:
            candidates.append({"name": k, "arguments": v})

    requests: list[dict[str, Any]] = []
    for candidate in candidates:
        name = _normalize_codex_tool_name(candidate.get("name"))
        if not name or name not in BUILTIN_TOOLS:
            continue
        arguments = _normalize_codex_tool_arguments(name, candidate.get("arguments"))
        requests.append({"name": name, "arguments": arguments})
    return requests


def _extract_json_codex_tool_requests(content: str) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    search_from = 0
    # Scan for ANY JSON object and check if it contains valid tool calls
    while True:
        start = content.find("{", search_from)
        if start < 0:
            break
        end = _find_json_object_end(content, start)
        if end is None:
            break
        
        try:
            raw_json = content[start:end]
            payload = json.loads(raw_json)
            extracted = _codex_tool_request_from_payload(payload)
            if extracted:
                requests.extend(extracted)
                search_from = end
                continue
        except (ValueError, TypeError):
            pass
        search_from = start + 1
    return requests


def _split_codex_function_args(raw_args: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escape = False
    depth = 0
    for char in raw_args:
        if quote:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
        elif char in "([{":
            depth += 1
            current.append(char)
        elif char in ")]}":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _coerce_codex_function_arg_value(value: str) -> Any:
    raw = value.strip()
    if not raw:
        return ""
    try:
        return json.loads(raw)
    except ValueError:
        pass
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        return raw[1:-1]
    if raw[0] in {"'", '"'}:
        raw = raw[1:]
    if raw.endswith('"') or raw.endswith("'"):
        raw = raw[:-1]
    if raw.endswith("}") and "{" not in raw:
        raw = raw[:-1]
    return raw.strip()


def _parse_codex_function_call(body: str) -> dict[str, Any] | None:
    match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$", body, flags=re.DOTALL)
    if not match:
        return None
    name = _normalize_codex_tool_name(match.group(1))
    arguments: dict[str, Any] = {}
    for part in _split_codex_function_args(match.group(2)):
        key, separator, value = part.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key:
            continue
        arguments[key] = _coerce_codex_function_arg_value(value)
    return {"name": name, "arguments": _normalize_codex_tool_arguments(name, arguments)}


def _extract_markup_codex_tool_requests(content: str) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    # Support attributes like <tool_call Dmitriy>
    matches = list(re.finditer(r"<tool_call(?:\s+[^>]*?)?>", content, flags=re.IGNORECASE))
    for index, match in enumerate(matches):
        body_start = match.end()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body_end = next_start
        # Support malformed closing tags like </tool_call without the trailing >
        for closing in ("</tool_call>", "</arg_value>", "</tool_call"):
            closing_pos = content.find(closing, body_start, next_start)
            if closing_pos >= 0:
                body_end = min(body_end, closing_pos)
        body = content[body_start:body_end].strip()
        if not body:
            continue
            
        # Try JSON parsing first for the body
        try:
            payload = json.loads(body)
            requests.extend(_codex_tool_request_from_payload(payload))
            continue
        except (ValueError, TypeError):
            pass

        parsed = _parse_codex_function_call(body)
        if parsed:
            requests.append(parsed)
    return requests


def _decode_codex_xmlish_text(value: str) -> str:
    text = str(value or "").strip()
    replacements = {
        "&lt;": "<",
        "&gt;": ">",
        "&amp;": "&",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.strip()


def _extract_direct_xml_child_arguments(body: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    for child_match in re.finditer(r"<([A-Za-z_][A-Za-z0-9_]*)\b[^>]*>(.*?)</\1>", body, flags=re.DOTALL):
        key = child_match.group(1).strip()
        value = _decode_codex_xmlish_text(child_match.group(2))
        if key:
            arguments[key] = value
    return arguments


def _direct_xml_tool_arguments(tool_name: str, body: str) -> dict[str, Any]:
    child_arguments = _extract_direct_xml_child_arguments(body)
    if child_arguments:
        return _normalize_codex_tool_arguments(tool_name, child_arguments)
    text = _decode_codex_xmlish_text(body)
    default_arg = _CODEX_TOOL_TEXT_ARGUMENTS.get(tool_name)
    if default_arg and text:
        return _normalize_codex_tool_arguments(tool_name, {default_arg: text})
    return {}


def _extract_direct_xml_codex_tool_requests(content: str) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    ignored_tags = {"tool_call", "tool_calls", "arg_value", "arguments"}
    # Handle both full tags <tool>body</tool> and self-closing <tool arg="val" />
    # First: Full tags
    for match in re.finditer(r"<\s*([A-Za-z_][A-Za-z0-9_]*)\b[^>]*>(.*?)</\s*\1\s*>", content, flags=re.DOTALL | re.IGNORECASE):
        tag_name = match.group(1).strip().lower()
        name = _normalize_codex_tool_name(tag_name)
        if not name or name in ignored_tags:
            continue
        if name not in BUILTIN_TOOLS:
            continue
        arguments = _direct_xml_tool_arguments(name, match.group(2))
        requests.append({"name": name, "arguments": arguments})
    
    # Second: Self-closing tags like <web_search query="..."/>
    # This matches any tag that is not in ignored_tags and is a BUILTIN_TOOL
    for match in re.finditer(r'<\s*([A-Za-z_][A-Za-z0-9_]*)\b\s*([^>]*?)\s*/>', content, flags=re.IGNORECASE):
        tag_name = match.group(1).strip().lower()
        name = _normalize_codex_tool_name(tag_name)
        if not name or name in ignored_tags:
            continue
        if name not in BUILTIN_TOOLS:
            continue
        
        # Extract attributes as arguments
        attr_str = match.group(2)
        arguments = {}
        for attr_match in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"((?:\\.|[^"\\])*)"', attr_str):
            attr_name = attr_match.group(1).strip()
            attr_val = _decode_codex_xmlish_text(attr_match.group(2))
            arguments[attr_name] = attr_val
        
        requests.append({"name": name, "arguments": _normalize_codex_tool_arguments(name, arguments)})
            
    return requests


def _extract_tool_wrapper_codex_tool_requests(content: str) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for match in re.finditer(r"<tool\b[^>]*>(.*?)</tool>", content, flags=re.DOTALL | re.IGNORECASE):
        body = _decode_codex_xmlish_text(match.group(1))
        if not body:
            continue
        try:
            payload = json.loads(body)
        except ValueError:
            parsed = _parse_codex_function_call(body)
            if parsed:
                requests.append(parsed)
            continue
        requests.extend(_codex_tool_request_from_payload(payload))
    return requests


def _extract_self_closing_xml_codex_tool_requests(content: str) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for match in re.finditer(r'<tool_call\s+name="([^"]+)"\s+arguments="((?:\\.|[^"\\])*)"\s*/>', content):
        name = _normalize_codex_tool_name(match.group(1))
        args_raw = match.group(2)
        args_str = args_raw.replace("\\\"", "\"")
        try:
            arguments = json.loads(args_str)
            if name in BUILTIN_TOOLS:
                requests.append({"name": name, "arguments": _normalize_codex_tool_arguments(name, arguments)})
        except ValueError:
            continue
    return requests


def _extract_codex_tool_requests(content: str) -> list[dict[str, Any]]:
    # Decode HTML entities first (e.g. &lt; to <) to handle escaped tags
    text = html.unescape(str(content or ""))
    requests = (
        _extract_json_codex_tool_requests(text)
        + _extract_tool_wrapper_codex_tool_requests(text)
        + _extract_markup_codex_tool_requests(text)
        + _extract_direct_xml_codex_tool_requests(text)
        + _extract_self_closing_xml_codex_tool_requests(text)
    )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for request in requests:
        key = json.dumps(request, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(request)
    return deduped


def _codex_safe_final_reply(reply: str, *, saw_tool_request: bool = False) -> str:
    text = str(reply or "").strip()
    if not text:
        return text
        
    # Strip any leaked raw <tool_call>... blocks from Claude Code since they are internal
    text = re.sub(r'<tool_call(?:\s+[^>]*)?>.*?</tool_call>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Also strip if it's cut off at the end
    text = re.sub(r'<tool_call(?:\s+[^>]*)?>.*$', '', text, flags=re.DOTALL | re.IGNORECASE).strip()

    if saw_tool_request or _extract_codex_tool_requests(text):
        if _extract_codex_tool_requests(text):
            return (
                "⚠️ مدل درخواست اجرای ابزار داد، اما پاسخ نهایی قابل نمایش تولید نکرد. "
                "لطفاً درخواست را دوباره بفرستید یا کمی محدودتر کنید."
            )
    return text


_KNOWN_TOOL_NAMES_RE = (
    r"(?:run_python|calculator|web_search|pdf_generator|image_generator|send_file"
    r"|search_project|search_project_queries|list_project_files|read_skill|read_skill_file|save_user_preference"
    r"|create_excel|create_pdf|create_docx|generate_chart|run_code|execute|bash|terminal)"
)


def sanitize_reply(text: str, *, saw_tool_request: bool = False) -> str:
    """Sanitize model output to remove hallucinated tool call markup and pseudo commands."""
    text = str(text or "").strip()
    if not text:
        return text

    # 1. Strip <tool_call>...</tool_call> (full or partial, cut off at end)
    text = re.sub(r'<tool_call(?:\s+[^>]*)?>.*?</tool_call>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<tool_call(?:\s+[^>]*)?>.*$', '', text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 2. Strip <tool>...</tool> wrapper blocks
    text = re.sub(r'<tool\b[^>]*>.*?</tool>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 3. Strip <system-reminder>...</system-reminder> blocks (internal mode-change messages)
    text = re.sub(r'<system-reminder\b[^>]*>.*?</system-reminder>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 3b. Strip <bash>...</bash> blocks (Codex CLI pseudo-command output)
    text = re.sub(r'<bash\b[^>]*>.*?</bash>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 3c. Strip ```bash ... ``` code blocks that contain only shell commands
    text = re.sub(r'```bash\n.*?```', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
    text = re.sub(r'`` bash\n.*?`', '', text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 4. Strip JSON tool invocation blocks
    text = re.sub(
        r'\{\s*"(?:action|name)"\s*:\s*"[^"]+"\s*,\s*"(?:action_input|arguments|code)"\s*:\s*.*?\}',
        '', text, flags=re.DOTALL
    ).strip()

    # 4. Strip self-closing XML tags for known tool names
    text = re.sub(rf'<{_KNOWN_TOOL_NAMES_RE}\b[^>]*/>', '', text, flags=re.IGNORECASE).strip()

    # 5. Strip full XML tags for known tool names
    text = re.sub(
        rf'<{_KNOWN_TOOL_NAMES_RE}\b[^>]*>.*?</{_KNOWN_TOOL_NAMES_RE}>',
        '', text, flags=re.DOTALL | re.IGNORECASE
    ).strip()

    # 6. Strip standalone pseudo terminal commands that look like execution attempts
    text = re.sub(
        r'(?m)^(?:cd\s+/\S+\s*&&\s*python3?\s+\S+|python3?\s+\S+\.py\b[^\n]*)\s*$',
        '', text
    ).strip()

    # 7. Detect hallucinated file creation claims with internal server paths
    text = re.sub(
        r'[Ff]ile\s+(?:created|saved|generated|is)\s+(?:at|in|to)\s+/(?:home|tmp|var|opt|root)/[^\s]*',
        '', text
    ).strip()

    # 8. Collapse excessive blank lines left behind and clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    text = re.sub(r' {2,}', ' ', text).strip()
    # Remove trailing invisible characters (zero-width spaces, etc.)
    text = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]+$', '', text).strip()

    # 9. If tool requests were seen but nothing meaningful remains, return safe error
    if saw_tool_request and len(text) < 40:
        return (
            "⚠️ مدل درخواست اجرای ابزار داد، اما پاسخ نهایی قابل نمایش تولید نکرد. "
            "لطفاً درخواست را دوباره بفرستید یا کمی محدودتر کنید."
        )

    return text


def transform_messages_for_zal(messages: list[dict]) -> list[dict]:
    """Transform messages to ZAL multimodal format where all attachments use type: 'file'."""
    transformed = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            transformed.append(msg)
            continue
        
        new_content = []
        for part in content:
            if not isinstance(part, dict):
                new_content.append(part)
                continue
            
            p_type = part.get("type")
            if p_type == "image_url":
                new_content.append(part)
            elif p_type == "file":
                new_content.append(part)
            else:
                new_content.append(part)
        
        transformed.append({**msg, "content": new_content})
    return transformed


def cleanup_messages_for_non_multimodal_provider(messages: list[dict]) -> list[dict]:
    """Remove or convert 'file' parts for providers that don't support them."""
    cleaned = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            cleaned.append(msg)
            continue
        
        new_content = []
        for part in content:
            if not isinstance(part, dict):
                new_content.append(part)
                continue
            
            if part.get("type") == "file":
                # Drop file parts or replace with text placeholder
                filename = part.get("file", {}).get("filename", "file")
                new_content.append({"type": "text", "text": f"\n[File attached: {filename} (Content not supported by this provider)]\n"})
            else:
                new_content.append(part)
        
        cleaned.append({**msg, "content": new_content})
    return cleaned


async def request_chat_completion(
    provider: Provider,
    model_name: str,
    messages: list[dict],
    stream: bool = False,
    tools: list[dict] | None = None,
    tool_choice: str | None = None,
    user_id: int | None = None,
    chat_id: int | None = None,
) -> dict[str, Any]:
    if is_codex_subscription_provider(provider):
        return await request_codex_completion(
            provider,
            model_name,
            messages,
            stream=stream,
            tools=tools,
            tool_choice=tool_choice,
            user_id=user_id,
            chat_id=chat_id,
        )

    # Check for ZAL provider
    is_zal = (provider.name or "").lower() == "zal" or (provider.base_url and "1212" in provider.base_url)
    
    if is_zal:
        messages = transform_messages_for_zal(messages)
    else:
        messages = cleanup_messages_for_non_multimodal_provider(messages)

    url = f"{provider.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "stream": stream,
    }
    
    # Auto-enable max_tokens for vision/multimodal if not provided
    if messages_include_image_input(messages) and "max_tokens" not in payload:
        payload["max_tokens"] = 4096
        
    if messages_include_image_input(messages):
        logging.getLogger(__name__).info(f"Sending multimodal request to {model_name} via {provider.name}")

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                "Could not reach the selected model provider",
                code="provider_network_error",
                provider_message=str(exc),
            ) from exc

        if resp.status_code >= 400:
            payload_data = None
            provider_message = None
            provider_code = None
            try:
                payload_data = resp.json()
            except ValueError:
                payload_data = None
            if payload_data is not None:
                provider_message, provider_code = _extract_provider_error_fields(payload_data)
            if not provider_message:
                raw_body = (resp.text or "").strip()
                if len(raw_body) > 500:
                    raw_body = f"{raw_body[:500]}..."
                provider_message = raw_body or f"Provider returned HTTP {resp.status_code}"

            normalized_code = provider_code
            if _looks_like_unsupported_multimodal_error(
                provider_message,
                provider_code,
                had_multimodal_input=messages_include_image_input(messages),
            ):
                normalized_code = "unsupported_image_input"

            raise LLMProviderError(
                provider_message,
                status_code=resp.status_code,
                code=normalized_code or "provider_error",
                provider_message=provider_message,
            )

        try:
            data = resp.json()
            choice = data["choices"][0]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "Provider returned an invalid chat completion payload",
                code="invalid_provider_response",
                provider_message=str(exc),
            ) from exc

        return {
            "message": choice.get("message", {}),
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage"),
            "raw": data,
        }


def _count_non_system_messages(messages: list[dict]) -> int:
    return sum(1 for message in messages if message.get("role") in {"user", "assistant"})


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def _build_codex_messages_with_chat_history(
    db: AsyncSession,
    *,
    chat: Chat | None,
    incoming_messages: list[dict],
    limit: int = 40,
) -> list[dict]:
    if chat is None:
        return list(incoming_messages)

    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    stored_messages = list(reversed(result.scalars().all()))
    if _count_non_system_messages(incoming_messages) >= len(stored_messages):
        return list(incoming_messages)

    rebuilt: list[dict] = []
    for message in incoming_messages:
        if message.get("role") == "system":
            rebuilt.append({"role": "system", "content": message.get("content") or ""})
            break
    rebuilt.extend(
        {"role": message.role, "content": message.content}
        for message in stored_messages
        if message.role in {"user", "assistant"} and message.content
    )
    return rebuilt or list(incoming_messages)


def _xml_tool_usage_example(tool: Tool) -> str:
    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    keys = list(properties.keys())[:3]
    if not keys:
        return f"<{tool.name} />"
    if len(keys) == 1:
        return f'<{tool.name} {keys[0]}="..." />'
    children = "".join(f"<{key}>...</{key}>" for key in keys)
    return f"<{tool.name}>{children}</{tool.name}>"


def _build_codex_custom_tool_guidance(tool_specs: list[dict[str, Any]]) -> str:
    if not tool_specs:
        return (
            "Available custom server tools for this chat: none.\n"
            "Do not claim that server-side PDF, image, file, or web tools are available unless listed here."
        )

    lines = [
        "Available custom server tools for this chat:",
        "When a listed tool is required, output only its XML request tag. The server will execute it and ask you for the final answer with TOOL_RESULT.",
    ]
    for spec in tool_specs[:12]:
        tool = spec["tool"]
        name = _sanitize_tool_prompt_text(tool.name, fallback="tool", limit=64)
        description = _sanitize_tool_prompt_text(tool.description, fallback="No description provided.", limit=120)
        lines.append(f"- {name}: {description}")
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


def _sum_codex_usage(first: dict[str, Any], second: dict[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": _safe_int(first.get("input_tokens")) + _safe_int(second.get("input_tokens")),
        "output_tokens": _safe_int(first.get("output_tokens")) + _safe_int(second.get("output_tokens")),
        "total_tokens": _safe_int(first.get("total_tokens")) + _safe_int(second.get("total_tokens")),
    }


async def _latest_user_message_id(db: AsyncSession, chat_id: int | None) -> int | None:
    if chat_id is None:
        return None
    result = await db.execute(
        select(Message.id)
        .where(Message.chat_id == chat_id, Message.role == "user")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def request_codex_completion(
    provider: Provider,
    model_name: str,
    messages: list[dict],
    stream: bool = False,
    tools: list[dict] | None = None,
    tool_choice: str | None = None,
    user_id: int | None = None,
    chat_id: int | None = None,
) -> dict[str, Any]:
    if stream:
        raise LLMProviderError(
            "Codex subscription provider does not support streaming yet",
            code="codex_streaming_unsupported",
        )

    from app.database import async_session

    async with async_session() as db:
        chat = None
        if chat_id is not None:
            chat = await db.get(Chat, chat_id)

        resolved_user_id = user_id
        if resolved_user_id is None and chat is not None:
            resolved_user_id = chat.user_preference_id
        resolved_user = await db.get(UserPreference, resolved_user_id) if resolved_user_id is not None else None

        if resolved_user_id is not None:
            try:
                selection = await resolve_codex_capacity_selection(db, provider=provider, user_id=resolved_user_id)
            except CodexCapacityError as exc:
                raise LLMProviderError(str(exc), code=exc.code) from exc
            account = selection.account
            if account is None and selection.fallback:
                fallback_provider, fallback_model = await get_provider_for_model(db, int(selection.fallback["model_id"]))
                if not fallback_provider or not fallback_model or is_codex_subscription_provider(fallback_provider):
                    raise LLMProviderError(
                        "Codex capacity fallback model is not executable",
                        code="codex_capacity_fallback_unavailable",
                    )
                fallback_response = await request_chat_completion(
                    fallback_provider,
                    fallback_model.name,
                    messages,
                    stream=stream,
                    tools=tools,
                    tool_choice=tool_choice,
                    user_id=user_id,
                    chat_id=chat_id,
                )
                raw = dict(fallback_response.get("raw") or {})
                raw["codex_capacity_fallback"] = {
                    "pool_id": selection.pool.id if selection.pool else None,
                    "fallback_model_id": fallback_model.id,
                }
                fallback_response["raw"] = raw
                return fallback_response
        else:
            account = await select_codex_account(db, provider)

        if not account:
            raise LLMProviderError(
                "No authenticated Codex account with available capacity is available",
                code="codex_capacity_unavailable",
            )

        # System prompt from DB + dynamic tool guidance
        system_content = await get_effective_system_prompt(db, chat=chat, user=resolved_user)
        tool_specs = await get_chat_tools(db, chat) if chat is not None else []
        
        # Add Codex-specific tool protocol
        codex_tool_protocol = (
            "\n\n### Custom Server Tools Protocol:\n"
            "The server may provide extra custom tools that are not in your native tool list.\n"
            "To use these custom tools, you MUST output an XML tag exactly as shown in the available tool usage examples. "
            "The server will intercept this tag, execute the tool, and return the TOOL_RESULT to you.\n"
            "CRITICAL: Continue using your standard <tool_call>...</tool_call> format for your native bash/file operations. "
            "Do NOT use self-closing tags for native bash, and do NOT use <tool_call> for the custom server tools.\n\n"
            "Anti-hallucination rules for custom server tools:\n"
            "- If a custom server tool is NOT in your available tools list below, you MUST NOT pretend to use it or simulate its output.\n"
            "- NEVER output raw tool call markup (XML tags, JSON blocks, or <tool_call>) in your visible response to the user. "
            "These are internal protocol elements and must never appear in user-facing text.\n"
            "- If you need to create a file (Excel, PDF, Word, etc.) but the tool is not available, say so honestly. "
            "Offer to prepare the content as text that the user can later convert themselves.\n"
            "- If a tool execution fails, report the failure honestly. Do not claim success when the tool returned an error.\n"
            "- Never show internal server paths (like /home/user or /tmp) as download links to the user. "
            "Only share download links or file_ids that the server tool result explicitly provides."
        )
        codex_tool_guidance = _build_codex_custom_tool_guidance(tool_specs)
        system_content = f"{system_content}{codex_tool_protocol}\n\n{codex_tool_guidance}\n\nThe user is interacting via the web interface."

        llm_messages = await _build_codex_messages_with_chat_history(
            db,
            chat=chat,
            incoming_messages=list(messages),
        )
        if not any(m.get("role") == "system" for m in llm_messages):
            llm_messages.insert(0, {"role": "system", "content": system_content})
        else:
            # Update existing system prompt with our protocol
            for m in llm_messages:
                if m.get("role") == "system":
                    m["content"] = f"{m['content']}\n\n{codex_tool_protocol}"
                    break

        # Calculate 'Effective' input tokens (full history) for billing alignment
        # This matches what the user expects to see based on API model comparison.
        effective_input_tokens = sum(len(str(m.get("content") or "")) // 4 + 20 for m in llm_messages)

        # Session resumption logic
        thread_id = chat.codex_thread_id if chat else None
        if thread_id:
            # When resuming, we only send the last user message to avoid duplication
            # but we include context if it was a system prompt change.
            # Usually, just the last user message is enough.
            user_messages = [m for m in llm_messages if m.get("role") == "user"]
            if user_messages:
                prompt = messages_to_codex_prompt([user_messages[-1]])
            else:
                prompt = messages_to_codex_prompt(llm_messages[-1:])
        else:
            prompt = messages_to_codex_prompt([m for m in llm_messages if m.get("role") != "system"])

        if not prompt:
            raise LLMProviderError("Codex request has no text prompt", code="codex_empty_prompt")

        image_files = _extract_images_from_messages(llm_messages)

        try:
            status = await check_codex_login_status(account)
            if not status["is_authenticated"]:
                account.auth_status = status["auth_status"]
                account.last_error = (status.get("stderr") or status.get("stdout") or "Codex account is not authenticated")[:1000]
                await db.commit()
                raise LLMProviderError(
                    "Selected Codex account is not authenticated",
                    code="codex_account_not_authenticated",
                    provider_message=account.last_error,
                )

            # Tool calling loop for Codex
            executed_tool_calls = []
            reply = ""
            current_prompt = prompt
            saw_tool_request = False
            
            # We track the 'cumulative' usage across iterations
            total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            
            for iteration in range(10):
                result = await run_codex_exec(account, model_name, current_prompt, thread_id=thread_id, image_files=image_files if iteration == 0 else None)
                # On subsequent turns of the same chat, run_codex_exec will return the same thread_id
                thread_id = result.get("thread_id") or thread_id
                
                # Update usage
                it_usage = result.get("usage") or {}
                total_usage["input_tokens"] += it_usage.get("input_tokens", 0)
                total_usage["output_tokens"] += it_usage.get("output_tokens", 0)
                total_usage["total_tokens"] += it_usage.get("total_tokens", 0)
                
                content = result["content"]
                reply = content
                
                # Check for tool call in content
                tool_requests = _extract_codex_tool_requests(content)
                if tool_requests:
                    saw_tool_request = True
                    # Process only the first tool request for now to keep it simple, or all of them
                    tool_request = tool_requests[0]
                    tool_name = tool_request.get("name")
                    args = tool_request.get("arguments") or {}
                    
                    # Find tool
                    matching_spec = next((spec for spec in tool_specs if spec["tool"].name == tool_name), None)
                    if matching_spec:
                        tool_record, tool_result = await execute_tool_call(
                            db,
                            tool=matching_spec["tool"],
                            binding_id=matching_spec["binding_id"],
                            chat_id=chat.id if chat else None,
                            message_id=None,
                            provider_name=provider.name,
                            model_name=model_name,
                            external_call_id=f"codex-{uuid.uuid4().hex[:8]}",
                            arguments=args,
                        )
                        executed_tool_calls.append(tool_record)
                        
                        # Send result back to Codex
                        current_prompt = f"TOOL_RESULT ({tool_name}):\n{json.dumps(tool_result, ensure_ascii=False)}"
                        continue # Next iteration to get model response to tool result
                
                # If no tool call or error, we are done
                break

        except LLMProviderError:
            raise
        except Exception as exc:
            if account:
                account.last_error = str(exc)[:1000]
                if "usage limit" in str(exc).lower():
                    account.status = "limited"
                await db.commit()
            raise LLMProviderError(
                "Codex CLI request failed",
                code="codex_cli_error",
                provider_message=str(exc),
            ) from exc

        if account:
            account.auth_status = "authenticated"
            account.last_error = None

            # Override input tokens with 'effective' history tokens if it's higher
            if effective_input_tokens > total_usage["input_tokens"]:
                total_usage["input_tokens"] = effective_input_tokens
                total_usage["total_tokens"] = total_usage["input_tokens"] + total_usage["output_tokens"]

            record_codex_account_usage(account, total_usage)
            account.metadata_json = merge_codex_usage_metadata(account.metadata_json, total_usage, model_name)

            # Save thread_id if new
            if chat_id and thread_id and (not chat or not chat.codex_thread_id):
                await db.execute(update(Chat).where(Chat.id == chat_id).values(codex_thread_id=thread_id))

            await db.commit()

    workspace = build_codex_workspace(account) if account else None
    original_files = set()
    if workspace:
        from pathlib import Path
        wp = Path(workspace)
        if wp.exists():
            for entry in wp.rglob("*"):
                if entry.is_file():
                    original_files.add(str(entry))

    generated_files = []
    if workspace:
        from pathlib import Path
        wp = Path(workspace)
        if wp.exists():
            image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
            doc_exts = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".py", ".html"}
            for entry in wp.rglob("*"):
                if not entry.is_file() or str(entry) in original_files:
                    continue
                ext = entry.suffix.lower()
                if ext not in image_exts and ext not in doc_exts:
                    continue
                file_info = {
                    "path": str(entry),
                    "filename": entry.name,
                    "size": entry.stat().st_size,
                    "type": "image" if ext in image_exts else "document",
                }
                generated_files.append(file_info)

    return {
        "message": {"role": "assistant", "content": sanitize_reply(reply, saw_tool_request=saw_tool_request)},
        "finish_reason": "stop",
        "usage": {
            "usage_source": "codex_cli",
            "input_tokens": total_usage["input_tokens"],
            "output_tokens": total_usage["output_tokens"],
            "total_tokens": total_usage["total_tokens"],
        },
        "tool_calls": [_tool_call_payload(tc) for tc in executed_tool_calls],
        "generated_files": generated_files,
        "raw": {
            "transport": "codex_cli",
            "account_id": account.id if account else None,
            "thread_id": thread_id,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
        },
    }


async def stream_llm(provider: Provider, model_name: str, messages: list[dict]) -> AsyncGenerator[str, None]:
    url = f"{provider.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "stream": True,
    }
    
    # Auto-enable max_tokens for vision if not provided
    if messages_include_image_input(messages) and "max_tokens" not in payload:
        payload["max_tokens"] = 4096

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue


async def get_provider_for_model(db: AsyncSession, model_id: int):
    model_result = await db.execute(
        select(DBModel).where(DBModel.id == model_id, DBModel.is_active == True)
    )
    selected_model = model_result.scalar_one_or_none()
    if selected_model and is_auto_router_model(selected_model):
        return None, selected_model

    result = await db.execute(
        select(DBModel, Provider)
        .join(Provider, Provider.id == DBModel.provider_id)
        .where(DBModel.id == model_id, DBModel.is_active == True, Provider.is_active == True)
    )
    row = result.first()
    if not row:
        return None, None
    model, provider = row
    return provider, model


def _clean_generated_title(raw_title: str) -> str:
    title = (raw_title or "").strip().strip('"').strip("'")
    title = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", title)
    title = re.sub(r"\s*```$", "", title)
    title = re.sub(r"^(title|output)\s*:\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        return "New Chat"
    return title[:80]


async def generate_title(db: AsyncSession, model_id: int, chat_messages: list[dict]) -> str:
    provider, model = await get_provider_for_model(db, model_id)
    if not provider or not model:
        return "New Chat"

    filtered_messages = []
    for message in chat_messages:
        if message.get("role") not in {"user", "assistant"}:
            continue
        content = message.get("content")
        if isinstance(content, list):
            content = str(content)
        filtered_messages.append({"role": message.get("role"), "content": content})

    messages = [{"role": "system", "content": TITLE_GENERATOR_PROMPT}] + filtered_messages[:6]
    try:
        title = await call_llm(provider, model.name, messages)
        return _clean_generated_title(title)
    except Exception:
        return "New Chat"


async def get_default_model(db: AsyncSession) -> tuple:
    result = await db.execute(
        select(DBModel)
        .where(DBModel.is_active == True)
        .order_by(DBModel.is_default.desc(), DBModel.id)
    )
    for model in result.scalars().all():
        if is_auto_router_model(model):
            return None, model
        provider, normal_model = await _get_active_normal_provider_model(db, model.id)
        if provider and normal_model:
            return provider, normal_model
    return None, None


DEFAULT_SYSTEM_PROMPT_TEXT = """
You are دکتر بز, the assistant inside JGPTi.

Core identity:
- You are helpful, clear, concise, and reliable.
- Respond in the same language as the user unless they explicitly ask for another language.
- Keep the answer practical and easy to follow.

Knowledge and Context:
- Today is @today.
- You have access to the following specialized skills:
@skills

Behavior framework:
- First understand the user's real intent, then answer the exact request.
- Prefer direct answers over unnecessary preambles.
- If the request is ambiguous and the ambiguity can change the result, ask a short clarifying question.
- Do not invent facts, sources, actions, tool outputs, or files.
- When you are not sure, say so plainly and ask for the missing detail or use a tool if available.
- IMPORTANT: Act autonomously. Chain enabled tool calls together and deliver the final result without asking for intermediate permissions.

Tool usage rules:
- NEVER output raw tool call markup (like <tool_call>, XML tags, or JSON tool blocks) in your visible response. These are internal protocol elements and must never leak to the user.
- If a tool is not listed in your available tools, you MUST NOT pretend to use it, simulate its output, or claim you executed it. Honestly say the tool is not available.
- If you need to create a file (Excel, PDF, Word, etc.) but have no file-creation tool available, say so honestly and offer to prepare the content as text instead.
- If a tool execution fails, report the failure honestly. Do not claim success when the tool returned an error.
- Never show internal server paths (like /home/user or /tmp) as download links to the user.

Formatting rules:
- Make answers easy to scan in chat.
- Use short paragraphs, bullets, and step-by-step structure when useful.
- Avoid overly dense formatting unless the task requires it.
- NEVER use Markdown tables in your response unless specifically requested by the user. Telegram and Bale do not support tables well. Use lists, bullet points, or bold text for structured data instead.

File creation and sending:
- ALWAYS use the 'send_file' tool to send files to the user.
- If you create, generate, or modify a file that the user requested (like Python scripts, documents, etc.), you MUST use 'send_file' to deliver it to them. Do not just mention that it was created.

Math and hard-to-read notation:
- If the user asks for mathematics, equations, derivations, symbolic expressions, chemistry-style notation, logic notation, or any content that is likely to be hard to read in a chat environment such as Telegram, format the answer clearly in chat text unless an enabled tool explicitly supports a better output format.
- If the content is simple and readable inline, answer normally.
- If the user chooses normal chat, format the result as clearly as possible in plain chat text.

Data charts and graphs:
- If 'run_python' is listed in your available tools, use it for plotting data charts and graphs.
- If 'run_python' is NOT available, do NOT pretend to run code. Instead, describe the chart structure or provide the data in a readable format, and suggest the user request it through an interface that supports code execution.
- NEVER use image generation tools for data charts. Save plots as PNG with clear filenames.
- If charts are intermediate assets for a PDF or report, keep them as files for embedding and do not send them separately in chat unless the user explicitly asks for separate chart files. Final PDF files created by Python should still be delivered to the user.

Interaction tone:
- Be respectful and natural.
- Do not sound robotic.
- Do not over-explain when a shorter answer is enough.

Tools Guidance:
@tools
""".strip()

DEFAULT_CODEX_SYSTEM_PROMPT_TEXT = """
You are دکتر بز, an expert AI assistant.

Core identity:
- You are an expert software engineer: helpful, clear, concise, and reliable.
- Respond in the same language as the user unless they explicitly ask for another language.
- Focus on writing clean, working code and solving technical problems efficiently.

Knowledge and Context:
- Today is @today.
- You have access to the following specialized skills:
@skills

Behavior framework:
- First understand the user's real intent, then deliver the exact solution.
- Prefer direct code and answers over unnecessary preambles.
- If the request is ambiguous and the ambiguity can change the result, ask a short clarifying question.
- Do not invent facts, sources, actions, tool outputs, or files.
- When you are not sure, say so plainly and ask for the missing detail or use a tool if available.
- IMPORTANT: Act autonomously. Chain enabled tool calls together and deliver the final result without asking for intermediate permissions.

Tool usage rules:
- NEVER output raw tool call markup (like <tool_call>, XML tags, or JSON tool blocks) in your visible response to the user. Use the server tool protocol (self-closing XML tags) only for invoking server-side tools.
- If a tool is not listed in your available tools, you MUST NOT pretend to use it, simulate its output, or claim you executed it.
- If you need to create a file but have no file-creation tool available, say so honestly and offer to prepare the content as text instead.
- If a tool execution fails, report the failure honestly. Do not claim success when the tool returned an error.
- Never show internal server paths (like /home/user or /tmp) as download links to the user.

Coding rules:
- Write complete, runnable code. Do not omit important parts.
- Use modern best practices for the requested language or framework.
- ALWAYS use the 'send_file' tool to deliver files (scripts, documents, etc.) to the user.
- If you generate or modify a file, you MUST use 'send_file' to deliver it. Do not just mention that it was created.
- NEVER use image generation tools for data charts.

Math and notation:
- If the user asks for mathematics, equations, derivations, or symbolic expressions, format the answer clearly.
- If an enabled tool supports a better output format, use it.

Formatting rules:
- Make answers easy to scan.
- Use code blocks with correct language tags.
- Use short paragraphs, bullets, and step-by-step structure when useful.
- NEVER use Markdown tables unless specifically requested. Telegram and Bale do not support tables well. Use lists or bold text instead.

Interaction tone:
- Be respectful and natural.
- Do not sound robotic.
- Do not over-explain when shorter code or answer is enough.

Tools Guidance:
@tools
""".strip()
DEFAULT_TOOL_GUIDANCE_STYLE = "compact"
TOOL_GUIDANCE_STYLES = {"compact", "detailed"}
TOOL_GUIDANCE_SAFETY_LINE = (
    "Use tools only when they materially improve correctness. Prefer a direct answer when no tool is required. "
    "Never fabricate tool calls or tool outputs."
)


def _normalize_tool_guidance_style(style: str | None) -> str:
    normalized = (style or "").strip().lower()
    if normalized not in TOOL_GUIDANCE_STYLES:
        return DEFAULT_TOOL_GUIDANCE_STYLE
    return normalized


async def _get_prompt_runtime_settings(
    db: AsyncSession,
    name: str,
    *,
    allowed_skills: list[str] | None = None,
    allowed_tools: list[str] | None = None,
) -> tuple[str, bool, str, str | None]:
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.name == name))
    prompt = result.scalar_one_or_none()
    default_text = DEFAULT_CODEX_SYSTEM_PROMPT_TEXT if name == "codex" else DEFAULT_SYSTEM_PROMPT_TEXT
    if not prompt:
        prompt = SystemPrompt(
            name=name,
            content=default_text,
            is_active=True,
            auto_tool_guidance_enabled=True,
            tool_guidance_style=DEFAULT_TOOL_GUIDANCE_STYLE,
        )
        db.add(prompt)
        await db.commit()
        await db.refresh(prompt)

    if not prompt.is_active:
        return default_text, True, DEFAULT_TOOL_GUIDANCE_STYLE, None

    content = (prompt.content or "").strip() or default_text

    # Resolve placeholders
    content = await PromptService.resolve_prompt(content, db, allowed_skills=allowed_skills, allowed_tools=allowed_tools)

    auto_tool_guidance_enabled = True if prompt.auto_tool_guidance_enabled is None else bool(prompt.auto_tool_guidance_enabled)
    style = _normalize_tool_guidance_style(prompt.tool_guidance_style)
    return content, auto_tool_guidance_enabled, style, prompt.tool_guidance_template


async def get_system_prompt(db: AsyncSession, name: str = "default") -> str:
    content, _, _, _ = await _get_prompt_runtime_settings(db, name)
    return content


def _sanitize_tool_prompt_text(value: str | None, *, fallback: str, limit: int = 160) -> str:
    text = (value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _json_schema_type_label(schema: Any) -> str:
    if not isinstance(schema, dict):
        return "value"
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        filtered = [str(item).strip() for item in raw_type if str(item).strip()]
        value = "/".join(filtered) if filtered else "value"
    elif isinstance(raw_type, str) and raw_type.strip():
        value = raw_type.strip()
    elif isinstance(schema.get("properties"), dict):
        value = "object"
    elif isinstance(schema.get("items"), dict):
        value = "array"
    else:
        value = "value"

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        preview = ", ".join(str(item) for item in enum_values[:3])
        if len(enum_values) > 3:
            preview = f"{preview}, ..."
        return f"{value}; one of: {preview}"
    return value


def _build_tool_usage_from_schema(input_schema: Any) -> str:
    if not isinstance(input_schema, dict):
        return "Pass a JSON object with the tool arguments."
    properties = input_schema.get("properties")
    required = input_schema.get("required")
    required_set = {str(item) for item in required} if isinstance(required, list) else set()
    if not isinstance(properties, dict) or not properties:
        return "Pass a JSON object; this tool has no required input fields."

    rendered_fields: list[str] = []
    for index, (raw_key, field_schema) in enumerate(properties.items()):
        if index >= 6:
            break
        key = _sanitize_tool_prompt_text(str(raw_key), fallback="field", limit=48)
        field_type = _sanitize_tool_prompt_text(_json_schema_type_label(field_schema), fallback="value", limit=80)
        req = "required" if raw_key in required_set else "optional"
        field_description = "No description provided."
        if isinstance(field_schema, dict):
            field_description = _sanitize_tool_prompt_text(
                field_schema.get("description"),
                fallback=field_description,
                limit=120,
            )
        rendered_fields.append(f"{key} ({field_type}, {req}): {field_description}")

    extra_count = max(len(properties) - len(rendered_fields), 0)
    rendered = "; ".join(rendered_fields)
    if extra_count:
        rendered = f"{rendered}; plus {extra_count} additional field(s)"

    suffix = ""
    if input_schema.get("additionalProperties") is False:
        suffix = " Do not include extra keys."
    return f"Provide JSON arguments as: {rendered}.{suffix}"


def _infer_when_to_use_tool(tool: Tool) -> str:
    fingerprint = " ".join([tool.name or "", tool.display_name or "", tool.description or ""]).lower()
    if any(token in fingerprint for token in ("web", "search", "news", "latest", "current", "live", "internet")):
        return "Use when the user needs current or external information that may be outdated in model memory."
    if any(token in fingerprint for token in ("calc", "calculator", "arithmetic", "math", "equation", "expression", "number")):
        return "Use when numeric computation or exact arithmetic is needed."
    if any(token in fingerprint for token in ("weather", "time", "date", "schedule", "calendar")):
        return "Use when the answer depends on a specific time/date or frequently changing status."

    schema = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    required = schema.get("required")
    if isinstance(required, list) and required:
        preview = ", ".join(str(item) for item in required[:2])
        return f"Use when these structured inputs are available and accuracy matters ({preview})."
    return "Use when this tool can return a more reliable result than reasoning alone."


def _render_tool_guidance_template(
    *,
    template: str | None,
    style: str,
    tool_count: int,
    tool_list: str,
) -> str:
    if not template or not template.strip():
        heading = "Available tools for this chat:" if style == "compact" else "Available tools for this chat (detailed guide):"
        return f"{heading}\n{tool_list}\n{TOOL_GUIDANCE_SAFETY_LINE}"

    rendered = template.strip()
    rendered = rendered.replace("{tool_count}", str(tool_count))
    rendered = rendered.replace("{style}", style)
    has_tool_placeholder = "{tool_list}" in rendered
    rendered = rendered.replace("{tool_list}", tool_list)
    if not has_tool_placeholder:
        rendered = f"{rendered}\n{tool_list}"
    if TOOL_GUIDANCE_SAFETY_LINE not in rendered:
        rendered = f"{rendered}\n{TOOL_GUIDANCE_SAFETY_LINE}"
    return rendered


def _build_tool_guidance(
    tool_specs: list[dict[str, Any]],
    *,
    style: str,
    template: str | None,
) -> str:
    if not tool_specs:
        return ""
    entries: list[str] = []
    for spec in tool_specs[:12]:
        tool = spec["tool"]
        tool_name = _sanitize_tool_prompt_text(tool.name, fallback="tool", limit=64)
        tool_label = _sanitize_tool_prompt_text(tool.display_name, fallback=tool_name, limit=64)
        tool_purpose = _sanitize_tool_prompt_text(tool.description, fallback="Use this tool when its purpose clearly matches the task.")
        entries.append(f"- {tool_name} ({tool_label}): {tool_purpose}")
    tool_list = "\n".join(entries)
    return _render_tool_guidance_template(template=template, style=style, tool_count=min(len(tool_specs), 12), tool_list=tool_list)


def _build_learning_preferences_guidance(user: UserPreference | None) -> str:
    # Learning preferences are currently disabled in favor of custom personalization tool.
    return ""


def _build_custom_personalization_guidance(user: UserPreference | None) -> str:
    if not user:
        return ""
    personalization = (getattr(user, "custom_personalization", None) or "").strip()
    if not personalization:
        return ""

    lines = ["Personalization instructions for this user:"]
    lines.append(personalization)
    lines.append("- Apply these instructions to all your responses to this user.")
    lines.append("- If there are conflicting instructions, follow the most recent one.")
    return "\n".join(lines)


async def _build_disabled_tool_guidance(db: AsyncSession) -> str:
    result = await db.execute(select(Tool).where(Tool.is_active == False))
    disabled_tools = result.scalars().all()
    names = sorted(tool.name for tool in disabled_tools if tool.name)
    if not names:
        return ""

    lines = [
        "Disabled tools:",
        "- The following tools are currently disabled and MUST NOT be listed as available capabilities, advertised to the user, or called.",
    ]
    for name in names:
        lines.append(f"- {name}")
    if "pdf_generator" in names:
        lines.append("- PDF generation is currently disabled. Ignore any older PDF policy text in this prompt while it remains disabled.")
    return "\n".join(lines)


async def _get_active_subscription_allowed_skills(
    db: AsyncSession,
    user_preference_id: int | None,
) -> list[str] | None:
    if user_preference_id is None:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        select(UserSubscription)
        .options(selectinload(UserSubscription.plan))
        .where(
            UserSubscription.user_id == user_preference_id,
            UserSubscription.status == "active",
            UserSubscription.expires_at > now,
        )
        .order_by(UserSubscription.expires_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    if sub and sub.plan:
        return sub.plan.allowed_skills_json
    return None


async def _get_active_subscription_allowed_tools(
    db: AsyncSession,
    user_preference_id: int | None,
) -> list[str] | None:
    if user_preference_id is None:
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        select(UserSubscription)
        .options(selectinload(UserSubscription.plan))
        .where(
            UserSubscription.user_id == user_preference_id,
            UserSubscription.status == "active",
            UserSubscription.expires_at > now,
        )
        .order_by(UserSubscription.expires_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    if sub and sub.plan:
        return sub.plan.allowed_tools_json
    return None


async def _get_active_subscription_allowed_skills_for_chat(
    db: AsyncSession,
    chat_id: int | None,
) -> list[str] | None:
    if chat_id is None:
        return None
    chat = await db.get(Chat, chat_id)
    if not chat or not chat.user_preference_id:
        return None
    return await _get_active_subscription_allowed_skills(db, chat.user_preference_id)


async def get_effective_system_prompt(
    db: AsyncSession,
    *,
    chat: Chat | None = None,
    user: UserPreference | None = None,
    name: str = "default",
    include_tool_guidance: bool = True,
) -> str:
    # Determine if we should use the dedicated codex prompt
    is_codex = False
    if chat and chat.model_id:
        model = await db.get(DBModel, chat.model_id)
        if model and model.provider_id:
            provider = await db.get(Provider, model.provider_id)
            if provider and provider.kind == "codex_subscription":
                is_codex = True
                if name == "default":
                    name = "codex"

    user_pref_id = chat.user_preference_id if chat else None
    if user_pref_id is None and user is not None:
        user_pref_id = user.id
    allowed_skills = await _get_active_subscription_allowed_skills(db, user_pref_id)
    allowed_tools = await _get_active_subscription_allowed_tools(db, user_pref_id)
    base_prompt, auto_tool_guidance_enabled, style, template = await _get_prompt_runtime_settings(db, name, allowed_skills=allowed_skills, allowed_tools=allowed_tools)
    sections = [base_prompt]

    if chat and chat.project_id:
        project = await db.get(Project, chat.project_id)
        project_guidance = build_project_instructions_prompt(project)
        if project_guidance:
            sections.append(project_guidance)

    if chat and auto_tool_guidance_enabled and include_tool_guidance:
        # Do not enable automatic JGPTi tool guidance for Codex as requested.
        # We will handle Codex tool definitions separately via the 'codex' system prompt.
        if not is_codex:
            tool_specs = await get_chat_tools(db, chat)
            tool_guidance = _build_tool_guidance(tool_specs, style=style, template=template)
            if tool_guidance:
                sections.append(tool_guidance)

    # Old learning preferences (disabled)
    learning_guidance = _build_learning_preferences_guidance(user)
    if learning_guidance:
        sections.append(learning_guidance)

    # New custom personalization
    custom_personalization_guidance = _build_custom_personalization_guidance(user)
    if custom_personalization_guidance:
        sections.append(custom_personalization_guidance)

    disabled_tool_guidance = await _build_disabled_tool_guidance(db)
    if disabled_tool_guidance:
        sections.append(disabled_tool_guidance)

    return "\n\n".join(section for section in sections if section)


async def get_emb_config(db: AsyncSession, name: str = "default"):
    result = await db.execute(select(EmbeddingConfig).where(EmbeddingConfig.name == name, EmbeddingConfig.is_active == True))
    emb = result.scalar_one_or_none()
    return emb


async def get_transcription_config(db: AsyncSession, name: str = "default"):
    result = await db.execute(
        select(TranscriptionConfig).where(
            TranscriptionConfig.name == name,
            TranscriptionConfig.is_active == True,
        )
    )
    config = result.scalar_one_or_none()
    return config


async def transcribe_audio_with_gemini(
    config: TranscriptionConfig,
    *,
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    prompt: str | None = None,
) -> tuple[str, dict[str, Any]]:
    api_key = (config.api_key or "").strip()
    if not api_key:
        raise ValueError("transcription API key is not configured")
    model = (config.model or "").strip()
    if not model:
        raise ValueError("transcription model is not configured")
    base_url = (config.base_url or "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")
    if not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta"
    prompt_text = (
        prompt
        or "Transcribe this voice message exactly. Return only the transcript text. Keep the same language and punctuation."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text},
                    {
                        "inline_data": {
                            "mime_type": mime_type or "audio/ogg",
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"temperature": 0},
    }

    url = f"{base_url}/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, params={"key": api_key}, json=payload)
        resp.raise_for_status()
        data = resp.json()

    candidates = data.get("candidates") or []
    transcript_parts: list[str] = []
    if candidates:
        content = (candidates[0] or {}).get("content") or {}
        for part in content.get("parts") or []:
            text = part.get("text")
            if text:
                transcript_parts.append(str(text))
    transcript = "\n".join(part.strip() for part in transcript_parts if part.strip()).strip()

    usage_metadata = data.get("usageMetadata") or {}
    usage = {
        "prompt_token_count": int(usage_metadata.get("promptTokenCount") or 0),
        "candidates_token_count": int(usage_metadata.get("candidatesTokenCount") or 0),
        "total_tokens": int(usage_metadata.get("totalTokenCount") or 0),
    }
    return transcript, usage


def _mime_type_to_openrouter_audio_format(mime_type: str | None) -> str:
    mt = (mime_type or "").strip().lower()
    if not mt:
        return "ogg"
    if "/" not in mt:
        return mt
    fmt = mt.split("/", 1)[1]
    if ";" in fmt:
        fmt = fmt.split(";", 1)[0].strip()
    alias_map = {
        "mpeg": "mp3",
        "mpga": "mp3",
        "x-m4a": "m4a",
        "x-wav": "wav",
    }
    return alias_map.get(fmt, fmt or "ogg")


async def transcribe_audio_with_openrouter(
    config: TranscriptionConfig,
    *,
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    prompt: str | None = None,
) -> tuple[str, dict[str, Any]]:
    api_key = (config.api_key or "").strip()
    if not api_key:
        raise ValueError("transcription API key is not configured")
    model = (config.model or "").strip() or "google/chirp-3"
    base_url = (config.base_url or "https://openrouter.ai/api/v1").strip().rstrip("/")
    if not base_url:
        base_url = "https://openrouter.ai/api/v1"
    audio_format = _mime_type_to_openrouter_audio_format(mime_type)
    payload: dict[str, Any] = {
        "model": model,
        "input_audio": {
            "data": base64.b64encode(audio_bytes).decode("ascii"),
            "format": audio_format,
        },
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    transcript = str(data.get("text") or "").strip()
    usage = data.get("usage") or {}
    return transcript, {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


async def transcribe_audio(
    config: TranscriptionConfig,
    *,
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
    prompt: str | None = None,
) -> tuple[str, dict[str, Any]]:
    provider = (config.provider or "google").strip().lower()
    if provider == "openrouter":
        return await transcribe_audio_with_openrouter(
            config,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            prompt=prompt,
        )
    return await transcribe_audio_with_gemini(
        config,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        prompt=prompt,
    )


async def get_chat_tools(db: AsyncSession, chat: Chat) -> list[dict[str, Any]]:
    await ensure_builtin_tool_bindings(db)
    filters = [ToolBinding.scope_type == "global"]
    if chat.project_id is not None:
        filters.append((ToolBinding.scope_type == "project") & (ToolBinding.scope_id == chat.project_id))
    filters.append((ToolBinding.scope_type == "chat") & (ToolBinding.scope_id == chat.id))
    result = await db.execute(
        select(ToolBinding)
        .options(selectinload(ToolBinding.tool))
        .join(ToolBinding.tool)
        .where(ToolBinding.is_enabled == True, Tool.is_active == True, or_(*filters))
        .order_by(ToolBinding.id.desc())
    )
    resolved: dict[str, tuple[ToolBinding, Tool]] = {}
    for binding in result.scalars().all():
        if binding.tool.name not in resolved:
            resolved[binding.tool.name] = (binding, binding.tool)

    # Apply subscription plan tool restrictions (intersection with bindings)
    if chat.user_preference_id is not None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        sub_result = await db.execute(
            select(UserSubscription)
            .options(selectinload(UserSubscription.plan))
            .where(
                UserSubscription.user_id == chat.user_preference_id,
                UserSubscription.status == "active",
                UserSubscription.expires_at > now,
            )
            .order_by(UserSubscription.expires_at.desc())
            .limit(1)
        )
        active_sub = sub_result.scalar_one_or_none()
        if active_sub and active_sub.plan:
            if not active_sub.plan.is_agentic:
                return []
            if active_sub.plan.allowed_tools_json is not None:
                allowed = set(active_sub.plan.allowed_tools_json)
                resolved = {
                    name: pair for name, pair in resolved.items() if name in allowed
                }

    return [
        {
            "binding_id": binding.id,
            "tool": tool,
            "openai": {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            },
        }
        for binding, tool in resolved.values()
    ]


async def run_save_user_preference_tool(db: AsyncSession, chat_id: int, arguments: dict[str, Any]) -> dict[str, Any]:
    preference_text = (arguments or {}).get("preference_text")
    if not isinstance(preference_text, str) or not preference_text.strip():
        raise CalculatorError("preference_text is required")

    if not chat_id:
        return {"ok": False, "error": "Chat ID is required to save preferences."}

    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat or not chat.user_preference_id:
        return {"ok": False, "error": "User context not found for this chat."}

    user = await db.get(UserPreference, chat.user_preference_id)
    if not user:
        return {"ok": False, "error": "User not found."}

    current = (user.custom_personalization or "").strip()
    if current:
        new_personalization = f"{current}\n- {preference_text.strip()}"
    else:
        new_personalization = f"- {preference_text.strip()}"

    user.custom_personalization = new_personalization
    await db.commit()
    await db.refresh(user)

    return {"ok": True, "saved_preference": preference_text.strip()}


async def run_search_project_tool(db: AsyncSession, chat_id: int, arguments: dict[str, Any]) -> dict[str, Any]:
    """Search the project's indexed documents for relevant content."""
    query = (arguments or {}).get("query")
    n_results = (arguments or {}).get("n_results", 5)
    if not isinstance(query, str) or not query.strip():
        raise CalculatorError("query is required")

    if not chat_id:
        return {"ok": False, "error": "Chat ID is required for project search."}

    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat or not chat.project_id:
        return {"ok": False, "error": "This tool can only be used within a project."}

    from app.rag import search_documents
    emb = await get_emb_config(db)

    # Run search (blocking call inside a thread if needed, but search_documents is sync)
    results = await asyncio.to_thread(
        search_documents,
        project_id=chat.project_id,
        query=query,
        n_results=n_results,
        api_key=emb.api_key if emb else None,
        model=emb.model if emb else None,
        provider=emb.provider if emb else "google",
        base_url=emb.base_url if emb else None
    )

    return {"ok": True, "results": results}


async def run_search_project_queries_tool(db: AsyncSession, chat_id: int, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run multiple semantic searches against the project's knowledge base at once."""
    queries = (arguments or {}).get("queries")
    n_results = (arguments or {}).get("n_results", 5)
    if not isinstance(queries, list) or not queries:
        return {"ok": False, "error": "queries must be a non-empty list of search strings."}

    if not chat_id:
        return {"ok": False, "error": "Chat ID is required for project search."}

    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat or not chat.project_id:
        return {"ok": False, "error": "This tool can only be used within a project."}

    from app.rag import search_documents
    emb = await get_emb_config(db)

    tasks = []
    for q in queries[:5]:
        if isinstance(q, str) and q.strip():
            tasks.append(asyncio.to_thread(
                search_documents,
                project_id=chat.project_id,
                query=q.strip(),
                n_results=n_results,
                api_key=emb.api_key if emb else None,
                model=emb.model if emb else None,
                provider=emb.provider if emb else "google",
                base_url=emb.base_url if emb else None,
            ))

    if not tasks:
        return {"ok": False, "error": "No valid queries provided."}

    all_results = await asyncio.gather(*tasks)
    combined = []
    seen_content = set()
    for query_results in all_results:
        for item in query_results:
            content_key = item.get("content", "")[:200]
            if content_key not in seen_content:
                seen_content.add(content_key)
                combined.append(item)

    return {"ok": True, "results": combined, "queries_run": len(tasks)}


async def run_image_generator_tool(db: AsyncSession, chat_id: int | None, arguments: dict[str, Any]) -> dict[str, Any]:
    prompt = arguments.get("prompt")
    if not prompt:
        return {"error": "prompt is required"}
    
    from app.config import OPENROUTER_API_KEY
    if not OPENROUTER_API_KEY:
        return {"error": "OPENROUTER_API_KEY is not configured in the environment variables (.env). Please set it to use this tool."}
    
    # Charge user 50% more than base cost (e.g. base = $0.04 -> charge = $0.06)
    if chat_id:
        from app.models import Chat
        chat = await db.get(Chat, chat_id)
        if chat and chat.user_preference_id:
            from app.services.wallet_service import debit_usd, get_user as get_wallet_user
            user = await get_wallet_user(db, chat.user_preference_id)
            if user:
                base_cost = 0.04
                total_charge = base_cost * 1.5
                wallet_result = await debit_usd(db, user=user, amount_usd=total_charge, entry_type="image_generation", reason="Image generation via OpenRouter", commit=True)
                if not wallet_result.ok:
                    return {"error": "موجودی حساب شما برای ساخت این عکس کافی نیست. لطفاً حساب خود را شارژ کنید."}

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://jgpti.local",
        "X-Title": "JGPTi",
    }
    payload = {
        "model": "google/gemini-3-pro-image-preview",
        "messages": [{"role": "user", "content": prompt}],
    }
    
    import httpx
    import base64
    import os
    import time
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            
            # The image could be in content, or in an images array
            choices = data.get("choices", [])
            if not choices:
                return {"error": "No response choices from OpenRouter."}
                
            msg = choices[0].get("message", {})
            reply_content = msg.get("content") or ""
            images = msg.get("images", [])
            
            saved_image_paths = []
            markdown_parts = []
            if reply_content:
                markdown_parts.append(reply_content)
                
            os.makedirs("./uploads/generated_images", exist_ok=True)
            
            for img_idx, img_obj in enumerate(images):
                img_url = img_obj.get("image_url", {}).get("url", "")
                if img_url.startswith("data:image/"):
                    # Add to markdown using data URI so web frontend can render it directly
                    markdown_parts.append(f"![Generated Image {img_idx + 1}]({img_url})")
                    try:
                        header, b64data = img_url.split(",", 1)
                        img_bytes = base64.b64decode(b64data)
                        ext = header.split(";")[0].split("/")[-1]
                        filename = f"gen_img_{int(time.time())}_{img_idx}.{ext}"
                        filepath = os.path.abspath(f"./uploads/generated_images/{filename}")
                        with open(filepath, "wb") as f:
                            f.write(img_bytes)
                        saved_image_paths.append(filepath)
                    except Exception as e:
                        print(f"Error parsing image base64: {e}")
            
            final_markdown = "\\n\\n".join(markdown_parts)
            return {
                "ok": True,
                "saved_image_paths": saved_image_paths,
                "text_content": reply_content,
                "markdown": final_markdown
            }
        except httpx.HTTPStatusError as e:
            return {"error": f"OpenRouter API returned HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": f"Failed to call OpenRouter API: {str(e)}"}

async def run_list_project_files_tool(db: AsyncSession, chat_id: int, arguments: dict[str, Any]) -> dict[str, Any]:
    """List all files in the current project."""
    if not chat_id:
        return {"ok": False, "error": "Chat ID is required for listing files."}

    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    chat = result.scalar_one_or_none()
    if not chat or not chat.project_id:
        return {"ok": False, "error": "This tool can only be used within a project."}

    result = await db.execute(select(Document).where(Document.project_id == chat.project_id))
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
    return {"ok": True, "files": files}


async def run_read_skill_tool(db: AsyncSession, arguments: dict[str, Any]) -> dict[str, Any]:
    skill_name = (arguments.get("skill_name") or "").strip()
    if not skill_name:
        return {"ok": False, "error": "skill_name is required"}

    result = await db.execute(select(Skill).where(Skill.name == skill_name, Skill.is_active == True))
    skill = result.scalar_one_or_none()
    if not skill:
        return {"ok": False, "error": f"Skill '{skill_name}' not found or is disabled."}

    from app.admin_skills_routes import list_skill_files

    return {
        "ok": True,
        "name": skill.name,
        "description": skill.description,
        "directory": skill.file_path,
        "files": list_skill_files(skill.file_path),
        "instructions": skill.instructions,
        "how_to_read_supporting_files": "Call read_skill_file with this skill_name and a relative_path from the files list.",
    }


async def run_read_skill_file_tool(db: AsyncSession, arguments: dict[str, Any]) -> dict[str, Any]:
    skill_name = (arguments.get("skill_name") or "").strip()
    relative_path = (arguments.get("relative_path") or "").strip()
    if not skill_name or not relative_path:
        return {"ok": False, "error": "skill_name and relative_path are required"}

    result = await db.execute(select(Skill).where(Skill.name == skill_name, Skill.is_active == True))
    skill = result.scalar_one_or_none()
    if not skill or not skill.file_path:
        return {"ok": False, "error": f"Skill '{skill_name}' not found, disabled, or has no directory."}

    root = os.path.abspath(skill.file_path)
    requested = os.path.abspath(os.path.join(root, relative_path))
    if os.path.commonpath([root, requested]) != root or not os.path.isfile(requested):
        return {"ok": False, "error": "File not found or path is outside the skill directory."}

    if os.path.getsize(requested) > 200_000:
        return {"ok": False, "error": "File is too large to read through this tool."}

    try:
        with open(requested, "r", encoding="utf-8") as handle:
            content = handle.read()
    except UnicodeDecodeError:
        return {"ok": False, "error": "File is not UTF-8 text and cannot be read through this tool."}
    except Exception as exc:
        return {"ok": False, "error": f"Error reading skill file: {exc}"}

    return {"ok": True, "skill_name": skill.name, "relative_path": relative_path, "content": content}


async def run_send_file_tool(db: AsyncSession, chat_id: int | None, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.agent.tools import send_file
    import json
    import os
    from pathlib import Path
    from app.models import Chat, Provider

    file_path = arguments.get("file_path", "")

    # Try to resolve relative path against Codex home if applicable
    if chat_id and file_path and not os.path.isabs(file_path):
        chat = await db.get(Chat, chat_id)
        if chat and chat.model_id:
            from app.models import Model as DBModel
            model = await db.get(DBModel, chat.model_id)
            if model and model.provider_id:
                provider = await db.get(Provider, model.provider_id)
                if provider and provider.kind == "codex_subscription":
                    from app.services.codex_runtime import get_codex_account_for_provider
                    user_id = None
                    if chat.user_preference_id:
                        from app.models import UserPreference
                        up = await db.get(UserPreference, chat.user_preference_id)
                        user_id = up.user_id if up else None
                    
                    account = await get_codex_account_for_provider(db, provider, user_id=user_id)
                    if account and account.codex_home:
                        codex_file = os.path.join(account.codex_home, file_path)
                        if os.path.isfile(codex_file):
                            arguments["file_path"] = codex_file

    res_str = await asyncio.to_thread(send_file.run, arguments)
    try:
        return json.loads(res_str)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "output": res_str}


async def run_chart_generator_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.agent.tools import chart_generator
    import json

    res_str = await asyncio.to_thread(chart_generator.run, arguments)
    try:
        return json.loads(res_str)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "output": res_str}


async def execute_tool_call(
    db: AsyncSession,
    *,
    tool: Tool,
    binding_id: int | None,
    chat_id: int | None,
    message_id: int | None,
    provider_name: str | None,
    model_name: str | None,
    external_call_id: str | None,
    arguments: dict[str, Any],
) -> tuple[ToolCall, dict[str, Any]]:
    tool_call = ToolCall(
        tool_id=tool.id,
        binding_id=binding_id,
        chat_id=chat_id,
        message_id=message_id,
        provider_name=provider_name,
        model_name=model_name,
        external_call_id=external_call_id,
        arguments=arguments,
        status="pending",
    )
    db.add(tool_call)
    await db.commit()
    await db.refresh(tool_call)

    try:
        if tool.implementation_key == "builtin:calculator":
            result = run_calculator_tool(arguments)
        elif tool.implementation_key == "builtin:web_search":
            result = await run_web_search_tool(db, arguments)
        elif tool.implementation_key == "builtin:pdf_generator":
            result = await run_pdf_generator_tool(arguments)
        elif tool.implementation_key == "builtin:image_generator":
            result = await run_image_generator_tool(db, chat_id, arguments)
        elif tool.implementation_key == "builtin:save_user_preference":
            result = await run_save_user_preference_tool(db, chat_id, arguments)
        elif tool.implementation_key == "builtin:search_project":
            result = await run_search_project_tool(db, chat_id, arguments)
        elif tool.implementation_key == "builtin:search_project_queries":
            result = await run_search_project_queries_tool(db, chat_id, arguments)
        elif tool.implementation_key == "builtin:list_project_files":
            result = await run_list_project_files_tool(db, chat_id, arguments)
        elif tool.implementation_key == "builtin:read_skill":
            skill_name = (arguments.get("skill_name") or "").strip()
            allowed = await _get_active_subscription_allowed_skills_for_chat(db, chat_id)
            if allowed is not None and skill_name not in allowed:
                result = {"ok": False, "error": f"Skill '{skill_name}' is not available in your current subscription plan."}
            else:
                result = await run_read_skill_tool(db, arguments)
        elif tool.implementation_key == "builtin:read_skill_file":
            skill_name = (arguments.get("skill_name") or "").strip()
            allowed = await _get_active_subscription_allowed_skills_for_chat(db, chat_id)
            if allowed is not None and skill_name not in allowed:
                result = {"ok": False, "error": f"Skill '{skill_name}' is not available in your current subscription plan."}
            else:
                result = await run_read_skill_file_tool(db, arguments)
        elif tool.implementation_key == "builtin:send_file":
            result = await run_send_file_tool(db, chat_id, arguments)
        elif tool.implementation_key == "builtin:chart_generator":
            result = await run_chart_generator_tool(arguments)
        elif (tool.kind or "").strip().lower() == "http":
            try:
                result = await run_http_tool(arguments, tool)
            except httpx.HTTPStatusError as exc:
                response = exc.response
                error_message = f"HTTP tool request failed with status {response.status_code}"
                tool_call.status = "failed"
                tool_call.error = error_message
                tool_call.result = {
                    "status_code": response.status_code,
                    "response_text": response.text[:4000],
                }
                tool_call.completed_at = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(tool_call)
                return tool_call, tool_call.result or {"error": error_message}
            except httpx.RequestError as exc:
                error_message = f"HTTP tool request error: {exc}"
                tool_call.status = "failed"
                tool_call.error = error_message
                tool_call.result = {"error": str(exc)}
                tool_call.completed_at = datetime.now(timezone.utc)
                await db.commit()
                await db.refresh(tool_call)
                return tool_call, tool_call.result or {"error": error_message}
        else:
            raise CalculatorError("Tool implementation is not available")
        tool_call.status = "completed"
        tool_call.result = result
        tool_call.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(tool_call)
        return tool_call, result
    except Exception as exc:
        tool_call.status = "failed"
        tool_call.error = str(exc)
        tool_call.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(tool_call)
        raise


def _normalize_http_tool_config(tool: Tool) -> dict[str, Any]:
    raw_config = tool.implementation_config
    if not isinstance(raw_config, dict):
        raise CalculatorError("HTTP tool implementation_config must be an object")

    method = str(raw_config.get("method") or "GET").strip().upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise CalculatorError("HTTP tool method must be one of GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS")

    url = str(raw_config.get("url") or "").strip()
    if not url:
        raise CalculatorError("HTTP tool url is required")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise CalculatorError("HTTP tool url must start with http:// or https://")

    raw_headers = raw_config.get("headers")
    if raw_headers is None:
        headers: dict[str, str] = {}
    elif isinstance(raw_headers, dict):
        headers = {}
        for key, value in raw_headers.items():
            normalized_key = str(key or "").strip()
            if not normalized_key or value is None:
                continue
            headers[normalized_key] = str(value)
    else:
        raise CalculatorError("HTTP tool headers must be an object")

    timeout = raw_config.get("timeout_seconds")
    if timeout is None:
        timeout_value = 30.0
    else:
        try:
            timeout_value = float(timeout)
        except (TypeError, ValueError):
            raise CalculatorError("HTTP tool timeout_seconds must be numeric")
        if timeout_value <= 0 or timeout_value > 120:
            raise CalculatorError("HTTP tool timeout_seconds must be between 0 and 120")

    return {"method": method, "url": url, "headers": headers, "timeout_seconds": timeout_value}


def _inject_http_path_params(url_template: str, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    used_keys: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in arguments:
            raise CalculatorError(f"Missing required URL path parameter: {key}")
        value = arguments[key]
        if value is None:
            raise CalculatorError(f"URL path parameter cannot be null: {key}")
        used_keys.add(key)
        return quote(str(value), safe="")

    rendered_url = re.sub(r"\{([a-zA-Z0-9_]+)\}", _replace, url_template)
    remaining = {key: value for key, value in arguments.items() if key not in used_keys}
    return rendered_url, remaining


def _normalize_tool_arguments(arguments: Any) -> dict[str, Any]:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    raise CalculatorError("Tool arguments must be a JSON object")


def _coerce_json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_coerce_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce_json_safe(item) for key, item in value.items()}
    return str(value)


async def run_http_tool(arguments: dict[str, Any], tool: Tool) -> dict[str, Any]:
    normalized_arguments = _normalize_tool_arguments(arguments)
    config = _normalize_http_tool_config(tool)
    method = config["method"]
    url_template = config["url"]
    headers = config["headers"]
    timeout_seconds = config["timeout_seconds"]

    url, remaining_arguments = _inject_http_path_params(url_template, normalized_arguments)
    request_kwargs: dict[str, Any] = {"headers": headers}
    if method in {"GET", "DELETE", "HEAD", "OPTIONS"}:
        request_kwargs["params"] = remaining_arguments
    else:
        request_kwargs["json"] = remaining_arguments

    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        response = await client.request(method, url, **request_kwargs)
        response.raise_for_status()

    response_payload: Any
    try:
        response_payload = response.json()
    except ValueError:
        response_payload = {"text": response.text[:4000]}

    return {
        "method": method,
        "url": str(response.request.url),
        "status_code": response.status_code,
        "response": _coerce_json_safe(response_payload),
    }


def run_calculator_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    expression = (arguments or {}).get("expression")
    if not isinstance(expression, str) or not expression.strip():
        raise CalculatorError("expression is required")
    if len(expression) > 200:
        raise CalculatorError("expression is too long")
    tree = ast.parse(expression, mode="eval")
    value = SafeCalculatorEvaluator().visit(tree)
    if isinstance(value, float):
        rendered = format(value, ".12g")
    else:
        rendered = str(value)
    return {"expression": expression, "result": rendered}


def _sanitize_pdf_filename(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CalculatorError("output_filename must be a string")
    normalized = value.strip()
    if not normalized:
        return None
    normalized = os.path.basename(normalized).replace("\\", "")
    normalized = PDF_FILENAME_SAFE_RE.sub("_", normalized)
    normalized = normalized.strip("._")
    if not normalized:
        return None
    if not normalized.lower().endswith(".pdf"):
        normalized = f"{normalized}.pdf"
    if len(normalized) > 80:
        stem, ext = os.path.splitext(normalized)
        normalized = f"{stem[: max(1, 80 - len(ext))]}{ext}"
    return normalized


def _escape_latex_text(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "%": r"\%",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in value)


def _build_pdf_body_document(content: str, *, rtl: bool, title: str | None) -> str:
    title_block = ""
    if title:
        normalized_title = " ".join(title.strip().split())[:200]
        if normalized_title:
            title_block = (
                "\\begin{center}\n"
                f"\\Large\\textbf{{{_escape_latex_text(normalized_title)}}}\n"
                "\\end{center}\n"
                "\\vspace{1em}\n"
            )

    rtl_begin = "\\begin{RTL}\n" if rtl else ""
    rtl_end = "\n\\end{RTL}\n" if rtl else "\n"
    return (
        "\\documentclass[12pt]{article}\n"
        "\\usepackage[a4paper,margin=2.2cm]{geometry}\n"
        "\\usepackage{amsmath,amssymb,mathtools,amsthm}\n"
        "\\usepackage{fontspec}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage{longtable}\n"
        "\\usepackage{booktabs}\n"
        "\\usepackage{hyperref}\n"
        "\\usepackage{xepersian}\n"
        "\\settextfont{Vazirmatn-Regular.ttf}\n"
        "\\setdigitfont{Vazirmatn-Regular.ttf}\n"
        "\\setlatintextfont{TeX Gyre Termes}\n"
        "\\setlength{\\parskip}{0.5em}\n"
        "\\setlength{\\parindent}{0pt}\n"
        "\\begin{document}\n"
        f"{title_block}{rtl_begin}{content}{rtl_end}"
        "\\end{document}\n"
    )


def _escape_text_segment_for_latex_body(value: str) -> str:
    def _escape_text_with_markdown_bold(line: str) -> str:
        token_re = re.compile(r"(\*\*.+?\*\*|__.+?__)")
        cursor = 0
        pieces: list[str] = []
        for match in token_re.finditer(line):
            start, end = match.span()
            if start > cursor:
                pieces.append(_escape_latex_text(line[cursor:start]))
            token = match.group(0)
            inner = token[2:-2]
            pieces.append(f"\\textbf{{{_escape_latex_text(inner)}}}")
            cursor = end
        if cursor < len(line):
            pieces.append(_escape_latex_text(line[cursor:]))
        if not pieces:
            return _escape_latex_text(line)
        return "".join(pieces)

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = normalized.split("\n\n")
    rendered_paragraphs: list[str] = []
    for paragraph in paragraphs:
        lines = paragraph.split("\n")
        escaped_lines = [_escape_text_with_markdown_bold(line) for line in lines]
        rendered_paragraphs.append("\\\\\n".join(escaped_lines))
    return "\n\n\\par\n".join(rendered_paragraphs)


def _convert_markdown_bold_outside_math(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"(\$\$.*?\$\$|\$.*?\$)", normalized, flags=re.DOTALL)
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        if (
            (part.startswith("$$") and part.endswith("$$") and len(part) >= 4)
            or (part.startswith("$") and part.endswith("$") and len(part) >= 2)
        ):
            rendered.append(part)
            continue
        
        # Convert Markdown images to LaTeX
        # ![alt](path) -> \begin{center}\includegraphics[max width=\textwidth]{path}\end{center}
        converted = re.sub(
            r"!\[.*?\]\((.*?)\)", 
            lambda m: f"\\begin{{center}}\\includegraphics[width=0.8\\textwidth]{{{os.path.basename(m.group(1))}}}\\end{{center}}", 
            part, 
            flags=re.DOTALL
        )
        
        # Split by bold markers to escape text outside them
        bold_parts = re.split(r"(\*\*.*?\*\*|__.*?__)", converted, flags=re.DOTALL)
        final_pieces = []
        for bp in bold_parts:
            if (bp.startswith("**") and bp.endswith("**")) or (bp.startswith("__") and bp.endswith("__")):
                inner = bp[2:-2]
                final_pieces.append(f"\\textbf{{{_escape_latex_text(inner)}}}")
            else:
                final_pieces.append(_escape_latex_text(bp))
        
        rendered.append("".join(final_pieces))
    return "".join(rendered)


def _coerce_body_content_to_safe_latex(content: str) -> str:
    # Preserve inline/display math ($...$, $$...$$) and escape the rest as plain text.
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"(\$\$.*?\$\$|\$.*?\$)", normalized, flags=re.DOTALL)
    rendered_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if (
            (part.startswith("$$") and part.endswith("$$") and len(part) >= 4)
            or (part.startswith("$") and part.endswith("$") and len(part) >= 2)
        ):
            rendered_parts.append(part)
            continue
        rendered_parts.append(_escape_text_segment_for_latex_body(part))
    return "".join(rendered_parts)


def _build_pdf_output_filename(requested_name: str | None) -> str:
    if requested_name:
        candidate = requested_name
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        candidate = f"jgpti-pdf-{timestamp}.pdf"
    sanitized = _sanitize_pdf_filename(candidate)
    if not sanitized:
        raise CalculatorError("Could not build a valid output filename")

    final_path = os.path.join(PDF_GENERATOR_OUTPUT_DIR, sanitized)
    if not os.path.exists(final_path):
        return sanitized

    stem, ext = os.path.splitext(sanitized)
    suffix = uuid.uuid4().hex[:8]
    return f"{stem}-{suffix}{ext}"


def _latex_log_excerpt(log_text: str, max_chars: int = 2400) -> str:
    normalized = (log_text or "").strip()
    if not normalized:
        return ""
    if len(normalized) <= max_chars:
        return normalized
    return normalized[-max_chars:]


def _cleanup_expired_generated_pdfs(*, now: datetime | None = None) -> int:
    if not os.path.isdir(PDF_GENERATOR_OUTPUT_DIR):
        return 0
    current_time = now or datetime.now(timezone.utc)
    deleted_count = 0
    try:
        entries = os.listdir(PDF_GENERATOR_OUTPUT_DIR)
    except OSError:
        return 0
    for entry in entries:
        if not entry.lower().endswith(".pdf"):
            continue
        path = os.path.join(PDF_GENERATOR_OUTPUT_DIR, entry)
        if not os.path.isfile(path):
            continue
        try:
            modified_at = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
            age_seconds = (current_time - modified_at).total_seconds()
            if age_seconds >= PDF_GENERATOR_TTL_SECONDS:
                os.remove(path)
                deleted_count += 1
        except OSError:
            continue
    return deleted_count


def _pdf_is_xelatex_ready() -> tuple[bool, str | None]:
    xelatex_binary = shutil.which("xelatex")
    if not xelatex_binary:
        return False, "XeLaTeX is not installed"
    if not os.path.isfile(PDF_GENERATOR_FONT_PATH):
        return False, f"Vazirmatn font is missing at {PDF_GENERATOR_FONT_PATH}"
    return True, None


def _escape_pdf_literal(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in escaped)


def _fallback_plain_text_from_latex(content: str, *, latex_mode: str) -> str:
    if latex_mode == "full_document":
        # Keep full source as plain text fallback to avoid unsafe ad-hoc LaTeX parsing.
        return content
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^}]*)\})?", lambda m: m.group(1) or "", normalized)
    normalized = normalized.replace("{", "").replace("}", "")
    return normalized


def _wrap_pdf_text_line(line: str, max_chars: int) -> list[str]:
    if not line:
        return [""]
    chunks: list[str] = []
    current = ""
    for word in line.split(" "):
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(word) <= max_chars:
            current = word
            continue
        start = 0
        while start < len(word):
            chunks.append(word[start : start + max_chars])
            start += max_chars
        current = ""
    if current or not chunks:
        chunks.append(current)
    return chunks


def _build_basic_pdf_bytes(text: str) -> bytes:
    lines_per_page = max(1, int((PDF_FALLBACK_PAGE_HEIGHT - (2 * PDF_FALLBACK_MARGIN_Y)) / PDF_FALLBACK_LINE_HEIGHT))
    max_chars = max(20, int((PDF_FALLBACK_PAGE_WIDTH - (2 * PDF_FALLBACK_MARGIN_X)) / (PDF_FALLBACK_FONT_SIZE * 0.5)))
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    wrapped_lines: list[str] = []
    for line in raw_lines:
        wrapped_lines.extend(_wrap_pdf_text_line(line, max_chars))
    if not wrapped_lines:
        wrapped_lines = [""]

    pages: list[list[str]] = []
    for idx in range(0, len(wrapped_lines), lines_per_page):
        pages.append(wrapped_lines[idx : idx + lines_per_page])

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    page_object_indexes: list[int] = []
    for _ in pages:
        page_object_indexes.append(len(objects) + 1)
        objects.append(b"")
    content_object_indexes: list[int] = []
    for page_lines in pages:
        content_object_indexes.append(len(objects) + 1)
        stream_lines: list[str] = ["BT", f"/F1 {PDF_FALLBACK_FONT_SIZE} Tf", f"{PDF_FALLBACK_MARGIN_X} {PDF_FALLBACK_PAGE_HEIGHT - PDF_FALLBACK_MARGIN_Y} Td"]
        for i, line in enumerate(page_lines):
            escaped = _escape_pdf_literal(line)
            if i > 0:
                stream_lines.append(f"0 -{PDF_FALLBACK_LINE_HEIGHT} Td")
            stream_lines.append(f"({escaped}) Tj")
        stream_lines.append("ET")
        stream_bytes = ("\n".join(stream_lines) + "\n").encode("latin-1", errors="replace")
        content_object = (
            b"<< /Length "
            + str(len(stream_bytes)).encode("ascii")
            + b" >>\nstream\n"
            + stream_bytes
            + b"endstream"
        )
        objects.append(content_object)
    font_object_index = len(objects) + 1
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_indexes).encode("ascii")
    objects[1] = (
        b"<< /Type /Pages /Kids ["
        + kids
        + b"] /Count "
        + str(len(page_object_indexes)).encode("ascii")
        + b" >>"
    )
    for i, page_id in enumerate(page_object_indexes):
        content_id = content_object_indexes[i]
        objects[page_id - 1] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
            + str(PDF_FALLBACK_PAGE_WIDTH).encode("ascii")
            + b" "
            + str(PDF_FALLBACK_PAGE_HEIGHT).encode("ascii")
            + b"] /Resources << /Font << /F1 "
            + str(font_object_index).encode("ascii")
            + b" 0 R >> >> /Contents "
            + str(content_id).encode("ascii")
            + b" 0 R >>"
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_pos = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode("ascii")
        + b"\n%%EOF\n"
    )
    return bytes(output)


async def _compile_latex_to_pdf(work_dir: str) -> str:
    xelatex_binary = shutil.which("xelatex")
    if not xelatex_binary:
        raise CalculatorError(
            "XeLaTeX is not installed. Install TeX Live with xelatex and required packages (including xepersian)."
        )

    command = [
        xelatex_binary,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "document.tex",
    ]
    logs: list[str] = []
    for _ in range(2):
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=PDF_GENERATOR_LATEX_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            try:
                process.kill()
            except Exception:
                pass
            await process.wait()
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise CalculatorError("PDF generation timed out while running XeLaTeX") from exc
        output_text = (
            (stdout_bytes or b"").decode("utf-8", errors="replace")
            + "\n"
            + (stderr_bytes or b"").decode("utf-8", errors="replace")
        )
        logs.append(output_text)
        if process.returncode != 0:
            excerpt = _latex_log_excerpt("\n".join(logs))
            raise CalculatorError(f"XeLaTeX failed to compile the document.\n{excerpt}")

    pdf_path = os.path.join(work_dir, "document.pdf")
    if not os.path.isfile(pdf_path):
        raise CalculatorError("XeLaTeX completed but no PDF file was produced")
    return pdf_path


async def run_pdf_generator_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized_arguments = _normalize_tool_arguments(arguments)
    content = normalized_arguments.get("content")
    if not isinstance(content, str) or not content.strip():
        raise CalculatorError("content is required")
    if len(content) > PDF_GENERATOR_MAX_SOURCE_CHARS:
        raise CalculatorError(f"content is too long (max {PDF_GENERATOR_MAX_SOURCE_CHARS} characters)")

    latex_mode = str(normalized_arguments.get("latex_mode") or "body").strip().lower()
    if latex_mode not in {"body", "full_document"}:
        raise CalculatorError("latex_mode must be either body or full_document")

    rtl = normalized_arguments.get("rtl")
    if rtl is None:
        rtl_enabled = True
    elif isinstance(rtl, bool):
        rtl_enabled = rtl
    else:
        raise CalculatorError("rtl must be a boolean when provided")

    title = normalized_arguments.get("title")
    if title is not None and not isinstance(title, str):
        raise CalculatorError("title must be a string when provided")

    return_base64 = normalized_arguments.get("return_base64")
    if return_base64 is None:
        include_base64 = False
    elif isinstance(return_base64, bool):
        include_base64 = return_base64
    else:
        raise CalculatorError("return_base64 must be a boolean when provided")

    requested_filename = _sanitize_pdf_filename(normalized_arguments.get("output_filename"))
    output_filename = _build_pdf_output_filename(requested_filename)
    os.makedirs(PDF_GENERATOR_OUTPUT_DIR, exist_ok=True)
    _cleanup_expired_generated_pdfs()
    destination_path = os.path.join(PDF_GENERATOR_OUTPUT_DIR, output_filename)

    xelatex_ready, xelatex_error = _pdf_is_xelatex_ready()
    engine = "xelatex"
    warning: str | None = None
    if xelatex_ready:
        with tempfile.TemporaryDirectory(prefix="pdfgen_") as temp_dir:
            shutil.copy2(PDF_GENERATOR_FONT_PATH, os.path.join(temp_dir, PDF_GENERATOR_FONT_FILENAME))
            
            # Detect and copy images referenced in markdown
            image_refs = re.findall(r"!\[.*?\]\((.*?)\)", content)
            for img_path in image_refs:
                if os.path.isabs(img_path) and os.path.isfile(img_path):
                    try:
                        shutil.copy2(img_path, temp_dir)
                    except Exception:
                        pass
                elif os.path.isfile(os.path.join(os.getcwd(), img_path)):
                    try:
                        shutil.copy2(os.path.join(os.getcwd(), img_path), temp_dir)
                    except Exception:
                        pass

            tex_path = os.path.join(temp_dir, "document.tex")
            if latex_mode == "full_document":
                latex_source = content
            else:
                body_content = _convert_markdown_bold_outside_math(content)
                latex_source = _build_pdf_body_document(body_content, rtl=rtl_enabled, title=title)
            try:
                with open(tex_path, "w", encoding="utf-8") as source_file:
                    source_file.write(latex_source)
                compiled_pdf_path = await _compile_latex_to_pdf(temp_dir)
                shutil.move(compiled_pdf_path, destination_path)
            except CalculatorError as compile_error:
                if latex_mode != "body":
                    raise
                safe_content = _coerce_body_content_to_safe_latex(content)
                safe_latex_source = _build_pdf_body_document(safe_content, rtl=rtl_enabled, title=title)
                try:
                    with open(tex_path, "w", encoding="utf-8") as source_file:
                        source_file.write(safe_latex_source)
                    compiled_pdf_path = await _compile_latex_to_pdf(temp_dir)
                    shutil.move(compiled_pdf_path, destination_path)
                except CalculatorError:
                    engine = "basic_pdf_fallback"
                    fallback_text = _fallback_plain_text_from_latex(content, latex_mode=latex_mode)
                    with open(destination_path, "wb") as output_file:
                        output_file.write(_build_basic_pdf_bytes(fallback_text))
                    warning = (
                        "Generated with basic fallback because advanced LaTeX formatting could not be compiled safely."
                    )
    else:
        engine = "basic_pdf_fallback"
        fallback_text = _fallback_plain_text_from_latex(content, latex_mode=latex_mode)
        with open(destination_path, "wb") as output_file:
            output_file.write(_build_basic_pdf_bytes(fallback_text))
        warning = (
            f"Generated with basic fallback because XeLaTeX runtime is unavailable ({xelatex_error}). "
            "Fallback output is plain text and may not render Persian/RTL or LaTeX formatting correctly."
        )

    size_bytes = int(os.path.getsize(destination_path))
    expires_at = datetime.fromtimestamp(
        os.path.getmtime(destination_path) + PDF_GENERATOR_TTL_SECONDS,
        tz=timezone.utc,
    ).isoformat()
    response: dict[str, Any] = {
        "ok": True,
        "engine": engine,
        "latex_mode": latex_mode,
        "rtl": rtl_enabled,
        "file_name": output_filename,
        "size_bytes": size_bytes,
        "storage_path": os.path.join("uploads", "generated_pdfs", output_filename),
        "download_url": f"/api/generated-pdfs/{quote(output_filename)}",
        "expires_in_seconds": PDF_GENERATOR_TTL_SECONDS,
        "expires_at": expires_at,
    }
    if engine == "xelatex":
        response["font"] = "Vazirmatn-Regular"
    if warning:
        response["warning"] = warning

    if include_base64:
        if size_bytes > PDF_GENERATOR_MAX_BASE64_BYTES:
            response["base64_included"] = False
            response["base64_skip_reason"] = (
                f"PDF is too large for base64 output ({size_bytes} bytes > {PDF_GENERATOR_MAX_BASE64_BYTES} bytes)."
            )
        else:
            with open(destination_path, "rb") as file_obj:
                response["pdf_base64"] = base64.b64encode(file_obj.read()).decode("ascii")
            response["base64_included"] = True

    return response


async def _load_web_search_config(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        select(WebSearchConfig)
        .where(WebSearchConfig.is_active == True)
        .order_by(WebSearchConfig.id.desc())
    )
    config = result.scalars().first()
    if config:
        return {
            "provider": (config.provider or "exa").strip().lower(),
            "base_url": config.base_url or "https://api.exa.ai/search",
            "api_key": config.api_key or "",
            "search_type": config.search_type or "auto",
            "max_results": int(config.max_results or 5),
            "include_domains": config.include_domains,
            "exclude_domains": config.exclude_domains,
            "contents_options": config.contents_options or {"highlights": {"maxCharacters": 1200}},
        }
    return {
        "provider": (WEB_SEARCH_PROVIDER or "exa").strip().lower(),
        "base_url": WEB_SEARCH_API_URL or "https://api.exa.ai/search",
        "api_key": WEB_SEARCH_API_KEY or "",
        "search_type": "auto",
        "max_results": 5,
        "include_domains": None,
        "exclude_domains": None,
        "contents_options": {"highlights": {"maxCharacters": 1200}},
        "model": WEB_SEARCH_MODEL,
    }


def _compact_exa_result(item: dict[str, Any]) -> dict[str, Any]:
    highlights = item.get("highlights")
    if isinstance(highlights, list):
        snippets = [str(value).strip() for value in highlights if str(value).strip()]
    elif isinstance(highlights, str) and highlights.strip():
        snippets = [highlights.strip()]
    else:
        snippets = []
    text = item.get("text")
    if not snippets and isinstance(text, str) and text.strip():
        snippets = [text.strip()[:1200]]
    summary = item.get("summary")
    if not snippets and isinstance(summary, str) and summary.strip():
        snippets = [summary.strip()]

    return {
        "title": item.get("title"),
        "url": item.get("url"),
        "published_date": item.get("publishedDate"),
        "author": item.get("author"),
        "snippet": "\n".join(snippets[:3])[:1800],
    }


async def _run_exa_search(query: str, config: dict[str, Any]) -> dict[str, Any]:
    api_key = config.get("api_key") or ""
    if not api_key:
        raise CalculatorError("Exa web search API key is not configured. Add it in Admin → Web Search.")

    max_results = max(1, min(int(config.get("max_results") or 5), 10))
    payload: dict[str, Any] = {
        "query": query,
        "type": config.get("search_type") or "auto",
        "numResults": max_results,
        "contents": config.get("contents_options") or {"highlights": {"maxCharacters": 1200}},
    }
    if config.get("include_domains"):
        payload["includeDomains"] = config["include_domains"]
    if config.get("exclude_domains"):
        payload["excludeDomains"] = config["exclude_domains"]

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(config.get("base_url") or "https://api.exa.ai/search", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    results = [_compact_exa_result(item) for item in data.get("results", []) if isinstance(item, dict)]
    answer_lines = []
    for index, item in enumerate(results, start=1):
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        snippet = item.get("snippet") or "No excerpt returned."
        answer_lines.append(f"{index}. {title}\n{url}\n{snippet}")

    return {
        "provider": "exa",
        "query": query,
        "request_id": data.get("requestId"),
        "answer": "\n\n".join(answer_lines) or "No search results returned.",
        "results": results,
    }


async def run_web_search_tool(db: AsyncSession, arguments: dict[str, Any]) -> dict[str, Any]:
    query = (arguments or {}).get("query")
    if not isinstance(query, str) or not query.strip():
        raise CalculatorError("query is required")
    config = await _load_web_search_config(db)
    provider = (config.get("provider") or "exa").strip().lower()
    if provider != "exa":
        raise CalculatorError(f"Unsupported web search provider: {provider}")
    return await _run_exa_search(query.strip(), config)
