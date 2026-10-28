

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from documents.models import Document
from .views import PDFQuestionAnswerView


class PDFQuestionAnswerTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/learning/ask/"

    def test_empty_question_returns_400(self):
        response = self.client.post(
            self.url,
            {"question": "   "},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"],
            "Please enter a question.",
        )

    def test_missing_question_returns_400(self):
        response = self.client.post(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_question_over_1000_characters_returns_400(self):
        response = self.client.post(
            self.url,
            {"question": "a" * 1001},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"],
            "Question must be 1000 characters or fewer.",
        )

    def test_invalid_document_id_returns_400(self):
        response = self.client.post(
            self.url,
            {
                "question": "What is Tamil?",
                "document_id": "invalid",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"],
            "document_id must be a valid positive number.",
        )

    @patch("learning.views.search_pdf_pages")
    def test_no_matching_pages_returns_empty_sources(
        self,
        mock_search,
    ):
        mock_search.return_value = []

        response = self.client.post(
            self.url,
            {"question": "What is Tamil?"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["question"], "What is Tamil?")
        self.assertEqual(response.data["sources"], [])
        mock_search.assert_called_once()

    @patch("learning.views.generate_pdf_answer")
    @patch("learning.views.search_pdf_pages")
    def test_successful_answer_includes_sources(
        self,
        mock_search,
        mock_generate,
    ):
        mock_search.return_value = [
            {
                "document_id": 1,
                "title": "sample.pdf",
                "page_number": 16,
                "extracted_text": "Tamil is a classical language.",
                "score": 0.853,
                "needs_ocr": False,
            }
        ]
        mock_generate.return_value = "Tamil is a classical language."

        response = self.client.post(
            self.url,
            {"question": "What is Tamil?"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["answer"],
            "Tamil is a classical language.",
        )
        self.assertEqual(len(response.data["sources"]), 1)
        self.assertEqual(
            response.data["sources"][0]["page_number"],
            16,
        )
        self.assertEqual(
            response.data["sources"][0]["similarity_score"],
            0.853,
        )

        mock_generate.assert_called_once()
