# Large File RAG Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify the document upload logic to automatically index files into the vector database (RAG) upon upload, even when a user is not explicitly inside a "Project". This allows the LLM to retrieve answers from large uploaded files in normal chat.

**Architecture:**
Currently, files are only indexed via RAG if `explicit_upload_requested` is true and a `project_id` exists. For normal chat uploads, the file's raw text is extracted (up to 10k chars) and injected directly into the prompt context, which fails for large files like 300-page PDFs.
We will modify the `Document` schema to accept a `chat_id` and update `rag.py` to use a `chat_id`-based collection name when a `project_id` is absent.

### Task 1: Update Database Schema
**Files:**
- Modify: `backend/app/models.py` (Document model)

- [ ] **Step 1:** Make `project_id` nullable and add `chat_id` to `Document`.
```python
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=True)
```

### Task 2: Refactor RAG Functions
**Files:**
- Modify: `backend/app/rag.py`
- Modify: `backend/app/services/rag_service.py`

- [ ] **Step 1:** Modify `index_document`, `index_document_async` to accept `chat_id` in addition to `project_id`, and determine the `collection_name`.
```python
def _get_collection_name(project_id: int | None, chat_id: int | None) -> str:
    if project_id:
        return f"project_{project_id}"
    elif chat_id:
        return f"chat_{chat_id}"
    raise ValueError("Either project_id or chat_id must be provided")
```
- [ ] **Step 2:** Update all ChromaDB `get_or_create_collection` and `get_collection` calls to use `_get_collection_name(project_id, chat_id)` instead of `f"project_{project_id}"`.
- [ ] **Step 3:** Update `search_documents` to accept `chat_id` and use the helper.

### Task 3: Update Background Task
**Files:**
- Modify: `backend/app/services/rag_service.py`

- [ ] **Step 1:** Update `background_index_document` to accept `chat_id: int = None`. Pass it down to `index_document_async`.

### Task 4: Update Bot File Upload Logic
**Files:**
- Modify: `backend/app/bot.py`

- [ ] **Step 1:** Update `_handle_document_upload` to always call `background_index_document`. If `explicit_upload_requested` is false and no `project_id` is active, pass `chat_id=chat_id`. It must create a `Document` record associated with `chat_id`. We should remove the old direct text extraction for large files and rely entirely on RAG for anything that can be indexed.
- [ ] **Step 2:** Update `_handle_document_upload` caption handling and `handle_message` RAG querying. If the user doesn't have an active project but they are in a chat, it should run `_search_with_config` using `chat_id=chat_id` so the LLM gets the RAG context.
