# Admin Error Logging Design

## Overview
A new feature to capture and display user-facing and system errors directly in the Admin Panel's Monitoring page. This allows administrators to proactively identify and resolve issues without accessing raw server logs.

## Architecture & Components

### 1. Database Model
A new SQLAlchemy model `ErrorLog` will be added to `backend/app/models.py`.
**Fields:**
- `id`: Integer, Primary Key
- `timestamp`: DateTime, default `utcnow`
- `source`: String (e.g., 'API', 'Telegram')
- `error_message`: Text
- `stack_trace`: Text
- `user_id`: Integer, nullable (Foreign Key to `User`, if identifiable)
- `resolved`: Boolean, default `False`

### 2. Backend Logic
**Global Exception Handlers:**
- **FastAPI:** Add a global exception handler for `Exception` in `backend/app/main.py` (or `backend/app/main_routes.py`). This will catch all unhandled 500 errors, log them to the `ErrorLog` table, and return the standard 500 JSON response.
- **Telegram Bot:** Add an error handler to the Telegram application (e.g., via `application.add_error_handler`) in the bot setup (`backend/app/bot.py`). This will catch errors during update processing, attempt to extract the `user_id` from the update, and save the log to `ErrorLog`.

**Admin API Routes (`backend/app/admin_routes.py`):**
- `GET /admin/errors`: Fetches a paginated list of error logs, ordered by timestamp descending.
- `PATCH /admin/errors/{id}/resolve`: Marks a specific error log as `resolved = True`.

### 3. Frontend Admin Panel
**Monitoring Page Updates (`frontend-v2/src/pages/Monitoring.tsx`):**
- Add a new section for "Error Logs" alongside the existing `UsageFeed` and `AuditLog`.

**New Component (`frontend-v2/src/components/monitoring/ErrorLogTable.tsx`):**
- Displays a table/list of errors fetched from `GET /admin/errors`.
- **Columns/Data:** Timestamp, Source, Error Message, Status (Resolved/Unresolved).
- **Actions:** 
  - "View Trace" button: Opens a modal showing the full `stack_trace`.
  - "Mark Resolved" button: Calls `PATCH /admin/errors/{id}/resolve`.

## Error Handling & Edge Cases
- **Database Failure During Error Logging:** If the database itself is the source of the exception, the global error handler might fail to log the error to the database. The handler should gracefully fall back to standard `logging.error` to avoid cascading failures.

## Testing Strategy
- Trigger a mock 500 error on a test API endpoint and verify it appears in the `ErrorLog` table.
- Trigger a mock Telegram update error and verify it logs correctly.
- Ensure the Admin UI successfully fetches and resolves the errors.