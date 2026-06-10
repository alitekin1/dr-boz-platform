# Design Spec: Parallel Document Processor (PDP)

**Date:** 2026-05-02
**Status:** Approved
**Goal:** Optimize large document processing (PDF/TXT/MD) to handle 1,000+ page books efficiently through parallel extraction, concurrent embedding, and memory-safe streaming.

## 1. Problem Statement
The current document indexing system is sequential and memory-heavy.
- **Sequential:** One page at a time, one embedding batch at a time.
- **Memory Crash:** Extracts the full text of a PDF into a single string, causing OOM (Out of Memory) crashes on large files.
- **Speed:** Processing a 1,000-page book takes minutes due to sequential API calls.
- **Reliability:** Often results in "zero chunks" or "failed" status without clear recovery.

## 2. Proposed Architecture

### 2.1 Streaming Reader (Memory Safety)
Instead of `PdfReader(file_path).extract_text()`, we will implement a window-based extractor.
- **Window Size:** 50 pages.
- **Process:**
    1. Read pages 1-50.
    2. Extract, chunk, and queue for embedding.
    3. Clear memory.
    4. Move to pages 51-100.
- **Impact:** Flat memory footprint (~50-100MB max) regardless of file size.

### 2.2 Concurrent Embedding Pipeline (Extreme Speed)
Utilize `asyncio` to parallelize network-bound embedding requests.
- **Producer:** The Streaming Reader yields chunks into an `asyncio.Queue`.
- **Workers:** 10 concurrent async workers.
- **Dispatcher:** Pulls batches of 100-200 chunks from the queue and sends them to OpenRouter/OpenAI.
- **Backpressure:** Limit queue size to prevent excessive memory usage if extraction is faster than embedding.

### 2.3 OpenRouter/OpenAI Migration
- **Backend:** Update `rag.py` to support OpenAI-compatible `/v1/embeddings` endpoint.
- **Model:** Default to `openai/text-embedding-3-large` (via OpenRouter).
- **Concurrency:** Higher RPM (Requests Per Minute) limits on OpenRouter for paid tiers allow for "Extreme Speed".

### 2.4 Atomic Progress Updates
- **Incremental Counting:** Update `Document.chunk_count` in the database after every successful batch instead of at the very end.
- **Status Updates:** Add a `processing_metadata` field or log entries to show "Extraction 50%", "Embedding 20%".

## 3. Data Flow
1. **Frontend:** User uploads file.
2. **Main Routes:** Saves file and spawns `background_index_document`.
3. **RAG Service:** Orchestrates the PDP pipeline.
4. **Reader:** Streams text blocks.
5. **Chunker:** Splits text into semantic chunks.
6. **Parallel Workers:** Embed chunks concurrently.
7. **ChromaDB:** Persists vectors in batches.
8. **DB:** Finalizes document status as `indexed`.

## 4. Error Handling
- **Retries:** Exponential backoff for `429` (Rate Limit) or `5xx` (Provider Down) errors.
- **Cleanup:** If a document fails, partially indexed chunks are either kept (for resume) or cleared (standard).

## 5. Testing Plan
- **Unit Tests:** Mock OpenRouter API and verify parallel worker orchestration.
- **Integration Test:** Process a sample 50-page PDF and verify chunk count and ChromaDB retrieval.
- **Load Test:** Verify memory stability during processing of a 1,000+ page document.
