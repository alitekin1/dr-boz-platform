# /stop Command Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `USER_AGENT_TASKS` to track multiple concurrent tasks per user and update all long-running operations to register themselves.

**Architecture:** 
- Change `USER_AGENT_TASKS` to `dict[int, set[asyncio.Task]]`.
- Add helper functions `_register_user_task(uid)` and `_unregister_user_task(uid, task)` to manage the set.
- Update `cmd_stop` to cancel all tasks in the set.
- Update `_run_tool_aware_completion`, `handle_document`, `handle_photo`, `handle_voice` to use the helpers.

**Tech Stack:** Python, asyncio, python-telegram-bot

---

### Task 1: Update USER_AGENT_TASKS declaration and add helpers

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update USER_AGENT_TASKS declaration**
Change the type hint and initialization around line 2424.

```python
USER_AGENT_TASKS: dict[int, set[asyncio.Task]] = {}
```

- [ ] **Step 2: Add helper functions**
Add `_register_user_task` and `_unregister_user_task` helpers near the declaration.

```python
def _register_user_task(uid: int) -> asyncio.Task:
    task = asyncio.current_task()
    if uid not in USER_AGENT_TASKS:
        USER_AGENT_TASKS[uid] = set()
    USER_AGENT_TASKS[uid].add(task)
    return task

def _unregister_user_task(uid: int, task: asyncio.Task):
    if uid in USER_AGENT_TASKS:
        USER_AGENT_TASKS[uid].discard(task)
        if not USER_AGENT_TASKS[uid]:
            USER_AGENT_TASKS.pop(uid, None)
```

- [ ] **Step 3: Commit**

### Task 2: Update cmd_stop

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update cmd_stop to cancel multiple tasks**
Update `cmd_stop` around line 3715 to iterate through the set of tasks and cancel each one.

```python
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _reset_ephemeral_state(context, clear_pending=True)
    uid = update.effective_user.id
    tasks = USER_AGENT_TASKS.get(uid, set()).copy()
    was_running = False
    for task in tasks:
        if not task.done():
            task.cancel()
            was_running = True
    USER_AGENT_TASKS.pop(uid, None)
    if was_running:
        await update.message.reply_text("⏹ Operation stopped.")
    else:
        await update.message.reply_text("هیچ عملیاتی در حال اجرا نیست.")
```

- [ ] **Step 2: Commit**

### Task 3: Update existing usages of USER_AGENT_TASKS

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Update _run_tool_aware_completion**
Update `_run_tool_aware_completion` (around line 2259) to use the new helpers and ensure cleanup in all exit paths.

- [ ] **Step 2: Update handle_voice, handle_message to cancel all tasks**
Update `handle_voice` (line 6877) and `handle_message` (line 7088) to cancel all existing tasks for the user.

- [ ] **Step 3: Commit**

### Task 4: Register long-running operations

**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1: Register handle_document**
Update `handle_document` (line 5575) to register its task.

- [ ] **Step 2: Register handle_photo**
Update `handle_photo` (line 6366) to register its task.

- [ ] **Step 3: Register handle_voice**
Update `handle_voice` (line 6875) to register its task.

- [ ] **Step 4: Commit**
