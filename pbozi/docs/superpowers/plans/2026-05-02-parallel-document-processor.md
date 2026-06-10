# Parallel Document Processor (PDP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a high-performance, memory-safe document processing pipeline that uses parallel extraction and concurrent embedding requests via OpenRouter/OpenAI.

**Architecture:** A producer-consumer pipeline where a streaming reader extracts text in page windows, a chunker generates semantic blocks, and multiple async workers concurrently embed and save these blocks to ChromaDB.

**Tech Stack:** Python, asyncio, pypdf, ChromaDB, OpenAI API (via OpenRouter).

---

### Task 1: Refactor Embedding Config to Support OpenAI/OpenRouter

**Files:**
- Modify: `backend/app/rag.py`
- Modify: `backend/app/models.py` (Verify defaults)

- [ ] **Step 1: Update `rag.py` to support OpenAI-compatible provider**
Modify `_get_embedding_fn` and related helpers to handle different providers.

```python
def _get_embedding_client(api_key: str = None, base_url: str = None):
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        api_key=api_key or DEFAULT_EMBEDDING_API_KEY,
        base_url=base_url or "https://openrouter.ai/api/v1"
    )

async def _embed_batch(texts: list[str], model: str, api_key: str, base_url: str):
    client = _get_embedding_client(api_key, base_url)
    response = await client.embeddings.create(
        model=model,
        input=texts
    )
    return [e.embedding for e in response.data]
```

- [ ] **Step 2: Commit**
```bash
git add backend/app/rag.py
git commit -m "feat: add OpenAI-compatible embedding support to RAG"
```

### Task 2: Implement Streaming PDF Reader

**Files:**
- Modify: `backend/app/rag.py`

- [ ] **Step 1: Create `_stream_read_pdf` generator**
Implement a generator that yields text from PDF pages in windows to save memory.

```python
def _stream_read_pdf(file_path: str, window_size: int = 50):
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    
    for start in range(0, total_pages, window_size):
        end = min(start + window_size, total_pages)
        text_parts = []
        for i in range(start, end):
            try:
                page_text = reader.pages[i].extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(f"Error extraction page {i}: {e}")
        yield "\n\n".join(text_parts), start, end
```

- [ ] **Step 2: Update `_read_file` to support streaming**
(Optional: for now we focus on PDF as it's the primary bottleneck).

- [ ] **Step 3: Commit**
```bash
git add backend/app/rag.py
git commit -m "feat: implement streaming PDF reader for memory safety"
```

### Task 3: Implement Concurrent Indexing Pipeline

**Files:**
- Modify: `backend/app/rag.py`
- Modify: `backend/app/services/rag_service.py`

- [ ] **Step 1: Rewrite `index_document` as `async` with workers**
Implement the producer-consumer logic with `asyncio.Queue` and `asyncio.gather`.

```python
async def index_document_async(project_id: int, document_id: int, file_path: str, 
                               api_key: str = None, model: str = None, base_url: str = None):
    # 1. Setup Queue and Semaphore
    queue = asyncio.Queue(maxsize=20)
    sem = asyncio.Semaphore(10) # 10 parallel workers
    total_chunks = 0

    # 2. Worker function
    async def worker():
        nonlocal total_chunks
        while True:
            batch = await queue.get()
            if batch is None: break
            async with sem:
                embeddings = await _embed_batch(batch['texts'], model, api_key, base_url)
                # Save to Chroma
                _save_to_chroma(project_id, batch['ids'], batch['texts'], batch['metadatas'], embeddings)
                total_chunks += len(batch['ids'])
                # Optional: Update DB progress here
            queue.task_done()

    # 3. Start workers
    workers = [asyncio.create_task(worker()) for _ in range(10)]
    
    # 4. Producer: Stream file and chunk
    for text_block, start, end in _stream_read_pdf(file_path):
        chunks = _chunk_text(text_block)
        # Push into queue in batches
        # ... logic to fill queue ...
    
    # 5. Cleanup
    await queue.join()
    for _ in range(10): await queue.put(None)
    await asyncio.gather(*workers)
    return total_chunks
```

- [ ] **Step 2: Update `background_index_document` to use the async version**

- [ ] **Step 3: Commit**
```bash
git add backend/app/rag.py backend/app/services/rag_service.py
git commit -m "feat: implement concurrent embedding pipeline"
```

### Task 4: Verification and Load Testing

- [ ] **Step 1: Write a load test script**
Create a script `backend/scripts/test_pdp_load.py` that processes a large dummy PDF (or a real one if available) and measures memory/time.

- [ ] **Step 2: Run verification**
Run: `cd backend && source venv/bin/activate && python3 scripts/test_pdp_load.py`
Expected: Completion without OOM and speed improvement of >3x.

- [ ] **Step 3: Final Commit**
```bash
git add backend/scripts/test_pdp_load.py
git commit -m "test: add load test for Parallel Document Processor"
```
