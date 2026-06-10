# PDF File Access Investigation & Fix Plan

## Problem Statement

When a user uploads a PDF (e.g., `Assignment 2-2.pdf`) and asks the agent to solve a question from it, the agent responds:

> "علی جان، فعلاً نتونستم فایل PDF رو باز کنم چون دسترسی لازم برای خوندن محتوای همین فایل در این لحظه درست عمل نکرد."

The agent cannot access the uploaded file content.

---

## Root Cause Analysis

### Upload Flow

1. User uploads PDF → `_handle_document_upload` (bot.py:8200)
2. File is 241KB (< 500KB threshold) → `_perform_direct_extraction` (bot.py:8301)
3. PDF text extracted via `pypdf` → stored in `pending_files_queue` (bot.py:8340)
4. User clicks "✅ اتمام آپلود و شروع گفتگو" → queue moved to `album_context` (bot.py:9385-9404)
5. User sends question → `handle_message` → `_process_chat_text_turn` (bot.py:10455)
6. `album_context` passed to `_append_recent_uploads_context` (bot.py:9460, 189)
7. File content appended to system prompt → sent to LLM

### Why It Fails

**Primary Issue: `context.user_data` is lost on bot restart**

The bot process (`jgpti-telegram-bot.service`) has restarted multiple times during user sessions:
- `Restart counter is at 2` (from systemctl status)
- `context.user_data` is in-memory session storage
- When bot restarts, `album_context` is `None`
- File content is NOT persisted anywhere

**Secondary Issue: `album_context` gets popped after first use**

Line 6480: `context.user_data.pop("album_context", None)` — this removes the context immediately after the first message, so subsequent questions lose file access.

**Tertiary Issue: No fallback tool to read files**

The agent only has `search_project_context` when inside a project. For regular chats with uploaded files, there's no tool to access file content on-demand.

---

## Evidence from Logs

```
ERROR:app.rag:Error getting collection for chat_647: Collection [chat_647] does not exist
ERROR:app.rag:Error getting collection for chat_649: Collection [chat_649] does not exist
ERROR:app.rag:Error getting collection for chat_651: Collection [chat_651] does not exist
Agent retry 1 due to: Recursion limit of 25 reached without hitting a stop condition.
Agent retry 2 due to: Recursion limit of 25 reached without hitting a stop condition.
Agent retry 3 due to: Recursion limit of 25 reached without hitting a stop condition.
```

- RAG collections don't exist for these chats (direct extraction was used, not RAG)
- Agent enters infinite retry loop (before the system prompt fix)
- `recursion_limit=25` (before the config fix)

### PDF Text Extraction Works

```
Text length: 4088
In the Name of God
Fundamentals of Earthquake Engineering  Mojtaba Mahsuli
Page 1 of 4
Assignment 2
Problem 1
Starting from the basic definition of stiffness, determine the effective stiffness...
```

The PDF text extraction works fine. The issue is purely about getting the text to the agent.

---

## Fixes Implemented

### Fix 1: Persist File Content in DB Messages (Primary)

**File**: `backend/app/bot.py`

**Location**: Line 9385-9404 ("✅ اتمام آپلود و شروع گفتگو" handler)

**Change**: When user confirms upload, save file content as a system message in the chat's message history.

```python
# After setting album_context, also persist to DB
for fname, ftext in texts:
    db.add(Message(
        chat_id=chat_id,
        role="system",
        content=f"[Uploaded File: {fname}]\n{ftext[:15000]}"
    ))
await db.commit()
```

**Why**: DB messages survive bot restarts. `_process_chat_text_turn` already loads the last 40 messages from DB (line 8868-8875), so file content is always in context.

### Fix 3: Don't Pop `album_context` After First Use

**File**: `backend/app/bot.py`

**Location**: Line 6480

**Change**: Remove `context.user_data.pop("album_context", None)` — let the context persist for the conversation.

**Why**: Currently `album_context` is popped immediately after the first message, so subsequent questions lose file access.

---

## Additional Fixes (Not Implemented Yet)

### Fix 2: Add `read_uploaded_file` Tool (Safety Net)

**File**: `backend/app/agent/tools.py`

Add a new tool that lets the agent read uploaded files by ID on-demand:

```python
@tool("read_uploaded_file", args_schema=ReadUploadedFileInput)
async def read_uploaded_file(file_id: int) -> str:
    """Read the content of an uploaded file by its ID."""
    # Query UploadedFile table, read storage_path, return content
```

**Why**: Gives the agent an on-demand way to access file content if it's not in the system prompt.

### Fix 4: Verify System Messages Are Included in LLM Context

**File**: `backend/app/bot.py`

**Location**: Line 8868-8875

Verify that system messages with `[Uploaded File: ...]` prefix are included in `llm_messages`. The current code loads all messages including system messages, so Fix 1 should work automatically.

---

## Architecture Diagram

```
User uploads PDF
    ↓
_handle_document_upload (bot.py:8200)
    ↓
_perform_direct_extraction (bot.py:8301)  ← PDF < 500KB
    ↓
pending_files_queue (context.user_data)   ← IN-MEMORY, lost on restart
    ↓
User clicks "✅ اتمام آپلود"
    ↓
album_context (context.user_data)         ← IN-MEMORY, lost on restart
    ↓
_process_chat_text_turn (bot.py:10455)
    ↓
_append_recent_uploads_context (bot.py:189)
    ↓
System prompt → LLM
```

**Problem**: The entire chain relies on `context.user_data` which is volatile.

**Solution**: Persist file content in DB messages (Fix 1) so it survives restarts.

---

## Service Status

| Service | Command | Status |
|---------|---------|--------|
| Backend API | `jgpti-backend.service` | port 7000 |
| Telegram Bot | `jgpti-telegram-bot.service` | runs `python3 -m app.bot` |

---

## Files Modified

| File | Line | Change |
|------|------|--------|
| `backend/app/bot.py` | 9385-9417 | Persist file content to DB messages in "✅ اتمام آپلود" handler |
| `backend/app/bot.py` | 6457-6495 | Persist file content in `process_queue` callback + remove album_context pop |
| `backend/app/bot.py` | 4004-4031 | Persist file content in album handler + remove album_context pop |

---

## Date

2026-05-17
