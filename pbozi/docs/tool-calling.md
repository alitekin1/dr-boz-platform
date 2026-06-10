# Tool and Function Calling in JGPTi

## Current architecture

JGPTi now has a basic end-to-end tool-calling path in place.

- `backend/app/main_routes.py` runs the web chat request path and performs a single backend-owned tool loop.
- `backend/app/bot.py` mirrors the same pattern for Telegram.
- `backend/app/llm.py` sends OpenAI-compatible `chat/completions` requests, resolves enabled tools, seeds builtin tools, and executes builtin handlers.
- `backend/app/admin_routes.py` exposes admin CRUD for tools, tool bindings, and recent tool calls.
- `backend/app/models.py` stores tool definitions, bindings, and invocation traces.
- `frontend/src/lib/api.ts` and `frontend/src/app/admin/page.tsx` are the admin-facing REST client and UI.

Current runtime flow:

1. user sends a message,
2. backend loads chat history and optional RAG context,
3. backend prepends a system prompt,
4. backend loads enabled tools for the chat scope,
5. backend calls the selected provider with a `tools` array,
6. if the model returns tool calls, the backend executes up to 5 of them, appends `role: tool` results, and makes one follow-up model call,
7. final assistant text plus tool-call trace data are saved and returned.

Builtins currently implemented:

- `calculator`
- `web_search`
- `pdf_generator` (XeLaTeX-based PDF generation with RTL + Vazirmatn template support)

## Recommended tool-calling shape

Add a small orchestration layer between prompt assembly and `call_llm(...)`.

Suggested runtime loop:

1. Build `messages`.
2. Load enabled tools for the current channel and user.
3. Send the model request with a `tools` array.
4. If the model returns a tool call:
   - validate tool name and arguments,
   - execute the tool on the server,
   - append a tool result message,
   - call the model again.
5. Stop when the model returns normal assistant text.
6. Save both tool events and final assistant output.

That keeps provider access in one place and avoids putting business logic in Telegram or the frontend.

## Notes on the current implementation

The current stack is intentionally conservative.

- Tool execution is backend-owned, not delegated to web or Telegram clients.
- Only builtin implementations are executable today.
- Admin-created tool records work as metadata plus routing/config surface, but arbitrary executable code is not supported.
- Tool traces are stored in `tool_calls` and exposed in admin.
- The runtime does one follow-up completion after tool execution instead of an unbounded loop.

## Suggested next backend changes

### 1. Add tool definitions to the data model

A practical first step is a new `Tool` table, for example:

- `id`
- `name` (unique)
- `display_name`
- `description`
- `json_schema`
- `server_handler`
- `is_active`
- `admin_only`
- `channels` (JSON, optional: `web`, `telegram`)
- `created_at`

Keep execution code server-side. Do not store raw Python in the database.

### 2. Add a tool executor module

Suggested file: `backend/app/tools.py`

Responsibilities:

- register built-in handlers,
- map DB tool records to OpenAI-compatible tool schemas,
- validate arguments,
- execute handlers,
- normalize results into compact JSON-safe payloads.

Example shape:

```python
async def build_tools(db, user, channel: str) -> list[dict]: ...
async def execute_tool(name: str, arguments: dict, *, db, user, channel: str) -> dict: ...
```

### 3. Extend the LLM client

`backend/app/llm.py` currently only sends `model`, `messages`, and `stream`.

Extend it to optionally send:

- `tools`
- `tool_choice`

and return the full assistant message object when needed, not just `content`.

A split like this is clean:

- `call_llm_text(...)` for simple text-only flows,
- `call_llm_response(...)` for tool-capable flows.

### 4. Add a chat orchestration function

Suggested file: `backend/app/chat_runtime.py`

This keeps `main_routes.py` thin and makes Telegram/web reuse the same logic.

Pseudo-flow:

```python
while True:
    response = await call_llm_response(..., tools=tool_schemas)
    if not response.tool_calls:
        return response.content

    for tool_call in response.tool_calls:
        result = await execute_tool(...)
        messages.append({"role": "tool", ...})
```

### 5. Store tool traces

If you want auditability, add a small `ToolInvocation` table:

- `chat_id`
- `message_id` or `request_id`
- `tool_name`
- `arguments_json`
- `result_json`
- `status`
- `created_at`

This is especially useful for admin-created tools and debugging Telegram incidents.

## Admin-created tools

The admin panel already manages providers, models, prompts, and embeddings. Tools fit naturally beside those.

Recommended rule: admins create metadata, not executable code.

Good admin-created tool types:

- HTTP wrapper tools against approved internal APIs,
- search tools over local project content,
- read-only business data lookups,
- parameterized actions with strict schemas.

Avoid this pattern:

- storing arbitrary scripts in the database and executing them directly.

Safer design:

- backend ships trusted handlers,
- admin chooses which handlers are enabled,
- admin edits label, description, schema defaults, visibility, and access policy.

Example handler keys:

- `web_search`
- `project_search`
- `list_projects`
- `get_project_documents`
- `get_user_profile`

Then the DB record points to one of those handlers.

## API contract guidance

## OpenAI-compatible tool schema

Use the standard function-tool shape so multiple providers can work with minimal branching.

```json
{
  "type": "function",
  "function": {
    "name": "web_search",
    "description": "Search the web for recent factual information.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": { "type": "string" },
        "max_results": { "type": "integer", "minimum": 1, "maximum": 10 }
      },
      "required": ["query"]
    }
  }
}
```

## Internal REST endpoints

If you expose tools via REST for the web app or admin panel, keep them separate from model-facing tool payloads.

Suggested endpoints:

- `GET /admin/tools`
- `POST /admin/tools`
- `PATCH /admin/tools/{id}`
- `DELETE /admin/tools/{id}`
- `POST /chats/{chat_id}/messages` continues to be the user entrypoint

The chat endpoint should not ask the frontend to execute tools. Tool execution should stay backend-owned.

## Validation rules

Validate before execution:

- known tool name,
- active and channel-allowed,
- argument schema,
- user/admin permission,
- timeout and result size limits.

Normalize every tool result to JSON-friendly output. Keep large raw payloads out of chat history.

## Telegram-specific considerations

Telegram is the place where tool calling can feel most fragile, so keep the behavior conservative.

### Use backend-owned execution

The bot should send user intent to the same backend runtime used by the web app. Do not fork tool logic in `bot.py` beyond Telegram formatting and UI state.

### Keep outputs short

Telegram messages are small, interactive, and easy to overwhelm. Tool results should usually be summarized before sending.

Good pattern:

- tool returns structured JSON,
- assistant converts it into a short answer,
- bot formats for Telegram HTML.

### Handle multi-step latency

Tool use can add extra round trips.

Recommended UX:

- send a “thinking” or temporary progress message,
- stream partial text only if the provider/tool path is reliable,
- otherwise prefer a single final answer.

### Respect Telegram formatting limits

`bot.py` already transforms markdown-ish output into Telegram-safe HTML. Tool results should avoid raw HTML, huge code blocks, or unescaped text.

### Avoid dangerous actions in chat

If you later add write actions, require explicit confirmation for Telegram-triggered destructive operations.

## Web-search tool plan

A web-search tool is the best first tool to add because it is easy to explain and high value for users.

### Phase 1

Implement one built-in handler:

- name: `web_search`
- input: `query`, optional `max_results`
- output: list of result objects with `title`, `url`, `snippet`

Use a single provider first, then wrap it behind a handler interface.

### Phase 2

Add policy controls:

- enabled/disabled,
- allowed channels,
- admin-only toggle,
- per-request timeout,
- result count cap.

### Phase 3

Add answer-grounding behavior:

- require the assistant to cite URLs when web search was used,
- store returned sources with the assistant message,
- show sources in web UI and Telegram.

### Suggested handler contract

```python
async def tool_web_search(arguments: dict, *, user, channel: str) -> dict:
    query = arguments["query"].strip()
    max_results = min(max(arguments.get("max_results", 5), 1), 10)
    ...
    return {"results": results}
```

### Suggested prompt rule

Add one short instruction to the active system prompt:

- use `web_search` only for time-sensitive or external factual questions,
- do not use it for stable internal project knowledge,
- cite the returned sources when using it.

## Implementation order

Completed already:

1. Extend the LLM client to send and receive tool-call payloads.
2. Add DB-backed tool records, bindings, and tool-call logging.
3. Ship `calculator` and `web_search` as builtin tools.
4. Add admin CRUD for tools, bindings, and recent tool calls.

Recommended next:

1. Move the duplicated web and Telegram tool loop into a shared runtime module.
2. Add schema validation before execution instead of relying on handler-level checks alone.
3. Support iterative tool rounds until a normal assistant stop condition, with conservative limits.
4. Store and surface source links more explicitly for web search.
5. Add tests around tool resolution precedence, tool-call persistence, and malformed arguments.

## Important current gaps

A few repo details matter before exposing tool calling broadly:

- `frontend/src/lib/config.ts` currently hardcodes `ADMIN_PASSWORD = "admin123"`; move this to environment config.
- `ProviderOut` currently includes `api_key`; admin read APIs should mask or omit secrets.
- tool execution should have strict allowlists, because the app already supports admin-managed external provider URLs.

Those are worth fixing early, because tool calling increases the blast radius of configuration mistakes.
