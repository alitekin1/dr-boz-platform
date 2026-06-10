---
title: API Documentation Specs
date: 2026-05-10
---

# API Documentation Design

## Overview
A comprehensive documentation portal for the Dr. Boz API, covering both user-facing and admin-restricted endpoints.

## Structure
- `/docs/api/README.md`: Entry point and auth overview.
- `/docs/api/accounts.md`: User management and onboarding.
- `/docs/api/projects.md`: Project and RAG management.
- `/docs/api/chat.md`: Chat messaging and SSE streaming.
- `/docs/api/admin.md`: Admin-only system configuration.

## Implementation Details
- Format: Markdown.
- Content: Based on source code analysis of `app/main_routes.py`, `app/account_routes.py`, `app/agent_routes.py`, and `app/admin_routes.py`.
