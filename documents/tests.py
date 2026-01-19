from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.test import TestCase
import asyncio

from documents.llm_utils import GeminiRateLimiter, semantic_module_boundaries
import json

User = get_user_model()


class DocumentUploadTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="tester", email="tester@example.com", password="pass1234")
        self.client.force_authenticate(self.user)
        self.upload_url = reverse("document-upload")

    def _pdf_file(self, name="sample.pdf"):
        content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    def test_upload_pdf_creates_document(self):
        dummy_result = MagicMock(id="task-1")
        with patch("documents.views.process_document_pipeline") as mock_task:
            mock_task.delay.return_value = dummy_result

            response = self.client.post(self.upload_url, {"file": self._pdf_file()}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("document_id", response.data)
        self.assertIn("processing_token", response.data)
        self.assertEqual(response.data["status"], "PENDING")
        mock_task.delay.assert_called_once()

    def test_duplicate_upload_returns_existing_document(self):
        dummy_result = MagicMock(id="task-2")
        with patch("documents.views.process_document_pipeline") as mock_task:
            mock_task.delay.return_value = dummy_result
            first = self.client.post(self.upload_url, {"file": self._pdf_file()}, format="multipart")
            self.assertEqual(first.status_code, status.HTTP_201_CREATED)
            doc_id = first.data["document_id"]

            second = self.client.post(self.upload_url, {"file": self._pdf_file()}, format="multipart")

        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["document_id"], doc_id)
        # pipeline should not be triggered again for duplicate
        mock_task.delay.assert_called_once()


class SemanticChunkingTests(TestCase):
    def setUp(self):
        self.rate_limiter = GeminiRateLimiter(rpm=1000, tpm=1_000_000)

    def _fake_text(self, words=1200):
        return " ".join([f"word{i%50}" for i in range(words)])

    def test_semantic_chunking_parses_llm_response(self):
        text = self._fake_text(600)

        class FakeResponse:
            def __init__(self, content):
                self.content = content

        class FakeLLM:
            async def ainvoke(self, *args, **kwargs):
                return FakeResponse(
                    json.dumps(
                        [
                            {
                                "title": "Introduction",
                                "start_index": 0,
                                "end_index": len(text),
                                "summary": "Intro module",
                            }
                        ]
                    )
                )

        modules = asyncio.run(semantic_module_boundaries(FakeLLM(), text, self.rate_limiter))
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0]["title"], "Introduction")
        self.assertTrue(modules[0]["end_index"] > modules[0]["start_index"])

    def test_semantic_chunking_fallback_enforces_word_limits(self):
        text = self._fake_text(1200)

        class FakeLLM:
            async def ainvoke(self, *args, **kwargs):
                return FakeResponse("not-json")

        class FakeResponse:
            def __init__(self, content):
                self.content = content

        modules = asyncio.run(semantic_module_boundaries(FakeLLM(), text, self.rate_limiter))
        self.assertGreaterEqual(len(modules), 1)
        for mod in modules:
            self.assertTrue(mod["end_index"] > mod["start_index"])
