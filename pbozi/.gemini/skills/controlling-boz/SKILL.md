---
name: controlling-boz
description: Use this skill to control BOZGPT (Dr. Bose) via API endpoints. It allows for sending messages, broadcasting to users, managing projects/documents, and interacting with the user account system. Ideal for automation agents (e.g., marketing, database analysis).
---

# Controlling BOZ (Dr. Bose)

This skill provides the instructions and patterns for an AI agent to control the BOZGPT backend.

## Workflow: Messaging Users

When tasked with messaging users based on analysis (e.g., "Message all users who haven't finished onboarding"):

1. **Identify Targets**: Use `GET /api/admin/users` to get the list of users and their status.
2. **Filter**: Process the user list to find those matching your criteria.
3. **Draft Content**: Create the personalized or broadcast message.
4. **Send**:
   - For mass messaging, use `POST /api/admin/broadcast`.
   - For individual follow-ups, use `POST /api/chats/{chat_id}/messages`.

## Workflow: Data Analysis & Reporting

1. **Collect Data**: Use `GET /api/admin/stats` and `GET /api/admin/usage-events` to gather system usage data.
2. **Analyze**: Perform your domain-specific analysis (marketing, technical, etc.).
3. **Report/Notify**: Use the messaging workflow to communicate findings to admins or users.

## API Reference

For a complete list of endpoints, request bodies, and authentication details, see [api_reference.md](references/api_reference.md).

## Key Parameters

- **Base URL**: `http://localhost:7000/api`
- **Admin Auth**: `Authorization: Bearer <ADMIN_PASSWORD>` (Default: `admin123`)
- **Default Port**: 7000

## Examples

### Sending a Broadcast
```bash
curl -X POST "http://localhost:7000/api/admin/broadcast" \
     -H "Authorization: Bearer admin123" \
     -F "message=Hello from the marketing agent!" \
     -F 'target_groups=["all"]'
```

### Sending an Individual Message
```bash
curl -X POST "http://localhost:7000/api/chats/5/messages" \
     -H "Content-Type: application/json" \
     -d '{"content": "Your analysis is ready.", "model_id": 1}'
```
