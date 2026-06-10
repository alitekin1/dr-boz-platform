# Design Spec: Persistent File Processing Status and Progress

The goal is to provide continuous feedback to the user during file uploads and background indexing in the Telegram bot. This includes both the message content (detailed steps) and the chat header status ("typing/uploading").

## Proposed Changes

### 1. Backend: Progress Tracking (`backend/app/rag.py` & `backend/app/services/rag_service.py`)

*   **`index_document_async`**:
    *   Add an optional `progress_callback: Callable[[str, int, int], Awaitable[None]]` parameter.
    *   Phases:
        *   `reading`: Before starting `_read_file`.
        *   `chunking`: After reading, before starting producers.
        *   `indexing`: Called periodically by workers after each batch is added to ChromaDB.
    *   The callback will receive `(phase, current_count, total_count)`.

*   **`background_index_document`**:
    *   Accept a `callback` and pass it through to `index_document_async`.

### 2. Bot: Persistent Status & Chat Action (`backend/app/bot.py`)

*   **Chat Action Loop**:
    *   In `_background_index_with_notification`, start a background loop that calls `context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)` (or `UPLOAD_DOCUMENT`) every 4-5 seconds.
    *   This loop must run until the indexing is finished or failed.

*   **Spinner & Progress Message**:
    *   Update the `spinner` task to also handle progress updates from the RAG callback.
    *   Instead of just rotating frames, it will display the specific stage and chunk count if available.
    *   Example message content:
        ```
        🔄 در حال پردازش فایل: filename.pdf
        
        ✂️ در حال قطعه‌بندی متن...
        🏗 ایندکس کردن قطعات: 120 / 1500
        
        این کار در پس‌زمینه انجام می‌شود... ⏳
        ```

*   **Final State**:
    *   Edit the message to the final success/error state.
    *   (Optional but requested previously) Send a new message to trigger notification, but focus on the "spinner" and "header status" as per latest instructions.

## Approaches Considered

1.  **Approach A: Polling DB status (Simple)**: Have the bot poll the `Document` status in the DB.
    *   *Cons*: High DB overhead, low granularity (only 'processing' or 'indexed').
2.  **Approach B: Real-time Callback (Recommended)**: Pass a callback down to the indexing logic.
    *   *Pros*: Precise progress reporting, low latency.

## Verification Plan

*   **Manual Test**: Upload a large PDF (like the one in the user screenshot) and verify:
    1.  The chat header says "is typing..." or "is uploading..." continuously.
    2.  The message text updates with progress (e.g., chunk counts).
    3.  The spinner doesn't stop until the very end.
*   **Unit Test**: Mock the callback in `index_document_async` to ensure it's called with the correct phases.
