---
name: jgpti-tool-creator
description: Create and bind JGPTi HTTP tools through the Admin API when asked to add API-backed tools (for example weather, stocks, lookup APIs). Builds `kind=http` tools with `implementation_config`, validates API status codes, and attaches a global tool binding.
---

# JGPTi Tool Creator

Use this skill when the request is to create/add/register a new tool in JGPTi that calls an HTTP API.

## Trigger Phrases

- create a tool
- add a weather tool
- make a tool for API
- register HTTP tool
- add an integration tool

## Required Inputs

Collect these before API calls:

1. Tool metadata: `name`, `display_name`, `description`.
2. HTTP runtime config:
   - `method` (GET/POST/PUT/PATCH/DELETE)
   - `url` (supports path templates like `/users/{user_id}`)
   - optional static `headers` map
3. Input schema (`input_schema`) describing callable arguments.
4. Admin API access:
   - base URL (for example `http://localhost:8000`)
   - `ADMIN_PASSWORD` bearer token

## Workflow

1. Build `POST /admin/tools` payload with:
   - `kind: "http"`
   - `implementation_key: null`
   - `implementation_config` object
   - `input_schema` object
   - `is_active: true`
   - `is_builtin: false`
2. Submit tool creation request.
3. Validate response status code is `201` and capture returned `id`.
4. Create global binding with `POST /admin/tool-bindings`:
   - `tool_id: <created_id>`
   - `scope_type: "global"`
   - `scope_id: null`
   - `is_enabled: true`
5. Validate binding response status code is `201`.
6. Report created tool id + binding id.

## cURL Template

```bash
curl -sS -X POST "${BASE_URL}/admin/tools" \
  -H "Authorization: Bearer ${ADMIN_PASSWORD}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "weather_current",
    "display_name": "Current Weather",
    "description": "Get current weather by city.",
    "kind": "http",
    "implementation_key": null,
    "implementation_config": {
      "method": "GET",
      "url": "https://api.example.com/weather/current",
      "headers": {
        "X-Api-Key": "'"${WEATHER_API_KEY}"'"
      }
    },
    "input_schema": {
      "type": "object",
      "properties": {
        "city": {"type": "string", "description": "City name"}
      },
      "required": ["city"],
      "additionalProperties": false
    },
    "is_active": true,
    "is_builtin": false
  }'
```

```bash
curl -sS -X POST "${BASE_URL}/admin/tool-bindings" \
  -H "Authorization: Bearer ${ADMIN_PASSWORD}" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_id": TOOL_ID,
    "scope_type": "global",
    "scope_id": null,
    "is_enabled": true
  }'
```

## Python (httpx) Template

```python
import os
import httpx

base_url = os.environ["JGPTI_BASE_URL"].rstrip("/")
admin_password = os.environ["ADMIN_PASSWORD"]

headers = {
    "Authorization": f"Bearer {admin_password}",
    "Content-Type": "application/json",
}

tool_payload = {
    "name": "weather_current",
    "display_name": "Current Weather",
    "description": "Get current weather by city.",
    "kind": "http",
    "implementation_key": None,
    "implementation_config": {
        "method": "GET",
        "url": "https://api.example.com/weather/current",
        "headers": {"X-Api-Key": os.environ.get("WEATHER_API_KEY", "")},
    },
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
        "additionalProperties": False,
    },
    "is_active": True,
    "is_builtin": False,
}

with httpx.Client(timeout=30.0) as client:
    tool_resp = client.post(f"{base_url}/admin/tools", headers=headers, json=tool_payload)
    tool_resp.raise_for_status()
    if tool_resp.status_code != 201:
        raise RuntimeError(f"Unexpected status for tool create: {tool_resp.status_code}")
    tool = tool_resp.json()

    binding_payload = {
        "tool_id": tool["id"],
        "scope_type": "global",
        "scope_id": None,
        "is_enabled": True,
    }
    binding_resp = client.post(f"{base_url}/admin/tool-bindings", headers=headers, json=binding_payload)
    binding_resp.raise_for_status()
    if binding_resp.status_code != 201:
        raise RuntimeError(f"Unexpected status for binding create: {binding_resp.status_code}")
    binding = binding_resp.json()

print({"tool_id": tool["id"], "binding_id": binding["id"]})
```

## Safety Rules

- Do not store executable code in the DB. Use `kind=http` + `implementation_config` only.
- Keep secrets in environment variables. Do not hardcode API keys.
- Validate the API response status code after each admin request.
- Fail fast on non-201 responses for create operations.
