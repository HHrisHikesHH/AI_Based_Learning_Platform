"""Celery tasks for the documents pipeline."""
import asyncio
import json
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF
from celery import chain, shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import F
from django.utils import timezone

from .llm_utils import (
    GeminiRateLimiter,
    embed_batch_with_retry,
    get_chat_llm,
    get_embedding_model,
    semantic_module_boundaries,
    _fallback_split,
)
from .models import Document, Module, ModuleChunk, ProcessingJob
from quizzes.tasks import generate_quiz_for_module  # type: ignore

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _update_document(
    document_id: int,
    *,
    status: str | None = None,
    progress: Dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Atomically update document fields."""
    fields: Dict[str, Any] = {}
    if status is not None:
        fields["status"] = status
    if progress is not None:
        fields["processing_progress"] = progress
    if error is not None:
        fields["error_message"] = error
    if fields:
        Document.objects.filter(pk=document_id).update(**fields, updated_at=timezone.now())


def _update_job(
    job_id: int,
    *,
    status: str | None = None,
    task_id: str | None = None,
    completed: bool = False,
    increment_retry: bool = False,
    started: bool = False,
) -> None:
    """Atomically update processing job fields."""
    fields: Dict[str, Any] = {}
    if status is not None:
        fields["status"] = status
    if task_id is not None:
        fields["task_id"] = task_id
    if completed:
        fields["completed_at"] = timezone.now()
    if started:
        fields["started_at"] = timezone.now()
    if fields:
        ProcessingJob.objects.filter(pk=job_id).update(**fields)
    if increment_retry:
        ProcessingJob.objects.filter(pk=job_id).update(retry_count=F("retry_count") + 1)


def _mark_failed(document_id: int, job_id: int, message: str) -> None:
    """Mark the job and document as failed."""
    _update_document(
        document_id,
        status="FAILED",
        error=message,
        progress={"current_stage": "failed"},
    )
    _update_job(job_id, status="FAILED", completed=True, increment_retry=True)


def _extract_pdf_text_inline(document_id: int, job_id: int) -> Dict[str, Any]:
    """Extract text per page using PyMuPDF."""
    document = Document.objects.get(pk=document_id)
    file_path = (
        default_storage.path(document.file_path)
        if hasattr(default_storage, "path")
        else document.file_path
    )
    _update_document(
        document_id,
        status="EXTRACTING",
        progress={"current_stage": "extracting", "pages_processed": 0},
    )
    _update_job(job_id, status="PROCESSING")

    try:
        pdf = fitz.open(file_path)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(document_id, job_id, f"Unable to open PDF: {exc}")
        raise

    if pdf.needs_pass:
        _mark_failed(document_id, job_id, "PDF is password protected.")
        raise ValueError("PDF is password protected.")

    pages: List[Dict[str, Any]] = []
    total_pages = pdf.page_count
    for index in range(total_pages):
        page = pdf.load_page(index)
        text = page.get_text("text") or ""
        pages.append({"page": index + 1, "text": text})
        _update_document(
            document_id,
            progress={
                "current_stage": "extracting",
                "pages_processed": index + 1,
                "total_pages": total_pages,
            },
        )
    pdf.close()
    full_text = "\n\n".join(p["text"] for p in pages)
    return {"pages": pages, "text": full_text}


def _validate_module_bounds(module: Dict[str, Any], text: str) -> Tuple[str, str]:
    start = int(module.get("start_index", 0))
    end = int(module.get("end_index", 0))
    start = max(start, 0)
    end = max(end, start + 1)
    content = text[start:end]
    summary = module.get("summary") or ""
    return content, summary


async def _chunk_document_async(text: str) -> List[Dict[str, Any]]:
    """Async helper to call Gemini for semantic module boundaries (no DB access)."""
    api_key = getattr(settings, "GEMINI_API_KEY", None) or None
    if not api_key or not text.strip():
        return []

    llm = get_chat_llm(api_key=api_key)
    rate_limiter = GeminiRateLimiter()
    return await semantic_module_boundaries(llm, text, rate_limiter)


def _chunk_document_inline(extracted: Dict[str, Any], document_id: int, job_id: int) -> List[Dict[str, Any]]:
    """Chunk document into semantic modules using fallback splitter (no LLM/async)."""
    text = extracted.get("text", "")
    if not text.strip():
        _mark_failed(document_id, job_id, "No text extracted from document.")
        return []

    _update_document(
        document_id,
        status="CHUNKING",
        progress={
            "current_stage": "chunking",
            "chunks_completed": 0,
            "total_chunks": 0,
        },
    )

    modules = _fallback_split(text)
    total = len(modules)
    _update_document(
        document_id,
        progress={
            "current_stage": "chunking",
            "chunks_completed": 0,
            "total_chunks": total,
        },
    )

    semantic_chunks: List[Dict[str, Any]] = []
    for idx, mod in enumerate(modules, start=1):
        content, summary = _validate_module_bounds(mod, text)
        semantic_chunks.append(
            {
                "title": mod.get("title") or f"Module {idx}",
                "content": content,
                "summary": summary,
                "order": idx,
            }
        )
        _update_document(
            document_id,
            progress={
                "current_stage": "chunking",
                "chunks_completed": idx,
                "total_chunks": total,
            },
        )

    return semantic_chunks


def _create_modules_with_embeddings_inline(
    semantic_chunks: List[Dict[str, Any]], document_id: int, job_id: int
) -> List[int]:
    """Create modules, chunks, embeddings, summaries and trigger quiz generation."""
    api_key = getattr(settings, "GEMINI_API_KEY", None) or None
    if not api_key:
        _mark_failed(document_id, job_id, "GEMINI_API_KEY is not configured.")
        return []

    llm = get_chat_llm(api_key=api_key)
    embedding_model = get_embedding_model(api_key=api_key)
    rate_limiter = GeminiRateLimiter()

    total_modules = len(semantic_chunks)
    _update_document(
        document_id,
        status="GENERATING_MODULES",
        progress={
            "current_stage": "generating_modules",
            "modules_completed": 0,
            "total_modules": total_modules,
        },
    )

    def split_text_for_embeddings(text: str, max_words: int = 512, overlap: int = 50) -> List[str]:
        """Simple word-based splitter to approximate token limits."""
        words = text.split()
        chunks: List[str] = []
        start = 0
        while start < len(words):
            end = min(start + max_words, len(words))
            chunk_words = words[start:end]
            if not chunk_words:
                break
            chunks.append(" ".join(chunk_words))
            if end == len(words):
                break
            start = max(end - overlap, 0)
        return chunks

    created_module_ids: List[int] = []

    for idx, module_payload in enumerate(semantic_chunks, start=1):
        # Create Module record
        module = Module.objects.create(
            document_id=document_id,
            title=module_payload["title"],
            summary=module_payload.get("summary") or "",
            module_order=idx,
            total_chunks=0,
            is_quiz_ready=False,
        )

        # Split into embedding-sized chunks
        text_chunks = split_text_for_embeddings(module_payload["content"])
        batch_size = 10
        embeddings_data: List[Tuple[str, List[float]]] = []
        for i in range(0, len(text_chunks), batch_size):
            batch = text_chunks[i : i + batch_size]
            vectors = asyncio.run(
                embed_batch_with_retry(batch, embedding_model, rate_limiter)
            )
            embeddings_data.extend(zip(batch, vectors))

        # Persist ModuleChunk entries
        module_chunks = []
        for order, (chunk_text, vector) in enumerate(embeddings_data, start=1):
            chunk_kwargs = {
                "module": module,
                "content": chunk_text,
                "chunk_order": order,
                "metadata": {},
                "created_at": timezone.now(),
            }
            if ModuleChunk._meta.get_field("embedding").get_internal_type() == "VectorField":  # type: ignore
                chunk_kwargs["embedding"] = vector
            else:
                chunk_kwargs["embedding"] = json.dumps(vector)
            module_chunks.append(ModuleChunk(**chunk_kwargs))
        ModuleChunk.objects.bulk_create(module_chunks)

        module.total_chunks = len(module_chunks)
        # Generate summary if missing
        if not module.summary:
            try:
                asyncio.run(
                    rate_limiter.acquire(
                        estimated_tokens=min(len(module_payload["content"]) // 4, 4000)
                    )
                )
                summary_resp = llm.invoke(
                    f"Summarize this learning module in 2 sentences:\n\n{module_payload['content'][:4000]}"
                )
                module.summary = getattr(summary_resp, "content", "") or str(summary_resp)
            except Exception:
                # Fallback: simple truncated summary without LLM
                module.summary = module_payload["content"][:200]
        module.save(update_fields=["total_chunks", "summary"])

        # Update document progress
        _update_document(
            document_id,
            progress={
                "current_stage": "generating_modules",
                "modules_completed": idx,
                "total_modules": total_modules,
            },
        )

        # Trigger quiz generation synchronously (no Celery needed in dev)
        try:
            from quizzes.tasks import generate_quiz_for_module

            # Call the task function directly (not as Celery task)
            quiz_id = generate_quiz_for_module(module.id)
            if quiz_id:
                logger.info("Quiz %s generated for module %s", quiz_id, module.id)
            else:
                logger.warning("Quiz generation returned None for module %s", module.id)
        except Exception as exc:
            logger.error("Quiz generation failed for module %s: %s", module.id, exc, exc_info=True)

        created_module_ids.append(module.id)

    _update_document(
        document_id,
        status="COMPLETED",
        progress={
            "current_stage": "completed",
            "modules_completed": total_modules,
            "total_modules": total_modules,
        },
        error=None,
    )
    _update_job(job_id, status="COMPLETED", completed=True)
    return created_module_ids


def _generate_all_quizzes_inline(module_ids: List[int], document_id: int, job_id: int) -> None:
    """Placeholder quiz generation step (handled per-module dispatch)."""
    _update_job(job_id, status="COMPLETED", completed=True)


# ---------------------------------------------------------------------------
# Celery Tasks
# ---------------------------------------------------------------------------
@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def extract_pdf_text(self, document_id: int, processing_job_id: int) -> Dict[str, Any]:
    """Celery task wrapper for PDF text extraction."""
    try:
        return _extract_pdf_text_inline(document_id, processing_job_id)
    except Exception as exc:  # noqa: BLE001
        if self.request.retries >= self.max_retries:
            _mark_failed(document_id, processing_job_id, str(exc))
        _update_job(processing_job_id, increment_retry=True)
        raise


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def intelligent_chunk_document(self, extracted: Dict[str, Any], document_id: int, processing_job_id: int) -> List[Dict[str, Any]]:
    """Celery task wrapper for intelligent chunking."""
    try:
        return _chunk_document_inline(extracted, document_id, processing_job_id)
    except Exception as exc:  # noqa: BLE001
        if self.request.retries >= self.max_retries:
            _mark_failed(document_id, processing_job_id, str(exc))
        _update_job(processing_job_id, increment_retry=True)
        raise


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def create_modules_with_embeddings(self, chunks: List[Dict[str, Any]], document_id: int, processing_job_id: int) -> List[int]:
    """Celery task wrapper for module creation with embeddings."""
    try:
        return _create_modules_with_embeddings_inline(chunks, document_id, processing_job_id)
    except Exception as exc:  # noqa: BLE001
        if self.request.retries >= self.max_retries:
            _mark_failed(document_id, processing_job_id, str(exc))
        _update_job(processing_job_id, increment_retry=True)
        raise


@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
)
def generate_all_quizzes(self, module_ids: List[int], document_id: int, processing_job_id: int) -> str:
    """Celery task wrapper for quiz generation."""
    try:
        _generate_all_quizzes_inline(module_ids, document_id, processing_job_id)
        return "COMPLETED"
    except Exception as exc:  # noqa: BLE001
        if self.request.retries >= self.max_retries:
            _mark_failed(document_id, processing_job_id, str(exc))
        _update_job(processing_job_id, increment_retry=True)
        raise


@shared_task(bind=True, max_retries=3, retry_backoff=True, retry_backoff_max=60)
def process_document_pipeline(self, document_id: int, processing_job_id: int, inline: bool = False) -> Dict[str, Any]:
    """
    Kick off the document processing pipeline.

    When inline=True, tasks run synchronously (useful for local/dev fallback).
    """
    _update_job(processing_job_id, status="PROCESSING", task_id=self.request.id, started=True)
    if inline:
        extracted = _extract_pdf_text_inline(document_id, processing_job_id)
        chunks = _chunk_document_inline(extracted, document_id, processing_job_id)
        module_ids = _create_modules_with_embeddings_inline(chunks, document_id, processing_job_id)
        _generate_all_quizzes_inline(module_ids, document_id, processing_job_id)
        return {"status": "COMPLETED", "mode": "inline"}

    try:
        workflow = chain(
            extract_pdf_text.s(document_id=document_id, processing_job_id=processing_job_id),
            intelligent_chunk_document.s(document_id=document_id, processing_job_id=processing_job_id),
            create_modules_with_embeddings.s(document_id=document_id, processing_job_id=processing_job_id),
            generate_all_quizzes.s(document_id=document_id, processing_job_id=processing_job_id),
        )
        async_result = workflow.apply_async()
        _update_job(processing_job_id, task_id=async_result.id)
        return {"status": "STARTED", "task_id": async_result.id}
    except Exception as exc:  # noqa: BLE001
        _mark_failed(document_id, processing_job_id, str(exc))
        raise

