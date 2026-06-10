import json
from typing import Any

DIRECT_DELIVERABLE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".csv"}


def parse_tool_output(output: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(output, dict):
        return output
    if not output:
        return None
    try:
        parsed = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def should_deliver_python_files(tool_output: str | dict[str, Any] | None) -> bool:
    return bool(files_to_deliver_from_python(tool_output))


def files_to_deliver_from_python(tool_output: str | dict[str, Any] | None) -> list[str]:
    data = parse_tool_output(tool_output)
    if not data or not data.get("new_files"):
        return []

    files = [path for path in data["new_files"] if isinstance(path, str)]
    if data.get("send_to_chat") is True:
        return files

    return [
        path
        for path in files
        if any(path.lower().endswith(ext) for ext in DIRECT_DELIVERABLE_EXTENSIONS)
    ]
