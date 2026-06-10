# Dr. Boz API Documentation

Welcome to the Dr. Boz API. This documentation provides a comprehensive guide for interacting with the backend services.

## Base URL

The API is accessible at:
`http://<host>:7000/api`

## Authentication

Authentication varies by endpoint:
- **Admin Endpoints (`/api/admin/*`):** Require an `Authorization: Bearer <ADMIN_PASSWORD>` header.
- **Account & Main Endpoints:** Often require a `telegram_user_id` or `user_id` in the query parameters or request body for context.

## Documentation Modules

The API is divided into the following logical modules:

1. [**Account & Onboarding**](./accounts.md) - User registration, learning preferences, and credits.
2. [**Projects & Documents**](./projects.md) - Knowledge base management and RAG indexing.
3. [**Chat & Agent**](./chat.md) - Messaging, streaming AI responses, and tool execution.
4. [**Admin Operations**](./admin.md) - System configuration, model management, and statistics.
