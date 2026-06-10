# Persistent File Processing Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide real-time, persistent feedback during file processing in the Telegram bot, including chat header status and detailed message progress.

**Architecture:** 
1. Enhance the RAG module to support asynchronous progress callbacks during indexing.
2. Update the bot's background task to maintain a "typing" status in the chat header and display detailed progress steps in the processing message.

**Tech Stack:** Python, Python-Telegram-Bot, SQLAlchemy, asyncio.

---

### Task 1: Enhance RAG Indexing with Progress Callbacks

**Files:**
- Modify: `backend/app/rag.py`
- Modify: `backend/app/services/rag_service.py`

- [ ] **Step 1: Update `index_document_async` in `rag.py` to support `progress_callback`**

```python
# backend/app/rag.py
async def index_document_async(
    project_id: int, 
    document_id: int, 
    file_path: str,
    api_key: str = None, 
    model: str = None, 
    provider: str = "google", 
    base_url: str = None,
    progress_callback=None # Add this parameter
) -> int:
    # ... inside the producer/worker logic ...
    if progress_callback:
        await progress_callback("reading", 0, 0)
    
    # After reading, before chunking
    if progress_callback:
        await progress_callback("chunking", 0, 0)

    # Inside the worker loop, after each successful batch add
    if progress_callback:
        await progress_callback("indexing", chunk_counter, total_estimated_or_actual)
```

- [ ] **Step 2: Update `background_index_document` in `rag_service.py` to forward the callback**

```python
# backend/app/services/rag_service.py
async def background_index_document(
    # ... existing params ...
    progress_callback=None
):
    # Pass progress_callback to index_document_async
```

- [ ] **Step 3: Commit Task 1**
```bash
git add backend/app/rag.py backend/app/services/rag_service.py
git commit -m "feat(rag): add progress callback support for indexing"
```

---

### Task 2: Implement Persistent Status and Progress in Bot

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update `_background_index_with_notification` to include a "typing" loop and detailed progress**

```python
# backend/app/bot.py
async def _background_index_with_notification(...):
    progress_state = {"phase": "starting", "current": 0, "total": 0}
    
    async def progress_cb(phase, current, total):
        progress_state.update({"phase": phase, "current": current, "total": total})

    # Update spinner task to use progress_state
    # Add a loop for bot.send_chat_action(chat_id, action="typing")
```

- [ ] **Step 2: Verify the "typing" status persists until the very end**
Ensure the chat action loop continues until the final success/error message is sent.

- [ ] **Step 3: Commit Task 2**
```bash
git add backend/app/bot.py
git commit -m "feat(bot): implement persistent status and progress for file processing"
```

---

### Task 3: Manual Verification and Final Polishing

- [ ] **Step 1: Restart backend and bot**
```bash
cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload
# (In another terminal) Run the bot_watcher.py or bot script
```

- [ ] **Step 2: Test with a large PDF**
Upload a 10MB+ PDF and verify:
1. Header says "typing..." continuously.
2. Message updates from "Reading" -> "Chunking" -> "Indexing X/Y".
3. Final success message replaces the spinner.

- [ ] **Step 3: Commit Final**
```bash
git commit --allow-empty -m "docs: finalize persistent status updates implementation"
```
