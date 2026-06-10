# Image Processing Hang Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix multiple issues causing the bot to hang or ignore images, including blocking syscalls, logic errors in update claiming, and album processing leaks.

**Architecture:** 
- Convert blocking `subprocess.run` and `_read_file` calls to use `asyncio.to_thread` or `asyncio.create_subprocess_exec`.
- Refine `_claim_update_once` to support internal re-entry (e.g. from document handlers to chat handlers).
- Fix the race condition/leak in `ALBUM_PENDING_COUNT` by ensuring only successfully claimed updates increment the count.

**Tech Stack:** Python, asyncio, python-telegram-bot, FastAPI

---

### Task 1: Non-blocking Bale Downloads

**Files:**
- Modify: `backend/app/bot.py:313-380`

- [ ] **Step 1: Modify `_download_telegram_file` to use `asyncio.to_thread` for the `curl` call.**
This prevents the 10-minute timeout from blocking the entire bot event loop.

```python
# In backend/app/bot.py

# Replace the blocking subprocess.run with asyncio.to_thread
import subprocess
result = await asyncio.to_thread(
    subprocess.run,
    ["curl", "-L", "-s", "-f", "--connect-timeout", "20", "--max-time", "600", "-A", "Mozilla/5.0", "-o", dest_path, download_url],
    capture_output=True, text=True
)
```

- [ ] **Step 2: Verify code syntax.**

- [ ] **Step 3: Commit.**

```bash
git add backend/app/bot.py
git commit -m "fix: make Bale file download non-blocking to the event loop"
```

---

### Task 2: Fix `_claim_update_once` for internal calls and Albums

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update `_claim_update_once` to allow re-claiming if requested.**
Add an optional `allow_reclaim` parameter.

```python
async def _claim_update_once(update: Update, allow_reclaim: bool = False) -> bool:
    if update.update_id is None:
        return True
    async with async_session() as db:
        # ...
        if existing:
            if existing.status == "completed":
                return False
            
            if allow_reclaim:
                return True # Allow re-entry if explicitly requested
            
            # ... existing timeout logic ...
```

- [ ] **Step 2: Update `handle_message` to use `allow_reclaim=True` when `forced_text` is provided.**
This allows document handlers (which already claimed the update) to call the chat handler successfully.

```python
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, forced_text: str = None):
    # ...
    if not await _claim_update_once(update, allow_reclaim=(forced_text is not None)):
        return
```

- [ ] **Step 3: Move `_register_album_update` AFTER `_claim_update_once` in handlers.**
This prevents count leaks from duplicate/ignored updates.

In `_handle_document_upload` and `handle_photo`:
```python
# Move this:
# await _register_album_update(update) 
# After this:
if not await _claim_update_once(update): return
await _register_album_update(update)
```

- [ ] **Step 4: Commit.**

```bash
git add backend/app/bot.py
git commit -m "fix: resolve update claiming conflicts and album count leaks"
```

---

### Task 3: Non-blocking Indexing Read

**Files:**
- Modify: `backend/app/rag.py:339`

- [ ] **Step 1: Use `asyncio.to_thread` for `_read_file` in `index_document_async`.**
This prevents slow file parsing (e.g. MarkItDown on images) from blocking the event loop.

```python
# In backend/app/rag.py

        else:
            # For non-PDF, read and chunk (non-streaming for simplicity for now)
            text = await asyncio.to_thread(_read_file, file_path)
```

- [ ] **Step 2: Commit.**

```bash
git add backend/app/rag.py
git commit -m "fix: make non-PDF file reading non-blocking during indexing"
```

---

### Task 4: Ensure updates are marked completed for documents

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Add `_mark_update_completed` to `_handle_document_upload` finally block if not already there.**
Wait, if `handle_message` is called, it will mark it completed. If not (e.g. no caption), we need to do it.

```python
# In backend/app/bot.py, inside _handle_document_upload finally:
    finally:
        _unregister_user_task(chat_id, task)
        await _finish_album_update(update, context, handle_message)
        # Ensure update is marked completed if it wasn't a RAG background task
        if not use_rag:
             await _mark_update_completed(update)
```

- [ ] **Step 2: Commit.**

```bash
git add backend/app/bot.py
git commit -m "fix: ensure document updates are marked as completed"
```

---

### Task 5: Verification

- [ ] **Step 1: Run reproduction script to ensure `_read_file` still works.**
Run: `backend/venv/bin/python3 reproduce_image_hang.py`

- [ ] **Step 2: Check for any syntax errors in `bot.py`.**
Run: `backend/venv/bin/python3 -m py_compile backend/app/bot.py`

- [ ] **Step 3: (Manual) User should test sending an image as a document and as a photo.**
