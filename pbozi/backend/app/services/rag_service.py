import asyncio
import logging
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import async_session
from app.models import Document, Project
from app.rag import index_document_async

logger = logging.getLogger(__name__)

async def background_index_document(
    project_id: int | None, 
    document_id: int, 
    file_path: str, 
    api_key: str = None, 
    model: str = None,
    provider: str = "google",
    base_url: str = None,
    callback=None,
    progress_callback=None,
    chat_id: int | None = None,
    pre_read_text: str = None
):
    """
    Background task to index a document.
    Updates the Document record status and handles errors.
    """
    async with async_session() as db:
        try:
            # 1. Update status to 'processing'
            doc = await db.get(Document, document_id)
            if not doc:
                logger.error(f"Document {document_id} not found for background indexing")
                return
            
            doc.status = "processing"
            await db.commit()
            
            # 2. Run the actual indexing concurrently
            chunk_count = await index_document_async(
                project_id, 
                document_id, 
                file_path, 
                api_key=api_key, 
                model=model,
                provider=provider,
                base_url=base_url,
                progress_callback=progress_callback,
                chat_id=chat_id,
                pre_read_text=pre_read_text
            )
            
            # 3. Update status to 'indexed'
            await db.refresh(doc)
            doc.chunk_count = chunk_count
            doc.status = "indexed"
            doc.error = None
            await db.commit()
            
            logger.info(f"Successfully indexed document {document_id} with {chunk_count} chunks")
            
            if callback:
                if asyncio.iscoroutinefunction(callback):
                    await callback(document_id, True)
                else:
                    callback(document_id, True)

        except Exception as e:
            logger.exception(f"Error indexing document {document_id}")
            async with async_session() as db_err:
                doc_err = await db_err.get(Document, document_id)
                if doc_err:
                    doc_err.status = "failed"
                    doc_err.error = str(e)
                    await db_err.commit()
            
            if callback:
                if asyncio.iscoroutinefunction(callback):
                    await callback(document_id, False, str(e))
                else:
                    callback(document_id, False, str(e))
