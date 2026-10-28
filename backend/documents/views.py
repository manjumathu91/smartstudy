

import os
import hashlib
from pathlib import Path
import pymupdf
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from learning.semantic_search import index_pdf_pages
from .models import Document, DocumentPage,SavedNote, DocumentAnalysis

from learning.models import (
    QuizAttempt,
    SavedFlashcardSet,
    SavedStudyPlan,
)

from .serializers import DocumentSerializer,SavedNoteSerializer,DocumentAnalysisSerializer
from .ocr_utils import extract_page_text_with_ocr
from .document_extraction import extract_document_text

# Maximum PDF upload size: 50 MB
MAX_PDF_SIZE = 150 * 1024 * 1024


def calculate_file_hash(file_obj):
    """Calculate SHA-256 hash for a stored PDF file."""
    sha256 = hashlib.sha256()

    file_obj.open("rb")
    try:
        for chunk in file_obj.chunks():
            sha256.update(chunk)
    finally:
        file_obj.close()

    return sha256.hexdigest()


class DocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded_file = request.FILES.get("file")

        # 1. Validate uploaded file
        if not uploaded_file:
            return Response(
                {"error": "Please upload a PDF file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not uploaded_file.name.lower().endswith(".pdf"):
            return Response(
                {"error": "Only PDF files are allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded_file.size > MAX_PDF_SIZE:
            return Response(
                {"error": "PDF must be 150 MB or smaller."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 2. Read PDF and calculate its content hash
            pdf_bytes = uploaded_file.read()
            file_hash = hashlib.sha256(pdf_bytes).hexdigest()

            # 3. Check for duplicate PDFs belonging to this user
            existing_document = Document.objects.filter(
                owner=request.user,
                file_hash=file_hash,
            ).first()

            if existing_document:
                return Response(
                    {
                        "duplicate": True,
                        "message": (
                            "This PDF has already been uploaded."
                        ),
                        "document": DocumentSerializer(
                            existing_document
                        ).data,
                    },
                    status=status.HTTP_200_OK,
                )

            # 4. Check older documents that have no saved hash yet
            old_documents = Document.objects.filter(
                owner=request.user,
                file_hash="",
            ).exclude(file="")

            for old_document in old_documents:
                try:
                    old_hash = calculate_file_hash(old_document.file)

                    if old_hash == file_hash:
                        # Store the hash for future duplicate checks
                        Document.objects.filter(
                            pk=old_document.pk
                        ).update(file_hash=file_hash)

                        return Response(
                            {
                                "duplicate": True,
                                "message": (
                                    "This PDF has already been uploaded."
                                ),
                                "document": DocumentSerializer(
                                    old_document
                                ).data,
                            },
                            status=status.HTTP_200_OK,
                        )

                    # Save the calculated hash for future checks
                    Document.objects.filter(
                        pk=old_document.pk
                    ).update(file_hash=old_hash)

                except (OSError, ValueError) as exc:
                    print(
                        f"Could not check old document "
                        f"{old_document.pk}: {exc}"
                    )

            page_records = []
            ocr_pages = []

            # 5. Extract text from every page
            with pymupdf.open(
                stream=pdf_bytes,
                filetype="pdf",
            ) as pdf:

                if pdf.needs_pass:
                    return Response(
                        {
                            "error": (
                                "This PDF is password-protected. "
                                "Please upload an unlocked PDF."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                for page_number, page in enumerate(pdf, start=1):
                    normal_text = page.get_text("text").strip()
                    page_text = normal_text

                    native_errors = normal_text.count("\ufffd")
                    should_try_ocr = (
                        not normal_text or native_errors > 0
                    )

                    if should_try_ocr:
                        try:
                            ocr_text = extract_page_text_with_ocr(
                                page,
                                languages="tam+eng",
                            ).strip()

                            ocr_errors = ocr_text.count("\ufffd")

                            if ocr_text and (
                                not normal_text
                                or ocr_errors < native_errors
                            ):
                                page_text = ocr_text
                                ocr_pages.append(page_number)

                        except Exception as exc:
                            # Preserve native text if OCR fails
                            print(
                                f"OCR failed on page "
                                f"{page_number}: {exc}"
                            )

                    page_records.append(
                        {
                            "page_number": page_number,
                            "extracted_text": page_text,
                            "needs_ocr": (
                                not bool(page_text)
                                or "\ufffd" in page_text
                            ),
                        }
                    )

            # 6. Create combined document text
            extracted_text = "\n\n".join(
                record["extracted_text"]
                for record in page_records
                if record["extracted_text"]
            ).strip()

            if not extracted_text:
                return Response(
                    {
                        "error": (
                            "No readable text could be extracted. "
                            "The PDF may need OCR or manual review."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

      
            # 7. Save document and pages for the logged-in user
            uploaded_file.seek(0)

            material_title = request.data.get("title", "").strip()
            subject = request.data.get("subject", "").strip()
            language = request.data.get("language", "Both").strip()
            class_level = request.data.get("class_level", "").strip()
            document_type = request.data.get(
            "document_type", "general"
      ).strip()

            if document_type not in ["textbook", "general"]:
              return Response(
             {"error": "Please select a valid document type."},
              status=status.HTTP_400_BAD_REQUEST,
    )

            if not material_title:
                material_title = uploaded_file.name.rsplit(".", 1)[0]

            if language not in ["Tamil", "English", "Both"]:
                return Response(
                    {"error": "Please select a valid language."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                document = Document.objects.create(
                    owner=request.user,
                    title=material_title,
                    file=uploaded_file,
                    file_hash=file_hash,
                    extracted_text=extracted_text,
                    subject=subject,
                    language=language,
                    class_level=class_level,
                    document_type=document_type,
                )

                DocumentPage.objects.bulk_create(
                    [
                        DocumentPage(
                            document=document,
                            page_number=record["page_number"],
                            extracted_text=record["extracted_text"],
                            needs_ocr=record["needs_ocr"],
                        )
                        for record in page_records
                    ]
                )

                        # 7(a).1 Index the saved PDF pages in local Qdrant
            try:
                index_pdf_pages(document_id=document.id)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "PDF page indexing failed for document %s",
                    document.id,
                )
            # 8. Return upload details
            response_data = DocumentSerializer(document).data
            response_data["pages_processed"] = len(page_records)
            response_data["pages_saved"] = len(page_records)
            response_data["ocr_pages"] = ocr_pages
            response_data["duplicate"] = False

            return Response(
                response_data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            print(f"PDF upload failed: {exc}")

            return Response(
                {
                    "error": (
                        "Could not read or save this PDF. "
                        "Please check whether the file is valid."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class DocumentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        documents = Document.objects.filter(
            owner=request.user
        ).order_by("-uploaded_at")

        serializer = DocumentSerializer(documents, many=True)
        return Response(serializer.data)


class DocumentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        document = get_object_or_404(
            Document,
            pk=pk,
            owner=request.user,
        )

        serializer = DocumentSerializer(document)
        return Response(serializer.data)

    def delete(self, request, pk):
        document = get_object_or_404(
            Document,
            pk=pk,
            owner=request.user,
        )

        file_path = document.file.path if document.file else None
        document.delete()

        if file_path and os.path.isfile(file_path):
            os.remove(file_path)

        return Response(
            {"message": "Document deleted successfully."},
            status=status.HTTP_200_OK,
        )


class DocumentPageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id, page_number):
        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        page = get_object_or_404(
            DocumentPage,
            document=document,
            page_number=page_number,
        )

        return Response(
            {
                "document_id": document.id,
                "document_title": document.title,
                "page_number": page.page_number,
                "text": page.extracted_text,
                "text_length": len(page.extracted_text),
                "needs_ocr": page.needs_ocr,
            },
            status=status.HTTP_200_OK,
        )


class DocumentTopicSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        topic = request.query_params.get("q", "").strip()

        if not topic:
            return Response(
                {
                    "error": (
                        "Please provide a topic using ?q=your_topic"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = int(request.query_params.get("limit", 10))
        except (ValueError, TypeError):
            return Response(
                {"error": "Limit must be a valid number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if limit < 1 or limit > 50:
            return Response(
                {"error": "Limit must be between 1 and 50."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        matching_pages = (
            DocumentPage.objects.filter(
                document__owner=request.user,
                extracted_text__icontains=topic,
            )
            .select_related("document")
            .order_by("document__title", "page_number")
        )

        total_results = matching_pages.count()
        results = []

        for page in matching_pages[:limit]:
            text = page.extracted_text
            position = text.casefold().find(topic.casefold())

            if position >= 0:
                start = max(0, position - 150)
                end = min(
                    len(text),
                    position + len(topic) + 250,
                )
                snippet = text[start:end]
            else:
                snippet = text[:400]

            results.append(
                {
                    "document_id": page.document.id,
                    "document_title": page.document.title,
                    "page_number": page.page_number,
                    "snippet": snippet,
                    "needs_ocr": page.needs_ocr,
                }
            )

        return Response(
            {
                "query": topic,
                "total_results": total_results,
                "returned_results": len(results),
                "limit": limit,
                "results": results,
            }
        )



class SavedNoteListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notes = (
            SavedNote.objects
            .filter(owner=request.user)
            .select_related("document")
        )

        serializer = SavedNoteSerializer(notes, many=True)
        return Response(serializer.data)

    def post(self, request):
        document_id = request.data.get("document_id")

        if not document_id:
            return Response(
                {"error": "document_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        payload = request.data.copy()
        payload.pop("document_id", None)

        serializer = SavedNoteSerializer(
            data={
                **payload,
                "document": document.pk,
            }
        )
        serializer.is_valid(raise_exception=True)

        note = serializer.save(
            owner=request.user,
            document=document,
        )

        return Response(
            SavedNoteSerializer(note).data,
            status=status.HTTP_201_CREATED,
        )


class SavedNoteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        note = get_object_or_404(
            SavedNote.objects.select_related("document"),
            pk=pk,
            owner=request.user,
        )

        return Response(SavedNoteSerializer(note).data)
    
class MultiFormatDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    MAX_FILE_SIZE = 50 * 1024 * 1024

    def post(self, request):
        uploaded_file = request.FILES.get("file")

        if not uploaded_file:
            return Response(
                {"error": "Please select a file to upload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded_file.size > self.MAX_FILE_SIZE:
            return Response(
                {"error": "File size must not exceed 50 MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = Path(uploaded_file.name).name
        extension = Path(filename).suffix.lower()

        allowed_extensions = {
            ".pdf", ".docx", ".xlsx", ".xls",
            ".csv", ".png", ".jpg", ".jpeg",
        }

        if extension not in allowed_extensions:
            return Response(
                {"error": "Unsupported file type."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            file_bytes = uploaded_file.read()
            extracted_text = extract_document_text(
                file_bytes,
                filename,
            )

            if not extracted_text.strip():
                return Response(
                    {
                        "error": (
                            "No readable text was found. "
                            "Check the file or its OCR quality."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            uploaded_file.seek(0)

            title = (
                request.data.get("title") or Path(filename).stem
            ).strip()

            if not title:
                title = Path(filename).stem

            subject = (request.data.get("subject") or "").strip()
            language = (request.data.get("language") or "Both").strip()
            class_level = (
                request.data.get("class_level") or ""
            ).strip()
            document_type = (
             request.data.get("document_type") or "general"
    ).strip()

            if document_type not in ["textbook", "general"]:
              return Response(
             {"error": "Please select a valid document type."},
             status=status.HTTP_400_BAD_REQUEST,
    )
            file_hash = hashlib.sha256(file_bytes).hexdigest()

            with transaction.atomic():
                document = Document.objects.create(
                    owner=request.user,
                    title=title,
                    file=uploaded_file,
                    subject=subject,
                    language=language,
                    class_level=class_level,
                    file_hash=file_hash,
                    extracted_text=extracted_text,
                    document_type=document_type,
                )

                analysis = DocumentAnalysis.objects.create(
                    owner=request.user,
                    document=document,
                    analysis_type="extraction",
                    title=f"Extracted content - {title}",
                    extracted_text=extracted_text,
                )

            return Response(
                {
                    "message": "File uploaded and text extracted successfully.",
                    "document": DocumentSerializer(document).data,
                    "analysis": DocumentAnalysisSerializer(
                        analysis
                    ).data,
                },
                status=status.HTTP_201_CREATED,
            )

        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            return Response(
                {
                    "error": (
                        "Could not process this file. "
                        "Check the server terminal for details."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class DocumentAnalysisListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses = DocumentAnalysis.objects.filter(
            owner=request.user
        ).select_related("document")

        serializer = DocumentAnalysisSerializer(
            analyses,
            many=True,
        )

        return Response(serializer.data)


class DocumentAnalysisDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        analysis = get_object_or_404(
            DocumentAnalysis,
            pk=pk,
            owner=request.user,
        )

        serializer = DocumentAnalysisSerializer(analysis)

        return Response(serializer.data)

class MyLibraryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        items = []

        # 1. Saved Notes
        saved_notes = (
            SavedNote.objects
            .filter(owner=user)
            .select_related("document")
        )

        seen_notes = set()

        for note in saved_notes:
            content = note.content or ""

            item = {
                "id": f"saved-note-{note.id}",
                "item_type": "notes",
                "title": note.title,
                "document_id": note.document_id,
                "document_title": note.document.title,
                "content": content,
                "note_type": note.note_type,
                "topic": note.topic,
                "page_number": note.page_number,
                "language": note.language,
                "created_at": note.created_at.isoformat(),
                "updated_at": note.updated_at.isoformat(),
            }

            items.append(item)

            seen_notes.add((
                note.document_id,
                (note.title or "").strip(),
                content.strip(),
            ))

        # 2. Notes saved through DocumentAnalysis
        analyses = (
            DocumentAnalysis.objects
            .filter(owner=user)
            .exclude(analysis_type="extraction")
            .select_related("document")
        )

        for analysis in analyses:
            content = (
                analysis.notes or analysis.summary or ""
            ).strip()

            if not content:
                continue

            dedupe_key = (
                analysis.document_id,
                (analysis.title or "").strip(),
                content,
            )

            # Avoid duplicate notes when title and content match
            if dedupe_key in seen_notes:
                continue

            items.append({
                "id": f"analysis-{analysis.id}",
                "item_type": "notes",
                "title": analysis.title,
                "document_id": analysis.document_id,
                "document_title": analysis.document.title,
                "content": content,
                "note_type": analysis.analysis_type,
                "topic": "",
                "page_number": None,
                "language": analysis.document.language,
                "created_at": analysis.created_at.isoformat(),
                "updated_at": analysis.updated_at.isoformat(),
            })

            seen_notes.add(dedupe_key)

                        # 3. Saved Quiz and Revision Attempts
        quizzes = (
            QuizAttempt.objects
            .filter(user=user)
            .select_related("document")
            .prefetch_related("answers")
            .order_by("-created_at")
        )

        for quiz in quizzes:
            answer_records = list(
                quiz.answers.all().order_by("id")
            )

            # Full question data, including saved question content
            questions_data = (
                quiz.questions_data
                if isinstance(quiz.questions_data, list)
                else []
            )

            question_details = []

            for index, question_data in enumerate(questions_data):
                if not isinstance(question_data, dict):
                    question_data = {
                        "question": str(question_data)
                    }

                answer_record = (
                    answer_records[index]
                    if index < len(answer_records)
                    else None
                )

                question_details.append({
                    **question_data,
                    "question_number": index + 1,
                    "question": question_data.get(
                        "question",
                        question_data.get("question_text", "")
                    ),
                    "topic": (
                        answer_record.topic
                        if answer_record else question_data.get("topic", "")
                    ),
                    "selected_answer": (
                        answer_record.selected_answer
                        if answer_record else ""
                    ),
                    "correct_answer": (
                        answer_record.correct_answer
                        if answer_record else question_data.get(
                            "correct_answer",
                            question_data.get("answer", "")
                        )
                    ),
                    "is_correct": (
                        answer_record.is_correct
                        if answer_record else None
                    ),
                })

            is_revision = quiz.quiz_type == "revision"

            items.append({
                "id": (
                    f"revision-{quiz.id}"
                    if is_revision
                    else f"quiz-{quiz.id}"
                ),
                "item_type": (
                    "revision" if is_revision else "quizzes"
                ),
                "title": (
                    f"Revision - {quiz.document.title}"
                    if is_revision
                    else f"Quiz - {quiz.document.title}"
                ),
                "document_id": quiz.document_id,
                "document_title": quiz.document.title,
                "quiz_type": quiz.quiz_type,
                "total_questions": quiz.total_questions,
                "correct_answers": quiz.correct_answers,
                "wrong_answers": max(
                    quiz.total_questions - quiz.correct_answers, 0
                ),
                "score": quiz.score,
                "accuracy": quiz.accuracy,
                "questions": question_details,
                "questions_data": questions_data,
                "answers": [
                    {
                        "question": answer.question,
                        "topic": answer.topic,
                        "selected_answer": answer.selected_answer,
                        "correct_answer": answer.correct_answer,
                        "is_correct": answer.is_correct,
                    }
                    for answer in answer_records
                ],
                "created_at": quiz.created_at.isoformat(),
                "updated_at": quiz.created_at.isoformat(),
            })
       

        # 4. Saved Flashcard Sets
        flashcard_sets = (
            SavedFlashcardSet.objects
            .filter(user=user)
            .select_related("document")
        )

        for card_set in flashcard_sets:
            items.append({
                "id": f"flashcards-{card_set.id}",
                "item_type": "flashcards",
                "title": card_set.title,
                "document_id": card_set.document_id,
                "document_title": card_set.document.title,
                "language": card_set.language,
                "page_start": card_set.page_start,
                "page_end": card_set.page_end,
                "cards": card_set.cards,
                "created_at": card_set.created_at.isoformat(),
                "updated_at": card_set.updated_at.isoformat(),
            })

        # 5. Saved Study Plans
        study_plans = (
            SavedStudyPlan.objects
            .filter(user=user)
        )

        for plan in study_plans:
            items.append({
                "id": f"plan-{plan.id}",
                "item_type": "plans",
                "title": plan.title,
                "exam_date": plan.exam_date.isoformat(),
                "daily_hours": plan.daily_hours,
                "topics": plan.topics,
                "plan": plan.plan,
                "days_available": plan.days_available,
                "total_study_hours": plan.total_study_hours,
                "created_at": plan.created_at.isoformat(),
                "updated_at": plan.updated_at.isoformat(),
            })

        # 6. Newest items first
        items.sort(
            key=lambda item: item["updated_at"],
            reverse=True,
        )

        counts = {
            "notes": sum(
                item["item_type"] == "notes" for item in items
            ),
            "quizzes": sum(
                item["item_type"] == "quizzes" for item in items
            ),
            "flashcards": sum(
                item["item_type"] == "flashcards" for item in items
            ),
            "plans": sum(
                item["item_type"] == "plans" for item in items
            ),
            "revision": sum(
                  item["item_type"] == "revision" for item in items
),
        }

        return Response({
            "items": items,
            "counts": counts,
            "total_items": len(items),
        })
