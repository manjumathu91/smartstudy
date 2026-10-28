

from io import BytesIO

import pymupdf
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Document, DocumentPage


@override_settings(MEDIA_ROOT="/tmp/smart_study_test_media")
class DocumentUploadTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.upload_url = "/api/documents/upload/"

    def create_pdf(self):
        """Create a small PDF with extractable text for testing."""
        buffer = BytesIO()

        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text(
                (72, 72),
                "Smart Study AI automated test document",
            )
            pdf.save(buffer)

        return buffer.getvalue()

    def test_upload_without_file_returns_400(self):
        response = self.client.post(
            self.upload_url,
            {},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"],
            "Please upload a PDF file.",
        )

    def test_upload_non_pdf_returns_400(self):
        uploaded_file = SimpleUploadedFile(
            "notes.txt",
            b"This is not a PDF.",
            content_type="text/plain",
        )

        response = self.client.post(
            self.upload_url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"],
            "Only PDF files are allowed.",
        )

    def test_upload_pdf_over_50_mb_returns_400(self):
        # A sparse file avoids allocating 50 MB of actual data.
        from tempfile import TemporaryFile

        from django.core.files.uploadedfile import File
        from documents.views import MAX_PDF_SIZE

        with TemporaryFile() as temp_file:
            temp_file.truncate(MAX_PDF_SIZE + 1)
            temp_file.seek(0)

            uploaded_file = File(temp_file, name="large.pdf")

            # Force the test upload object's size to exceed the limit.
            uploaded_file.size = MAX_PDF_SIZE + 1

            response = self.client.post(
                self.upload_url,
                {"file": uploaded_file},
                format="multipart",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"],
            "PDF must be 50 MB or smaller.",
        )

    def test_valid_pdf_upload_saves_document_and_pages(self):
        uploaded_file = SimpleUploadedFile(
            "study_test.pdf",
            self.create_pdf(),
            content_type="application/pdf",
        )

        response = self.client.post(
            self.upload_url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(DocumentPage.objects.count(), 1)

        document = Document.objects.get()
        page = DocumentPage.objects.get()

        self.assertIn(
            "Smart Study AI automated test document",
            document.extracted_text,
        )
        self.assertEqual(page.document_id, document.id)
        self.assertEqual(page.page_number, 1)
