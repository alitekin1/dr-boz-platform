# Dynamic HTTP Tools and Tool Creator Skill Design

## Overview
This design introduces the ability for JGPTi to support dynamic HTTP-based tools and provides a new Gemini CLI skill (`jgpti-tool-creator`) that enables the AI to autonomously define, register, and bind these tools via the JGPTi Admin API.

## Architecture

### 1. Database and Model Changes
To support flexible HTTP tools without injecting arbitrary Python code into the database, we will extend the `Tool` model:
- Add a new `implementation_config` column of type `JSON` to the `Tool` model. This will store the HTTP configuration (method, base URL template, default headers).
- Update `backend/app/database.py`'s SQLite migration block for the `tools` table to include `ALTER TABLE tools ADD COLUMN implementation_config JSON`.
- Update `backend/app/schemas.py` (`ToolBase`, `ToolCreate`, `ToolUpdate`, `ToolOut`) to include `implementation_config: Optional[dict] = None`.

### 2. Execution Logic (`backend/app/llm.py`)
Modify `execute_tool_call` to handle a new `tool.kind == "http"`:
- When triggered, it will read `tool.implementation_config`.
- Expected config shape:
  ```json
  {
    "method": "GET",
    "url": "https://api.weather.com/v1/current",
    "headers": {"Authorization": "Bearer ..."}
  }
  ```
- It will parse the LLM-provided `arguments` (from `input_schema`) and dynamically inject them. For GET requests, arguments become query parameters (or URL path parameters if templated). For POST/PUT requests, arguments become the JSON body.
- It will use `httpx.AsyncClient` to make the external call and return the JSON response.

### 3. AI Skill (`jgpti-tool-creator`)
A new Superpowers skill will be created in the current workspace (or globally depending on preference, but we'll build it locally) using the `skill-creator` process.
- **Trigger**: "create a tool", "add a weather tool", "make a tool for API"
- **Workflow**:
  1. Determine the exact API requirements (URL, method, auth, input schema).
  2. Send a `POST /admin/tools` request via `httpx` or `curl` (using `ADMIN_PASSWORD` Bearer token) with `kind: "http"`, `implementation_config`, and the `input_schema`.
  3. Send a `POST /admin/tool-bindings` request to bind the tool globally (`scope_type: "global"`).

## Error Handling
- The HTTP execution in `llm.py` must catch `httpx.HTTPStatusError` and `httpx.RequestError` and cleanly return them in the `ToolCall` error field without crashing the chat loop.
- The `jgpti-tool-creator` skill will verify the successful creation of tools by checking the HTTP status codes from the backend API.

## Testing Strategy
- Create a simple mock HTTP tool (e.g., hitting a public test API like `httpbin.org/get`).
- Verify the DB migration properly adds the `implementation_config` column.
- Verify the tool execution logs correctly in the `tool_calls` table.