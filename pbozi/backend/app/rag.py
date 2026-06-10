"""
RAG Module — v3: Google Embedding API + ChromaDB (using built-in GoogleGenerativeAiEmbeddingFunction)
Admin can configure embedding model and provider via DB.
"""

import os
import asyncio
import logging
import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from app.config import BOT_TOKEN
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Default embedding config
DEFAULT_EMBEDDING_API_KEY = "AIzaSyARosrfBA3pcVU77j8zqIJklU6Aj317VBQ"
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")

_client = None


def get_chroma_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def _get_embedding_fn(api_key: str = None, model: str = None, provider: str = "google", base_url: str = None):
    """Get embedding function for ChromaDB."""
    if provider == "google":
        api_key = api_key or DEFAULT_EMBEDDING_API_KEY
        model = model or DEFAULT_EMBEDDING_MODEL
        
        return embedding_functions.GoogleGenerativeAiEmbeddingFunction(
            api_key=api_key,
            model_name=model,
            task_type="retrieval_document",
        )
    else:
        # OpenAI/OpenRouter support
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=model or "text-embedding-3-small",
            api_base=base_url or "https://api.openai.com/v1"
        )


def _get_query_embedding_fn(api_key: str = None, model: str = None, provider: str = "google", base_url: str = None):
    """Get embedding function optimized for queries (retrieval_query task type)."""
    if provider == "google":
        api_key = api_key or DEFAULT_EMBEDDING_API_KEY
        model = model or DEFAULT_EMBEDDING_MODEL
        
        return embedding_functions.GoogleGenerativeAiEmbeddingFunction(
            api_key=api_key,
            model_name=model,
            task_type="retrieval_query",
        )
    else:
        # OpenAI/OpenRouter support
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            model_name=model or "text-embedding-3-small",
            api_base=base_url or "https://api.openai.com/v1"
        )


def _get_embedding_client(api_key: str = None, base_url: str = None):
    """Get AsyncOpenAI client for embedding."""
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url or "https://api.openai.com/v1",
        timeout=60.0  # 60 second timeout for embedding requests
    )


async def _embed_batch(texts: list[str], model: str, api_key: str, base_url: str = None):
    """Embed a batch of texts using OpenAI-compatible API asynchronously."""
    max_retries = 5
    retry_delay = 2.0
    last_exc = None
    for attempt in range(max_retries):
        try:
            client = _get_embedding_client(api_key, base_url)
            logger.info(f"Embedding {len(texts)} texts with model={model}, base_url={base_url}, attempt={attempt+1}")
            response = await client.embeddings.create(
                input=texts,
                model=model
            )
            logger.info(f"Successfully embedded {len(texts)} texts")
            return [item.embedding for item in response.data]
        except Exception as e:
            last_exc = e
            error_str = str(e).lower()
            is_retryable = any(kw in error_str for kw in [
                "rate limit", "quota", "429", "timeout", "deadline",
                "resource exhausted", "unavailable", "service unavailable"
            ])
            if not is_retryable or attempt == max_retries - 1:
                logger.error(f"Embedding failed (attempt {attempt+1}/{max_retries}, retryable={is_retryable}): {e}")
                raise
            logger.warning(
                f"Embedding retry {attempt+1}/{max_retries} in {retry_delay}s: {e}"
            )
            await asyncio.sleep(retry_delay)
            retry_delay *= 2
            logger.warning(
                f"_embed_batch retry {attempt+1}/{max_retries} "
                f"(delay={retry_delay}s): {e}"
            )
            await asyncio.sleep(retry_delay)
            retry_delay *= 2
    raise last_exc


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks, trying to break at sentence boundaries."""
    import re
    chunks = []
    sentences = re.split(r'(?<=[.!?؟。\n])\s+', text)
    
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            words = current_chunk.split()
            overlap_words = words[-overlap//4:] if len(words) > overlap//4 else []
            current_chunk = " ".join(overlap_words) + " " + sentence
        else:
            current_chunk += " " + sentence if current_chunk else sentence
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    if not chunks:
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start = end - overlap
    
    return [c for c in chunks if c]


def _stream_read_pdf(file_path: str, window_size: int = 50):
    """
    Generator that reads a PDF in chunks of pages for memory safety.
    Yields (text_block, start_page, end_page).
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        reader = PdfReader(file_path)
        num_pages = len(reader.pages)
        
        for i in range(0, num_pages, window_size):
            pages = []
            start_page = i
            end_page = min(i + window_size, num_pages)
            
            for page_idx in range(start_page, end_page):
                try:
                    page = reader.pages[page_idx]
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                except Exception as e:
                    logger.warning(f"Error extracting text from page {page_idx} of {file_path}: {e}")
            
            if pages:
                yield "\n\n".join(pages), start_page, end_page - 1
    except Exception as e:
        logger.error(f"PdfReader failed for {file_path}: {e}")
        raise ValueError(f"Could not read PDF file: {e}")


def _read_file(file_path: str) -> str:
    """Read content from a file."""
    import logging
    logger = logging.getLogger(__name__)
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".pdf":
        try:
            # Use streaming reader to collect all text
            blocks = []
            for text_block, _, _ in _stream_read_pdf(file_path):
                blocks.append(text_block)
            return "\n\n".join(blocks)
        except Exception as e:
            logger.error(f"Streaming PDF reader failed for {file_path}, attempting fallback: {e}")
            # Fallback to MarkItDown if available
            try:
                from markitdown import MarkItDown
                md = MarkItDown()
                result = md.convert(file_path)
                return result.text_content
            except Exception as e2:
                logger.error(f"Fallback MarkItDown also failed for {file_path}: {e2}")
                raise ValueError(f"Could not read PDF file: {e}")
                
    elif ext in (".txt", ".md", ".csv"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    else:
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(file_path)
            return result.text_content
        except Exception as e:
            logger.error(f"MarkItDown error for {file_path}: {e}")
            raise ValueError(f"Unsupported or unparseable file type: {ext}")


def _get_collection_name(project_id: int | None, chat_id: int | None) -> str:
    if project_id:
        return f"project_{project_id}"
    elif chat_id:
        return f"chat_{chat_id}"
    raise ValueError("Either project_id or chat_id must be provided")

def index_document(project_id: int | None, document_id: int, file_path: str,
                    api_key: str = None, model: str = None, provider: str = "google", base_url: str = None, chat_id: int | None = None) -> int:
    """Index a document into ChromaDB using Google or OpenAI embeddings. Returns chunk count."""
    text = _read_file(file_path)
    
    if not text.strip():
        return 0
    
    chunks = _chunk_text(text)
    
    if not chunks:
        return 0

    client = get_chroma_client()
    embedding_fn = _get_embedding_fn(api_key, model, provider, base_url)
    
    collection_name = _get_collection_name(project_id, chat_id)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
        embedding_function=embedding_fn,
    )

    ids = [f"doc_{document_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"document_id": document_id, "chunk_index": i} for i in range(len(chunks))]

    # Add in batches of 100
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i:i+batch_size],
            documents=chunks[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
        )

    return len(chunks)


async def index_document_async(project_id: int | None, document_id: int, file_path: str,
                               api_key: str = None, model: str = None, provider: str = "google", 
                               base_url: str = None, progress_callback=None, chat_id: int | None = None,
                               pre_read_text: str = None) -> int:
    """
    Index a document into ChromaDB using a concurrent pipeline.
    Uses a producer-consumer model with 3 workers for high throughput with rate limit safety.
    """
    if progress_callback:
        await progress_callback("reading", 0, 0)

    client = get_chroma_client()
    embedding_fn = _get_embedding_fn(api_key, model, provider, base_url)
    
    collection_name = _get_collection_name(project_id, chat_id)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
        embedding_function=embedding_fn,
    )

    queue = asyncio.Queue(maxsize=50)
    chunk_counter = 0
    total_chunks_estimated = 0
    worker_count = 3  # Reduced from 10 to avoid Google API rate limits
    first_error = None
    
    async def worker(worker_id):
        nonlocal chunk_counter, first_error
        while True:
            batch = await queue.get()
            if batch is None:
                queue.task_done()
                break
            
            batch_texts, batch_ids, batch_metadatas = batch
            try:
                if provider != "google" and api_key:
                    # Manual embedding for OpenAI/OpenRouter to be truly async
                    embeddings = await _embed_batch(batch_texts, model or "text-embedding-3-small", api_key, base_url)
                    collection.add(
                        ids=batch_ids,
                        documents=batch_texts,
                        metadatas=batch_metadatas,
                        embeddings=embeddings
                    )
                else:
                    # For Google, use retry logic with exponential backoff
                    max_retries = 5
                    retry_delay = 2.0
                    last_exc = None
                    for attempt in range(max_retries):
                        try:
                            await asyncio.to_thread(
                                collection.add,
                                ids=batch_ids,
                                documents=batch_texts,
                                metadatas=batch_metadatas
                            )
                            break  # Success
                        except Exception as e:
                            last_exc = e
                            error_str = str(e).lower()
                            # Check if it's a rate limit or timeout error
                            is_retryable = any(kw in error_str for kw in [
                                "rate limit", "quota", "429", "timeout", "deadline",
                                "resource exhausted", "unavailable", "service unavailable"
                            ])
                            if not is_retryable or attempt == max_retries - 1:
                                raise
                            logger.warning(
                                f"Worker {worker_id} retry {attempt+1}/{max_retries} for batch "
                                f"(delay={retry_delay}s): {e}"
                            )
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                chunk_counter += len(batch_texts)
                if progress_callback:
                    await progress_callback("indexing", chunk_counter, total_chunks_estimated)
            except Exception as e:
                logger.error(f"Worker {worker_id} error indexing batch: {e}")
                if first_error is None:
                    first_error = e
            finally:
                queue.task_done()

    # Start workers
    logger.info(f"Starting {worker_count} workers for indexing document {document_id}")
    workers = [asyncio.create_task(worker(i)) for i in range(worker_count)]

    # Producer
    ext = os.path.splitext(file_path)[1].lower()
    batch_size = 20 # Optimal batch size for concurrency/latency balance
    producer_error = None
    
    logger.info(f"Producer starting for {file_path}, ext={ext}")
    try:
        if ext == ".pdf":
            if progress_callback:
                await progress_callback("chunking", 0, 0)
            current_batch_texts = []
            current_batch_ids = []
            current_batch_metadatas = []
            chunk_idx = 0
            
            for text_block, start_page, end_page in _stream_read_pdf(file_path):
                chunks = _chunk_text(text_block)
                logger.info(f"PDF block: pages {start_page}-{end_page}, extracted {len(chunks)} chunks")
                for chunk in chunks:
                    current_batch_texts.append(chunk)
                    current_batch_ids.append(f"doc_{document_id}_chunk_{chunk_idx}")
                    current_batch_metadatas.append({
                        "document_id": document_id, 
                        "chunk_index": chunk_idx,
                        "pages": f"{start_page}-{end_page}"
                    })
                    chunk_idx += 1
                    
                    if len(current_batch_texts) >= batch_size:
                        await queue.put((current_batch_texts, current_batch_ids, current_batch_metadatas))
                        await asyncio.sleep(0.5)  # Small delay to avoid overwhelming the API
                        current_batch_texts, current_batch_ids, current_batch_metadatas = [], [], []
            
            if current_batch_texts:
                await queue.put((current_batch_texts, current_batch_ids, current_batch_metadatas))
            
            total_chunks_estimated = chunk_idx
        else:
            # For non-PDF, read and chunk (non-streaming for simplicity for now)
            text = pre_read_text if pre_read_text else await asyncio.to_thread(_read_file, file_path)
            if progress_callback:
                await progress_callback("chunking", 0, 0)
            chunks = _chunk_text(text)
            total_chunks_estimated = len(chunks)
            logger.info(f"Non-PDF: extracted {len(chunks)} chunks")
            for i in range(0, len(chunks), batch_size):
                batch_texts = chunks[i:i+batch_size]
                batch_ids = [f"doc_{document_id}_chunk_{j}" for j in range(i, i+len(batch_texts))]
                batch_metadatas = [{"document_id": document_id, "chunk_index": j} for j in range(i, i+len(batch_texts))]
                await queue.put((batch_texts, batch_ids, batch_metadatas))
                await asyncio.sleep(0.5)  # Small delay to avoid overwhelming the API
                
    except Exception as e:
        logger.error(f"Producer error for {file_path}: {e}")
        producer_error = e
        # Signal workers to exit even on producer error
    finally:
        # Signal workers to stop
        logger.info(f"Producer finished for {file_path}, signaling workers")
        for _ in range(worker_count):
            await queue.put(None)
        
        # Wait for all batches to be processed and workers to finish
        await queue.join()
        await asyncio.gather(*workers)

    logger.info(f"Indexing complete for document {document_id}, total chunks: {chunk_counter}")
    if producer_error:
        raise producer_error
    if first_error:
        raise first_error
    if chunk_counter == 0:
        raise ValueError("No content could be extracted or indexed from the file.")

    return chunk_counter


def delete_document(project_id: int, document_id: int, api_key: str = None, model: str = None, provider: str = "google", base_url: str = None):
    """Delete a document's chunks from ChromaDB index."""
    client = get_chroma_client()
    embedding_fn = _get_embedding_fn(api_key, model, provider, base_url)
    try:
        collection = client.get_collection(
            name=f"project_{project_id}",
            embedding_function=embedding_fn,
        )
        collection.delete(where={"document_id": document_id})
    except Exception:
        # Collection might not exist, that's fine
        pass


def copy_project_index(source_project_id: int, target_project_id: int, document_id_map: dict[int, int],
                       api_key: str = None, model: str = None, provider: str = "google", base_url: str = None) -> int:
    """Copy existing Chroma chunks from one project collection to another."""
    if not document_id_map:
        return 0

    client = get_chroma_client()
    embedding_fn = _get_embedding_fn(api_key, model, provider, base_url)
    try:
        source_collection = client.get_collection(
            name=f"project_{source_project_id}",
            embedding_function=embedding_fn,
        )
    except Exception:
        return 0

    target_collection = client.get_or_create_collection(
        name=f"project_{target_project_id}",
        metadata={"hnsw:space": "cosine"},
        embedding_function=embedding_fn,
    )

    try:
        existing = source_collection.get(include=["documents", "metadatas", "embeddings"])
    except Exception:
        return 0

    ids = existing.get("ids") or []
    documents = existing.get("documents") or []
    metadatas = existing.get("metadatas") or []
    embeddings = existing.get("embeddings")

    target_ids = []
    target_documents = []
    target_metadatas = []
    target_embeddings = []
    for index, source_id in enumerate(ids):
        metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
        old_document_id = metadata.get("document_id")
        try:
            old_document_id = int(old_document_id)
        except (TypeError, ValueError):
            continue
        new_document_id = document_id_map.get(old_document_id)
        if not new_document_id:
            continue
        chunk_index = metadata.get("chunk_index", 0)
        metadata["document_id"] = new_document_id
        target_ids.append(f"doc_{new_document_id}_chunk_{chunk_index}")
        target_documents.append(documents[index] if index < len(documents) else "")
        target_metadatas.append(metadata)
        if embeddings is not None:
            target_embeddings.append(embeddings[index])

    if not target_ids:
        return 0

    batch_size = 5000
    for i in range(0, len(target_ids), batch_size):
        end = i + batch_size
        batch_kwargs = {
            "ids": target_ids[i:end],
            "documents": target_documents[i:end],
            "metadatas": target_metadatas[i:end],
        }
        if embeddings is not None:
            batch_kwargs["embeddings"] = target_embeddings[i:end]
        target_collection.add(**batch_kwargs)
    return len(target_ids)


def search_documents(project_id: int | None, query: str, n_results: int = 5,
                     api_key: str = None, model: str = None, provider: str = "google", base_url: str = None, chat_id: int | None = None) -> list[dict]:
    """Search indexed documents for a project using semantic search."""
    client = get_chroma_client()
    query_fn = _get_query_embedding_fn(api_key, model, provider, base_url)
    
    collection_name = _get_collection_name(project_id, chat_id)

    try:
        # Use the document embedding function for the collection metadata
        embedding_fn = _get_embedding_fn(api_key, model, provider, base_url)
        collection = client.get_collection(
            name=collection_name,
            embedding_function=embedding_fn,
        )
    except Exception as e:
        logger.error(f"Error getting collection for {collection_name}: {e}")
        return []

    # For querying, we use the query function which has task_type=retrieval_query for Google.
    # We manually embed the query and use the results to ensure task_type is respected.
    try:
        if provider == "google":
            # For Google, task_type='retrieval_query' is required for the query
            query_embeddings = query_fn([query])
            results = collection.query(query_embeddings=query_embeddings, n_results=n_results)
        else:
            # For OpenAI/OpenRouter, the standard query_texts approach is fine
            results = collection.query(query_texts=[query], n_results=n_results)
    except Exception as e:
        logger.error(f"Error querying collection for {collection_name}: {e}")
        # Fallback: try one more time with a simple query if specialized fails
        try:
            results = collection.query(query_texts=[query], n_results=n_results)
        except Exception as e2:
            logger.error(f"Final fallback query failed for {collection_name}: {e2}")
            return []

    output = []
    if results.get("documents") and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            output.append({
                "content": doc,
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })
    return output
