import hashlib
import json
import time
import uuid
from typing import Any, Dict

from django.http import Http404, StreamingHttpResponse
from django.core.files.storage import default_storage
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document, Module, ProcessingJob
from .serializers import DocumentUploadSerializer
from .tasks import process_document_pipeline


class DocumentUploadView(APIView):
    """Handle PDF uploads with idempotency."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]

        sha_hash = self._compute_sha256(upload)

        existing_job = (
            ProcessingJob.objects.select_related("document")
            .filter(idempotency_key=sha_hash)
            .order_by("-id")
            .first()
        )

        if existing_job:
            document = existing_job.document
            if existing_job.status in ("PENDING", "PROCESSING", "COMPLETED"):
                return Response(
                    self._build_response(document, existing_job),
                    status=status.HTTP_200_OK,
                )

            if existing_job.status == "FAILED":
                document = self._refresh_document_file(document, upload)
                self._reset_failed_job(existing_job)
                token = self._dispatch_pipeline(document.id, existing_job.id)
                existing_job.task_id = token
                existing_job.save(update_fields=["task_id"])
                return Response(
                    self._build_response(document, existing_job, processing_token=token),
                    status=status.HTTP_202_ACCEPTED,
                )

        document = self._create_document(request.user, upload)
        job = ProcessingJob.objects.create(
            document=document,
            idempotency_key=sha_hash,
            status="PENDING",
            retry_count=0,
            started_at=None,
            completed_at=None,
        )
        token = self._dispatch_pipeline(document.id, job.id)
        job.task_id = token
        job.save(update_fields=["task_id"])

        return Response(
            self._build_response(document, job, processing_token=token),
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------ helpers
    def _compute_sha256(self, upload) -> str:
        """Compute SHA256 hash of the uploaded file content."""
        sha = hashlib.sha256()
        for chunk in upload.chunks():
            sha.update(chunk)
        upload.seek(0)
        return sha.hexdigest()

    def _save_file(self, upload, user_id: int) -> Dict[str, Any]:
        """Persist the uploaded PDF to storage."""
        filename = f"documents/{user_id}/{uuid.uuid4()}.pdf"
        saved_path = default_storage.save(filename, upload)
        size = default_storage.size(saved_path) if hasattr(default_storage, "size") else upload.size
        return {"path": saved_path, "size": size}

    def _create_document(self, user, upload) -> Document:
        """Create and persist a new Document record."""
        saved = self._save_file(upload, user.id)
        return Document.objects.create(
            user=user,
            title=upload.name,
            file_path=saved["path"],
            file_size=saved["size"],
            status="PENDING",
            processing_progress={"current_stage": "queued"},
        )

    def _refresh_document_file(self, document: Document, upload) -> Document:
        """Replace document file on retry after a failure."""
        saved = self._save_file(upload, document.user.id)
        document.file_path = saved["path"]
        document.file_size = saved["size"]
        document.status = "PENDING"
        document.error_message = None
        document.processing_progress = {"current_stage": "queued"}
        document.save(
            update_fields=[
                "file_path",
                "file_size",
                "status",
                "error_message",
                "processing_progress",
                "updated_at",
            ]
        )
        return document

    def _reset_failed_job(self, job: ProcessingJob) -> None:
        """Reset a failed job to pending for retry."""
        job.status = "PENDING"
        job.started_at = None
        job.completed_at = None
        job.save(update_fields=["status", "started_at", "completed_at"])

    def _dispatch_pipeline(self, document_id: int, job_id: int):
        """
        Run the processing pipeline synchronously, without using Celery/Redis.

        We call the Celery task's `run` method directly so no broker or backend
        is touched.
        """
        process_document_pipeline.run(
            document_id=document_id,
            processing_job_id=job_id,
            inline=True,
        )
        return None

    def _build_response(self, document: Document, job: ProcessingJob, processing_token=None) -> Dict[str, Any]:
        """Build consistent response payload."""
        return {
            "document_id": document.id,
            "processing_token": processing_token or job.idempotency_key,
            "status": document.status,
        }


class DocumentStatusSSEView(APIView):
    """Server-Sent Events endpoint for document processing status.
    
    Supports both SSE (Accept: text/event-stream) and regular JSON polling.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int, *args, **kwargs):
        try:
            document = Document.objects.get(pk=pk, user=request.user)
        except Document.DoesNotExist as exc:
            raise Http404 from exc

        # Check if client wants SSE or regular JSON
        accept = request.META.get("HTTP_ACCEPT", "")
        if "text/event-stream" in accept:
            # SSE mode
            response = StreamingHttpResponse(
                self._event_stream(document.id, request.user.id),
                content_type="text/event-stream",
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            response["Connection"] = "keep-alive"
            return response
        else:
            # Regular JSON polling mode
            modules_ready = list(
                document.modules.filter(is_quiz_ready=True).values_list("id", flat=True)
            )
            return Response(
                {
                    "status": document.status,
                    "progress": document.processing_progress or {},
                    "modules_ready": modules_ready,
                    "error": document.error_message,
                }
            )

    def _format_event(self, payload: Dict[str, Any]) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    def _event_stream(self, document_id: int, user_id: int):
        """Yield SSE messages with periodic refresh."""
        timeout_seconds = 30
        poll_interval = 2
        start = time.monotonic()

        while time.monotonic() - start < timeout_seconds:
            try:
                document = (
                    Document.objects.filter(pk=document_id, user_id=user_id)
                    .prefetch_related("modules")
                    .get()
                )
            except Document.DoesNotExist:
                yield self._format_event({"error": "Document not found"})
                return

            modules_ready = list(
                document.modules.filter(is_quiz_ready=True).values_list("id", flat=True)
            )
            payload = {
                "status": document.status,
                "progress": document.processing_progress or {},
                "modules_ready": modules_ready,
                "error": document.error_message,
            }
            yield self._format_event(payload)

            if document.status in {"COMPLETED", "FAILED"}:
                break
            time.sleep(poll_interval)

        # keep-alive ping for reconnection logic
        yield "event: keepalive\ndata: ping\n\n"


class DocumentAnalyticsView(APIView):
    """Aggregate analytics for a document for a given user."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int, *args, **kwargs):
        from feedback.views import get_document_analytics  # avoid circular import

        analytics = get_document_analytics(request.user.id, pk)
        return Response(analytics)
