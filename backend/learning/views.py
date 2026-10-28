import logging
from django.utils import timezone
from django.db.models.functions import TruncDate
from django.db.models import Count, Q ,Sum
from datetime import date, timedelta
from groq import RateLimitError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import (
    QuizAttempt,
    QuizAnswer,
    SavedFlashcardSet,
    SavedStudyPlan,
    StudyTimeSession,
    StudyChat,
    StudyChatMessage,
    StudyActivity,
)

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from documents.models import Document, DocumentPage,DocumentAnalysis
import unicodedata
from .ai_utils import (
    generate_pdf_answer,
    generate_study_content,
    detect_pdf_lessons,
    generate_general_answer,
    generate_quiz_questions,
    generate_flashcards,generate_topic_revision_questions,
)
from .semantic_search import search_pdf_pages
from .pdf_utils import create_notes_pdf

logger = logging.getLogger(__name__)


def normalize_lesson_title(value):
    """Normalize lesson titles before comparing them."""
    if not isinstance(value, str):
        return ""

    value = unicodedata.normalize("NFKC", value)

    # Remove invisible Unicode formatting characters.
    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Cf"
    )

    # Normalize repeated spaces and compare without case differences.
    return " ".join(value.split()).casefold()

def is_pdf_related_question(question):
    text = question.casefold().strip()

    pdf_phrases = [
        # English
        "this pdf",
        "the pdf",
        "selected pdf",
        "uploaded pdf",
        "this document",
        "the document",
        "in this book",
        "this textbook",
        "this lesson",
        "this chapter",
        "from the pdf",
        "according to the pdf",
        "summarize this",
        "what is in the pdf",
        "what does the pdf contain",
        "in the uploaded file",
        "selected document",
        "the selected document",
        "selected file",
        "the selected file",
        "extract the key points",
        "key points from",
        "document summary",
        "summarize the document",
        "summarise the document",
        "analyse the document",
        "analyze the document",
        "analyse the topic",
        "analyze the topic",
        "use the selected document",
        "from the selected document",

        # Tamil / Tanglish
        "இந்த pdf",
        "இந்தப் pdf",
        "இந்த ஆவணம்",
        "இந்த புத்தகம்",
        "இந்தப் புத்தகம்",
        "இந்த பாடம்",
        "இந்தப் பாடம்",
        "இந்த பாடத்தில்",
        "இந்தப் பாடத்தில்",
        "இந்த அத்தியாயம்",
        "இந்தப் பக்கத்தில்",
        "இந்த கோப்பில்",
        "இந்தக் கோப்பில்",
        "pdf ல",
        "pdf ல்",
        "pdf la",
        "pdf la enna",
        "pdf pathi",
        "intha pdf",
        "intha book",
        "intha lesson",
        "intha chapter",
        "intha paadathula",
        "intha padathula",
    ]

    return any(phrase in text for phrase in pdf_phrases)











class PDFQuestionAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import re

        question = request.data.get("question", "")
        document_id = request.data.get("document_id")

        # 1. Validate question
        if not isinstance(question, str) or not question.strip():
            return Response(
                {"error": "Please enter a question."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        question = question.strip()

        if len(question) > 1000:
            return Response(
                {"error": "Question must be 1000 characters or fewer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Detect Tamil script for bilingual messages
        has_tamil = any(
            "\u0B80" <= char <= "\u0BFF"
            for char in question
        )

        def get_redirect_message():
            if has_tamil:
                return (
                    "இந்தக் கேள்விக்குத் தேவையான தகவல் "
                    "நீங்கள் தேர்ந்தெடுத்த PDF-ல் கிடைக்கவில்லை. "
                    "பொதுவான TNPSC படிப்பு உதவி, கணித விளக்கம் "
                    "அல்லது படிப்பு வழிகாட்டுதலுக்கு "
                    "AI Study Chat-ஐப் பயன்படுத்துங்கள்."
                )

            return (
                "I couldn't find enough relevant information "
                "in your selected PDF to answer this question. "
                "For general TNPSC study help, Maths explanations, "
                "or study guidance, please use AI Study Chat."
            )

        def redirect_response(message_type="pdf_content_not_found"):
            return Response(
                {
                    "question": question,
                    "answer": get_redirect_message(),
                    "sources": [],
                    "suggest_ai_study_chat": True,
                    "message_type": message_type,
                },
                status=status.HTTP_200_OK,
            )

        # 3. Selected PDF is required
        if document_id is None or document_id == "":
            message = (
                "முதலில் ஒரு PDF-ஐத் தேர்ந்தெடுக்கவும்."
                if has_tamil
                else "Please select a PDF first."
            )

            return Response(
                {
                    "error": message,
                    "suggest_ai_study_chat": False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Validate document ID
        try:
            document_id = int(document_id)
            if document_id <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response(
                {"error": "Please select a valid PDF."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5. Verify PDF ownership
        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        # 6. Detect question type
        lower_question = question.lower()

        page_match = re.search(
            r"\b(?:page|பக்கம்)\s*[-:#]?\s*(\d+)\b",
            question,
            re.IGNORECASE,
        )

        is_lesson_list = any(
            phrase in lower_question
            for phrase in [
                "all lessons",
                "list lessons",
                "lesson names",
                "topics in this pdf",
                "topics in the pdf",
                "என்னென்ன பாடங்கள்",
                "பாடங்களின் பெயர்கள்",
                "பாடங்கள் என்ன",
                "தலைப்புகள் என்ன",
            ]
        )

        is_question_generation = any(
            phrase in lower_question
            for phrase in [
                "2 mark",
                "2-mark",
                "two mark",
                "1 mark",
                "1-mark",
                "one mark",
                "important questions",
                "மதிப்பெண் வினாக்கள்",
                "இரண்டு மதிப்பெண்",
                "ஒரு மதிப்பெண்",
                "முக்கிய வினாக்கள்",
                "வினாக்கள் உருவாக்கு",
            ]
        )

        if page_match:
            page_number = int(page_match.group(1))
            search_question = (
                f"Page {page_number} of the selected PDF. "
                f"Retrieve the exact page content. "
                f"User question: {question}"
            )
        elif is_lesson_list:
            search_question = (
                "Find lesson names, chapter headings, "
                "table of contents, and page numbers. "
                f"User request: {question}"
            )
        elif is_question_generation:
            search_question = (
                "Find relevant lesson content, definitions, "
                "facts, and key points for question generation. "
                f"User request: {question}"
            )
        else:
            search_question = question

        # 7. Search only the selected PDF
        try:
            selected = search_pdf_pages(
                question=search_question,
                limit=(
                    10
                    if is_lesson_list or is_question_generation
                    else 5
                ),
                document_id=document.id,
                owner_id=request.user.id,
            )
        except Exception:
            logger.exception("Ask AI PDF search failed")
            return Response(
                {
                    "error": (
                        "Could not search this PDF. "
                        "Please try again."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 8. For page-specific questions, keep only the requested page
        if page_match:
            requested_page = int(page_match.group(1))
            selected = [
                item
                for item in selected
                if item.get("page_number") == requested_page
            ]

        # 9. Build context and sources from retrieved pages
        context_parts = []
        sources = []

        for item in selected:
            page_text = (
                item.get("extracted_text") or ""
            ).strip()

            if not page_text:
                continue

            page_number = item.get("page_number")

            context_parts.append(
                f"Document: {document.title}\n"
                f"Page: {page_number}\n"
                f"Content:\n{page_text[:5000]}"
            )

            sources.append(
                {
                    "document_id": document.id,
                    "document_title": document.title,
                    "page_number": page_number,
                    "similarity_score": round(
                        float(item.get("score") or 0), 3
                    ),
                }
            )

        context = "\n\n--- PDF PAGE ---\n\n".join(
            context_parts
        )

        # 10. No relevant readable content
        if not context.strip():
            return redirect_response()

        # 11. Generate an answer strictly from the PDF context
        answer_question = f"""
You are Ask AI, a patient teacher.

Answer using ONLY the supplied content from the user's
selected PDF.

Rules:
1. Never invent facts, lesson names, answers, or page numbers.
2. If the context does not support the answer, say that
   the available PDF information is insufficient.
3. Answer in the same language as the user's question.
4. Explain simply and clearly.
5. For page-specific questions, explain only the requested
   page. Do not use other pages as a substitute.
6. For lesson lists, list only lesson names supported by
   the supplied context.
7. For 1-mark questions, give short answers.
8. For 2-mark questions, give concise answers with key points.
9. For important questions, summaries, and revision notes,
   use only the supplied PDF content.
10. Do not guarantee that a question will appear in an exam.

Selected document: {document.title}

User question:
{question}

PDF context:
{context}
"""

        # 12. Generate answer
        try:
            answer = generate_pdf_answer(
                answer_question,
                context,
            )
        except Exception:
            logger.exception(
                "Ask AI PDF answer generation failed"
            )
            return Response(
                {
                    "error": (
                        "AI could not generate an answer. "
                        "Please try again."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


               
        # 13. Detect an insufficient-context response
        normalized_answer = (answer or "").strip().lower()

        insufficient_phrases = [
            # English
            "information is insufficient",
            "not enough information",
            "couldn't find",
            "could not find",
            "not available in the provided context",
            "not mentioned in the pdf",
            "does not contain information",
            "no information about",
            "the answer is not available",
            "not enough relevant information",

            # Tamil
            "pdf-ல் தகவல் இல்லை",
            "தகவல் கிடைக்கவில்லை",
            "போதுமான தகவல் இல்லை",
            "போதுமான தகவல்கள் இல்லை",
            "குறிப்பிடப்படவில்லை",
            "பதில் இல்லை",
            "பதில்கள் எதுவும் இல்லை",
            "அதில் இல்லை",
            "அதில் இடம்பெறவில்லை",
            "தகவல்கள் எதுவும் இடம்பெறவில்லை",
            "நேரடியான விளக்கம் அதில் இல்லை",
            "நேரடியான விளக்கம் இல்லை",
            "தகவல்கள் போதாது",
            "தகவல் இதற்குப் போதுமானதாக இல்லை",
            "pdf தகவல் இதற்குப் போதுமானதாக இல்லை",
            "pdf தகவல்களின்படி",
            "வழங்கப்பட்ட pdf ஆவணத்தில் உள்ள தகவல்களின்படி",
            "வழங்கப்பட்ட pdf தகவல்களின்படி",
        ]

        if any(
            phrase in normalized_answer
            for phrase in insufficient_phrases
        ):
            return redirect_response()

        # 14. Return PDF answer and sources
        return Response(
            {
                "question": question,
                "answer": answer,
                "sources": sources,
                "document_id": document.id,
                "document_title": document.title,
                "suggest_ai_study_chat": False,
                "message_type": "pdf_answer",
            },
            status=status.HTTP_200_OK,
        )




class AIStudyChatHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        chats = StudyChat.objects.filter(
            user=request.user
        ).order_by("-updated_at")

        results = []

        for chat in chats[:100]:
            results.append({
                "chat_id": chat.id,
                "title": chat.title,
                "mode": chat.mode,
                "language": chat.language,
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
            })

        return Response({"chats": results})




class AIStudyChatDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, chat_id):
        try:
            chat = StudyChat.objects.get(
                id=chat_id,
                user=request.user,
            )
        except StudyChat.DoesNotExist:
            return Response(
                {"error": "Chat not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        messages = chat.messages.all().order_by("created_at", "id")

        return Response({
            "chat_id": chat.id,
            "title": chat.title,
            "mode": chat.mode,
            "language": chat.language,
            "messages": [
                {
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "mode": message.mode,
                    "created_at": message.created_at,
                }
                for message in messages
            ],
        })

    def delete(self, request, chat_id):
        try:
            chat = StudyChat.objects.get(
                id=chat_id,
                user=request.user,
            )
        except StudyChat.DoesNotExist:
            return Response(
                {"error": "Chat not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        chat.delete()

        return Response(
            {"message": "Chat deleted successfully."},
            status=status.HTTP_200_OK,
        )



class StudyContentView(APIView):
    permission_classes = [IsAuthenticated]
    def rate_limit_response(self):
        return Response(
        {
            "error": (
                "AI usage limit reached. Please try again "
                "when the provider quota becomes available."
            )
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )

    
    def auto_save_analysis(
        self,
        request,
        document,
        analysis_type,
        title,
        content,
        extracted_text="",
    ):
        analysis, _ = DocumentAnalysis.objects.update_or_create(
            owner=request.user,
            document=document,
            analysis_type=analysis_type,
            title=title,
            defaults={
                "summary": (
                    content if analysis_type == "summary" else ""
                ),
                "notes": (
                    content if analysis_type != "summary" else ""
                ),
                "extracted_text": extracted_text,
            },
        )
        return analysis.id


    def post(self, request):
        document_id = request.data.get("document_id")
        content_type = request.data.get("content_type", "notes")
        language = request.data.get("language", "Tamil")
        page_offset = request.data.get("page_offset", 0)
        page_number = request.data.get("page_number")

        if content_type not in ("notes", "summary"):
            return Response(
                {"error": "content_type must be 'notes' or 'summary'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if language not in ("Tamil", "English", "Both"):
            return Response(
                {"error": "language must be Tamil, English, or Both."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            document_id = int(document_id)
            if document_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "A valid document_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page_offset = int(page_offset)
            if page_offset < 0 or page_offset % 3 != 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "page_offset must be 0, 3, 6, 9, and so on."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        all_pages = (
            DocumentPage.objects
            .filter(document=document)
            .exclude(extracted_text="")
            .order_by("page_number")
        )
        total_pages = all_pages.count()

        if total_pages == 0:
            return Response(
                {"error": "No readable pages were found in this PDF."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # PAGE-WISE CONTENT
        if page_number is not None:
            try:
                page_number = int(page_number)
                if page_number < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return Response(
                    {"error": "page_number must be a positive integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            page = all_pages.filter(page_number=page_number).first()

            if page is None:
                return Response(
                    {"error": "No readable text was found on that page."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            context = f"Page {page.page_number}:\n{page.extracted_text}"

            try:
                result = generate_study_content(
                    content_type="notes",
                    context=context,
                    language=language,
                )
            except RateLimitError:
                logger.warning("Groq rate limit reached for page-wise notes.")
                return self.rate_limit_response()
            except Exception:
                logger.exception("Page-wise content generation failed.")
                return Response(
                    {"error": "Could not generate content for this page."},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            saved_analysis_id = self.auto_save_analysis(
                request=request,
                document=document,
                analysis_type="page_notes",
                title=(
                    f"Page {page_number} Notes - "
                    f"{document.title} ({language})"
                ),
                content=result,
                extracted_text=context,
            )

            return Response({
                "document_id": document.id,
                "document_title": document.title,
                "content_type": "page",
                "language": language,
                "page_number": page_number,
                "page_start": page_number,
                "page_end": page_number,
                "total_pages": total_pages,
                "has_next": False,
                "next_page_offset": None,
                "content": result,
                "saved_analysis_id": saved_analysis_id,
            })

        # SUMMARY: three readable pages per AI request
        if content_type == "summary":
            summaries = []

            for offset in range(0, total_pages, 3):
                batch = list(all_pages[offset:offset + 3])
                if not batch:
                    continue

                batch_context = "\n\n".join(
                    f"Page {page.page_number}:\n{page.extracted_text}"
                    for page in batch
                )

                try:
                    batch_summary = generate_study_content(
                        content_type="summary",
                        context=batch_context,
                        language=language,
                    )
                except RateLimitError:
                    logger.warning(
                        "Groq rate limit reached at summary offset %s.",
                        offset,
                    )
                    return self.rate_limit_response()
                except Exception:
                    logger.exception(
                        "Summary batch failed at offset %s.", offset
                    )
                    return Response(
                        {"error": "Could not summarize the entire PDF."},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

                summaries.append(
                    f"Pages {batch[0].page_number}-"
                    f"{batch[-1].page_number}:\n{batch_summary}"
                )

            combined_context = "\n\n".join(summaries)

            try:
                result = generate_study_content(
                    content_type="summary",
                    context=combined_context,
                    language=language,
                )
            except RateLimitError:
                logger.warning("Groq rate limit reached for final summary.")
                return self.rate_limit_response()
            except Exception:
                logger.exception("Final summary generation failed.")
                return Response(
                    {"error": "Could not combine the PDF summaries."},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
         
            saved_analysis_id = self.auto_save_analysis(
                request=request,
                document=document,
                analysis_type="summary",
                title=f"Summary - {document.title} ({language})",
                content=result,
                extracted_text=combined_context,
            )

            return Response({
                "document_id": document.id,
                "document_title": document.title,
                "content_type": "summary",
                "language": language,
                "page_start": 1,
                "page_end": all_pages.last().page_number,
                "total_pages": total_pages,
                "has_next": False,
                "next_page_offset": None,
                "content": result,
                 "saved_analysis_id": saved_analysis_id,
            })

        # STUDY NOTES: three readable pages per request
        selected_pages = list(all_pages[page_offset:page_offset + 3])

        if not selected_pages:
            return Response(
                {
                    "error": "No more readable pages are available.",
                    "total_pages": total_pages,
                    "page_offset": page_offset,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        context = "\n\n".join(
            f"Page {page.page_number}:\n{page.extracted_text}"
            for page in selected_pages
        )

        try:
            result = generate_study_content(
                content_type="notes",
                context=context,
                language=language,
            )
        except RateLimitError:
            logger.warning(
                "Groq rate limit reached for study notes at offset %s.",
                page_offset,
            )
            return self.rate_limit_response()
        except Exception:
            logger.exception("Study notes generation failed.")
            return Response(
                {"error": "Could not generate study notes."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        saved_analysis_id = self.auto_save_analysis(
            request=request,
            document=document,
            analysis_type="study_notes",
            title=(
                f"Study Notes Pages "
                f"{selected_pages[0].page_number}-"
                f"{selected_pages[-1].page_number} - "
                f"{document.title} ({language})"
            ),
            content=result,
            extracted_text=context,
        )

        next_offset = page_offset + 3
        has_next = next_offset < total_pages

        return Response({
            "document_id": document.id,
            "document_title": document.title,
            "content_type": "notes",
            "language": language,
            "page_offset": page_offset,
            "page_start": selected_pages[0].page_number,
            "page_end": selected_pages[-1].page_number,
            "total_pages": total_pages,
            "has_next": has_next,
            "next_page_offset": next_offset if has_next else None,
            "content": result,
             "saved_analysis_id": saved_analysis_id,
        })

    
class DetectPDFLessonsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        document_id = request.data.get("document_id")

        try:
            document_id = int(document_id)
            if document_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "A valid document_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        pages = list(
            DocumentPage.objects
            .filter(document=document)
            .exclude(extracted_text="")
            .order_by("page_number")
            .values("page_number", "extracted_text")
        )

        if not pages:
            return Response(
                {"error": "No readable PDF pages were found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Convert database records to the input format expected by AI.
        ai_pages = [
            {
                "page_number": page["page_number"],
                "text": page["extracted_text"],
            }
            for page in pages
        ]

        try:
            lessons = detect_pdf_lessons(ai_pages)
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception:
            logger.exception(
                "Lesson detection failed for document %s",
                document_id,
            )
            return Response(
                {"error": "Could not detect lessons. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            "document_id": document.id,
            "document_title": document.title,
            "lesson_count": len(lessons),
            "lessons": lessons,
        })



class LessonSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        document_id = request.data.get("document_id")
        lesson_title = request.data.get("lesson_title")
        language = request.data.get("language", "Tamil")

        # 1. Validate document ID
        try:
            document_id = int(document_id)
            if document_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "A valid document_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Validate lesson title
        if not isinstance(lesson_title, str) or not lesson_title.strip():
            return Response(
                {"error": "Please provide a lesson_title."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Validate language
        if language not in ("Tamil", "English", "Both"):
            return Response(
                {
                    "error": (
                        "language must be Tamil, English, or Both."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_title = normalize_lesson_title(lesson_title)

        # 4. Verify PDF belongs to the logged-in user
        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        # 5. Read pages from this PDF only
        pages = list(
            DocumentPage.objects
            .filter(document=document)
            .exclude(extracted_text="")
            .order_by("page_number")
            .values("page_number", "extracted_text")
        )

        if not pages:
            return Response(
                {"error": "No readable PDF pages were found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        ai_pages = [
            {
                "page_number": page["page_number"],
                "text": page["extracted_text"],
            }
            for page in pages
        ]

        # 6. Detect lessons
        try:
            lessons = detect_pdf_lessons(ai_pages)
        except Exception:
            logger.exception(
                "Lesson detection failed for document %s",
                document_id,
            )
            return Response(
                {"error": "Could not detect lessons in this PDF."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not lessons:
            return Response(
                {
                    "error": (
                        "No lessons were detected in this PDF. "
                        "Please check the PDF text or lesson detection."
                    ),
                    "available_lessons": [],
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 7. Match title after Unicode normalization
        matched_lesson = next(
            (
                lesson
                for lesson in lessons
                if normalize_lesson_title(
                    lesson.get("title", "")
                ) == requested_title
            ),
            None,
        )

        if matched_lesson is None:
            return Response(
                {
                    "error": (
                        "The requested lesson was not detected. "
                        "Please select a lesson from the detected list."
                    ),
                    "requested_lesson": lesson_title,
                    "available_lessons": lessons,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 8. Validate lesson page range
        try:
            start_page = int(matched_lesson["start_page"])
            end_page = int(matched_lesson["end_page"])

            if start_page <= 0 or end_page < start_page:
                raise ValueError

        except (KeyError, TypeError, ValueError):
            logger.error(
                "Invalid page range for lesson %s in document %s",
                matched_lesson.get("title", lesson_title),
                document_id,
            )
            return Response(
                {"error": "The detected lesson has an invalid page range."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 9. Get pages belonging to this lesson only
        lesson_pages = [
            page
            for page in pages
            if start_page <= page["page_number"] <= end_page
        ]

        if not lesson_pages:
            return Response(
                {
                    "error": (
                        "No readable pages were found for this lesson."
                    ),
                    "page_start": start_page,
                    "page_end": end_page,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        context = "\n\n".join(
            f'PDF Page {page["page_number"]}:\n'
            f'{page["extracted_text"]}'
            for page in lesson_pages
        )

        # 10. Generate an exam-focused summary
        try:
            summary = generate_study_content(
                content_type="summary",
                context=(
                    f"Lesson title: {matched_lesson['title']}\n"
                    f"PDF page range: {start_page}-{end_page}\n\n"
                    "Create a clear, exam-focused summary of this lesson only. "
                    "Use only the supplied lesson text. Do not invent facts "
                    "or include unrelated lessons. Preserve important facts, "
                    "definitions, examples, dates, names, and key points. "
                    "Organize the summary with meaningful headings and "
                    "bullet points where appropriate.\n\n"
                    f"{context}"
                ),
                language=language,
            )

            if not summary or not str(summary).strip():
                raise ValueError("The AI returned an empty lesson summary.")

        except Exception:
            logger.exception(
                "Lesson summary generation failed for document %s",
                document_id,
            )
            return Response(
                {"error": "Could not generate the lesson summary."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # 11. Return summary and source page range
        return Response({
            "document_id": document.id,
            "document_title": document.title,
            "content_type": "lesson_summary",
            "lesson_title": matched_lesson["title"],
            "language": language,
            "page_start": start_page,
            "page_end": end_page,
            "content": summary,
        })






class StudyQuizView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import logging

        logger = logging.getLogger(__name__)

        document_id = request.data.get("document_id")
        page_number = request.data.get("page_number", 1)
        number_of_questions = request.data.get(
            "number_of_questions", 5
        )
        language = request.data.get("language", "Tamil")

        scope = str(
            request.data.get("scope", "page")
        ).strip().lower()

        scope_name = str(
            request.data.get("scope_name", "")
        ).strip()

        # 1. Validate document ID
        try:
            document_id = int(document_id)
            if document_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "A valid document_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Validate question count
        try:
            number_of_questions = int(number_of_questions)
            if not 1 <= number_of_questions <= 10:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "Choose between 1 and 10 questions."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Validate language
        if language not in ("Tamil", "English"):
            return Response(
                {"error": "language must be Tamil or English."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Validate scope
        if scope not in ("page", "topic", "lesson"):
            return Response(
                {"error": "scope must be page, topic, or lesson."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if scope in ("topic", "lesson") and not scope_name:
            return Response(
                {
                    "error": (
                        "Please enter a topic name or lesson name."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5. Validate page number
        if scope == "page":
            try:
                page_number = int(page_number)
                if page_number < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return Response(
                    {"error": "Enter a valid page number."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 6. Get the selected PDF owned by this user
        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        all_pages = (
            DocumentPage.objects
            .filter(document=document)
            .exclude(extracted_text="")
            .order_by("page_number")
        )

        total_pages = all_pages.count()

        if total_pages == 0:
            return Response(
                {"error": "This PDF has no readable pages."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 7. Select PDF content
        if scope == "page":
            selected_page = all_pages.filter(
                page_number=page_number
            ).first()

            if not selected_page:
                return Response(
                    {
                        "error": (
                            f"Page {page_number} was not found "
                            "or has no readable text."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            selected_pages = [selected_page]

            context = (
                f"Page {selected_page.page_number}:\n"
                f"{selected_page.extracted_text[:8000]}"
            )

        else:
            matching_pages = []
            search_name = scope_name.casefold()

            for page in all_pages.iterator():
                page_text = page.extracted_text or ""

                if search_name in page_text.casefold():
                    matching_pages.append(page)

            if not matching_pages:
                return Response(
                    {
                        "error": (
                            f"No pages containing '{scope_name}' "
                            "were found in this PDF. Check the name "
                            "or try a shorter keyword."
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            selected_pages = matching_pages

            context = "\n\n".join(
                f"Page {page.page_number}:\n"
                f"{page.extracted_text[:8000]}"
                for page in selected_pages
            )

        # 8. Check selected PDF text
        if not context.strip():
            return Response(
                {"error": "No readable text was found for this quiz."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 9. Collect previous questions from this PDF
        seen_questions = []
        previous_attempts = (
            QuizAttempt.objects
            .filter(
                user=request.user,
                document=document,
            )
            .only("questions_data")
        )

        for previous_attempt in previous_attempts:
            previous_questions = previous_attempt.questions_data

            if not isinstance(previous_questions, list):
                continue

            for previous_question in previous_questions:
                if not isinstance(previous_question, dict):
                    continue

                old_question = previous_question.get("question", "")

                if isinstance(old_question, str) and old_question.strip():
                    seen_questions.append(old_question.strip())

        # 10. Generate and save new quiz
        try:
            questions = generate_quiz_questions(
                context=context,
                number_of_questions=number_of_questions,
                language=language,
                excluded_questions=seen_questions,
            )

            if not isinstance(questions, list) or not questions:
                return Response(
                    {
                        "error": (
                            "No new quiz questions could be generated. "
                            "Try another page, topic, or lesson."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Ensure questions are dictionaries
            questions = [
                question
                for question in questions
                if isinstance(question, dict)
                and str(question.get("question", "")).strip()
            ]

            if not questions:
                return Response(
                    {"error": "No valid quiz questions were generated."},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Set default metadata
            for question in questions:
                question.setdefault(
                    "topic",
                    scope_name if scope != "page" else "",
                )

                if scope == "page":
                    question.setdefault(
                        "source_page",
                        selected_pages[0].page_number,
                    )
                else:
                    question.setdefault("source_page", None)

            attempt = QuizAttempt.objects.create(
                user=request.user,
                document=document,
                quiz_type="quiz",
                total_questions=len(questions),
                correct_answers=0,
                score=0,
                questions_data=questions,
            )

        except Exception as exc:
            logger.exception(
                "Quiz generation or saving failed."
            )

            return Response(
                {"error": "Quiz generation failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 11. Return questions without correct answers
        public_questions = [
            {
                "question": question.get("question", ""),
                "options": question.get("options", {}),
                "source_page": question.get("source_page"),
            }
            for question in questions
        ]

        # 12. Determine next readable page
        last_page_number = (
            all_pages.order_by("-page_number")
            .values_list("page_number", flat=True)
            .first()
        )

        has_next = (
            scope == "page"
            and page_number < (last_page_number or page_number)
        )

        return Response(
            {
                "attempt_id": attempt.id,
                "document_id": document.id,
                "document_title": document.title,
                "language": language,
                "scope": scope,
                "scope_name": (
                    scope_name if scope != "page" else ""
                ),
                "page_start": selected_pages[0].page_number,
                "page_end": selected_pages[-1].page_number,
                "total_pages": total_pages,
                "has_next": has_next,
                "next_page_offset": None,
                "next_page_number": (
                    page_number + 1 if has_next else None
                ),
                "questions": public_questions,
            },
            status=status.HTTP_201_CREATED,
        )

class QuizSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        attempt_id = request.data.get("attempt_id")
        submitted_answers = request.data.get("answers")

        try:
            attempt_id = int(attempt_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "A valid attempt_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(submitted_answers, dict):
            return Response(
                {
                    "error": (
                        "answers must be an object mapping "
                        "question numbers to selected options."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            attempt = get_object_or_404(
                QuizAttempt.objects.select_for_update(),
                pk=attempt_id,
                user=request.user,
            )

            if attempt.answers.exists():
                return Response(
                    {"error": "This quiz has already been submitted."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            questions = attempt.questions_data

            if not isinstance(questions, list) or not questions:
                return Response(
                    {"error": "No quiz questions were found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            results = []
            correct_count = 0
            weak_topics = []

            for index, question in enumerate(questions):
                question_key = str(index)
                selected = submitted_answers.get(question_key, "")
                selected = (
                    selected.strip().upper()
                    if isinstance(selected, str)
                    else ""
                )

                options = question.get("options", {})
                correct = str(
                    question.get("correct_answer", "")
                ).strip().upper()

                if correct not in ("A", "B", "C", "D"):
                    return Response(
                        {"error": "A quiz question has an invalid answer key."},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    )

                if selected and selected not in ("A", "B", "C", "D"):
                    return Response(
                        {
                            "error": (
                                f"Invalid option for question "
                                f"{index + 1}. Choose A, B, C, or D."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                is_correct = selected == correct

                if is_correct:
                    correct_count += 1

                topic = str(
                    question.get("topic")
                    or f"Page {question.get('source_page', 'Unknown')}"
                )[:200]

                if not is_correct:
                    weak_topics.append(topic)

                QuizAnswer.objects.create(
                    attempt=attempt,
                    question=question.get("question", ""),
                    topic=topic,
                    selected_answer=selected,
                    correct_answer=correct,
                    is_correct=is_correct,
                )

                results.append(
                    {
                        "question_number": index + 1,
                        "question": question.get("question", ""),
                        "selected_answer": selected or None,
                        "correct_answer": correct,
                        "is_correct": is_correct,
                        "explanation": question.get("explanation", ""),
                        "source_page": question.get("source_page"),
                    }
                )

            total = len(questions)
            score = round(correct_count / total * 100, 2)

            attempt.total_questions = total
            attempt.correct_answers = correct_count
            attempt.score = score
            attempt.save(
                update_fields=[
                    "total_questions",
                    "correct_answers",
                    "score",
                ]
            )

        return Response(
            {
                "attempt_id": attempt.id,
                "total_questions": total,
                "correct_answers": correct_count,
                "incorrect_answers": total - correct_count,
                "score": score,
                "accuracy": attempt.accuracy,
                "results": results,
                "weak_topics": sorted(set(weak_topics)),
            },
            status=status.HTTP_200_OK,
        )




class StudyFlashcardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        document_id = request.data.get("document_id")
        page_offset = request.data.get("page_offset", 0)
        number_of_cards = request.data.get("number_of_cards", 5)
        language = request.data.get("language", "Tamil")

        # Validate document ID
        try:
            document_id = int(document_id)
            if document_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "A valid document_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate page offset for batch navigation
        try:
            page_offset = int(page_offset)
            if page_offset < 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "page_offset must be a non-negative integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate requested number of flashcards
        try:
            number_of_cards = int(number_of_cards)
            if number_of_cards not in (3, 5, 10):
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "Choose 3, 5, or 10 flashcards."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate language
        if language not in ("Tamil", "English"):
            return Response(
                {"error": "language must be Tamil or English."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only allow the logged-in user to access their PDF
        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        # Get every readable page in the selected PDF
        all_pages = (
            DocumentPage.objects
            .filter(document=document)
            .exclude(extracted_text="")
            .order_by("page_number")
        )

        total_pages = all_pages.count()

        if total_pages == 0:
            return Response(
                {"error": "No readable pages found in this PDF."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Load the complete PDF text
        all_page_records = list(all_pages)

        context = "\n\n".join(
            f"Page {page.page_number}:\n{page.extracted_text}"
            for page in all_page_records
        )

        page_start = all_page_records[0].page_number
        page_end = all_page_records[-1].page_number

        # Generate flashcards using the complete PDF context
        
           
        # Generate flashcards using the complete PDF context
        try:
            cards = generate_flashcards(
                context=context,
                number_of_cards=number_of_cards,
                language=language,
            )

        except Exception as exc:
            import traceback

            traceback.print_exc()

            error_text = str(exc).upper()

            if (
                "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
                or "QUOTA_EXCEEDED" in error_text
            ):
                return Response(
                    {
                        "error": (
                            "Gemini API rate limit reached. "
                            "Please wait 30–60 seconds and try again."
                        )
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            return Response(
                {
                    "error": (
                        "Flashcard generation failed. "
                        "Please check the backend terminal."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


        if not isinstance(cards, list) or not cards:
            return Response(
                {"error": "No flashcards were generated."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Save the generated flashcards to My Library
        saved_set = SavedFlashcardSet.objects.create(
            user=request.user,
            document=document,
            title=f"Flashcards - {document.title} (Full PDF)",
            language=language,
            page_start=page_start,
            page_end=page_end,
            cards=cards,
        )

        # Keep existing batch navigation support
        next_offset = page_offset + 3
        has_next = next_offset < total_pages

        return Response({
            "document_id": document.id,
            "document_title": document.title,
            "language": language,
            "page_start": page_start,
            "page_end": page_end,
            "total_pages": total_pages,
            "has_next": has_next,
            "next_page_offset": (
                next_offset if has_next else None
            ),
            "flashcards": cards,
            "saved_flashcard_set_id": saved_set.id,
            "saved_to_library": True,
        })



class StudyPlannerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        exam_date_value = request.data.get("exam_date")
        daily_hours_value = request.data.get("daily_hours")
        topics = request.data.get("topics", [])

        try:
            exam_date = date.fromisoformat(exam_date_value)
        except (TypeError, ValueError):
            return Response(
                {"error": "Provide exam_date in YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if exam_date < date.today():
            return Response(
                {"error": "Exam date cannot be in the past."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            daily_hours = float(daily_hours_value)
            if not 1 <= daily_hours <= 12:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"error": "daily_hours must be between 1 and 12."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            not isinstance(topics, list)
            or not topics
            or any(
                not isinstance(topic, str) or not topic.strip()
                for topic in topics
            )
        ):
            return Response(
                {"error": "Provide a non-empty list of topics."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        days_left = (exam_date - date.today()).days + 1
        study_days = max(days_left, 1)

        daily_plan = []

        for day_index in range(study_days):
            current_date = date.today() + timedelta(days=day_index)
            topic_index = day_index % len(topics)

            daily_plan.append({
                "date": current_date.isoformat(),
                "topics": [topics[topic_index].strip()],
                "study_hours": daily_hours,
                "revision": (
                    "Revise previously studied topics"
                    if day_index > 0 else "Review today's topic"
                ),
            })
              
        saved_plan = SavedStudyPlan.objects.create(
            user=request.user,
            title="Study Plan",
            exam_date=exam_date,
            daily_hours=daily_hours,
            topics=[topic.strip() for topic in topics],
            plan=daily_plan,
            days_available=study_days,
            total_study_hours=round(
                study_days * daily_hours, 2
            ),
        )

        return Response({
            "exam_date": exam_date.isoformat(),
            "days_available": study_days,
            "daily_hours": daily_hours,
            "total_study_hours": round(
                study_days * daily_hours, 2
            ),
            "plan": daily_plan,
            "saved_plan_id": saved_plan.id,
            "saved_to_library": True,
        })

class StudyPlanProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, plan_id):
        completed_date = request.data.get("date")
        completed = request.data.get("completed")

        if not isinstance(completed_date, str):
            return Response(
                {"error": "A valid date is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(completed, bool):
            return Response(
                {"error": "completed must be true or false."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan_obj = get_object_or_404(
            SavedStudyPlan,
            pk=plan_id,
            user=request.user,
        )

        plan_days = plan_obj.plan

        if not isinstance(plan_days, list):
            return Response(
                {"error": "Invalid saved plan format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        matching_day = next(
            (
                day for day in plan_days
                if isinstance(day, dict)
                and day.get("date") == completed_date
            ),
            None,
        )

        if matching_day is None:
            return Response(
                {"error": "Day not found in this plan."},
                status=status.HTTP_404_NOT_FOUND,
            )

        matching_day["completed"] = completed
        plan_obj.plan = plan_days
        plan_obj.save(update_fields=["plan", "updated_at"])

        completed_count = sum(
            1 for day in plan_days
            if isinstance(day, dict)
            and day.get("completed") is True
        )

        return Response({
            "success": True,
            "date": completed_date,
            "completed": completed,
            "completed_days": completed_count,
            "total_days": len(plan_days),
        })
class NotesPDFExportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        title = request.data.get("title", "Smart Study AI Notes")
        content = request.data.get("content", "")

        if not isinstance(title, str) or not title.strip():
            return Response(
                {"error": "A valid title is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(content, str) or not content.strip():
            return Response(
                {"error": "Notes content is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            pdf_buffer = create_notes_pdf(
                title=title.strip(),
                content=content,
            )
        except Exception:
            import traceback
            traceback.print_exc()
            return Response(
                {
                    "error": (
                        "PDF generation failed. "
                        "Check server logs."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = HttpResponse(
            pdf_buffer.getvalue(),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = (
            'attachment; filename="study_notes.pdf"'
        )
        return response



class SmartRevisionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        answers = (
            QuizAnswer.objects
            .filter(attempt__user=request.user)
            .select_related("attempt", "attempt__document")
            .order_by("-attempt__created_at")
        )

        topic_stats = {}

        for answer in answers:
            topic = (answer.topic or "General Revision").strip()
            document = answer.attempt.document
            document_id = document.id if document else None
            document_name = (
                getattr(document, "title", None)
                or getattr(document, "name", None)
                or getattr(document, "original_filename", None)
                or getattr(document, "file_name", None)
                or "Unknown PDF"
            ) if document else None

            # Group by BOTH PDF ID and topic name.
            # The same topic in two PDFs stays separate.
            key = (document_id, topic.casefold())

            if key not in topic_stats:
                topic_stats[key] = {
                    "topic": topic,
                    "document_id": document_id,
                    "document_name": document_name,
                    "total_questions": 0,
                    "correct_answers": 0,
                    "incorrect_answers": 0,
                    "latest_attempt": answer.attempt.created_at,
                }

            stats = topic_stats[key]
            stats["total_questions"] += 1

            if answer.is_correct:
                stats["correct_answers"] += 1
            else:
                stats["incorrect_answers"] += 1

        revision_topics = []

        for stats in topic_stats.values():
            total = stats["total_questions"]
            correct = stats["correct_answers"]
            incorrect = stats["incorrect_answers"]

            accuracy = round((correct / total) * 100, 2)

            # Show topics that have at least one wrong answer.
            if incorrect <= 0:
                continue

            if accuracy < 40:
                priority = "High"
                recommendation = (
                    "Revise this topic carefully and "
                    "practise basic questions."
                )
            elif accuracy < 70:
                priority = "Medium"
                recommendation = (
                    "Review your mistakes and practise "
                    "more questions."
                )
            else:
                priority = "Low"
                recommendation = (
                    "Review incorrect answers and "
                    "take a short revision quiz."
                )

            revision_topics.append({
                **stats,
                "accuracy": accuracy,
                "priority": priority,
                "recommendation": recommendation,

                # Keep compatibility with the existing frontend.
                "total": total,
                "correct": correct,
                "incorrect": incorrect,
            })

        priority_order = {
            "High": 0,
            "Medium": 1,
            "Low": 2,
        }

        revision_topics.sort(
            key=lambda item: (
                priority_order[item["priority"]],
                -item["incorrect"],
                item["accuracy"],
            )
        )

        # Do not limit the results to the top 10 here.
        # Otherwise, some PDFs may have no topics in the filter.

        return Response({
            "total_topics_to_revise": len(revision_topics),
            "revision_topics": revision_topics,
            "message": (
                "Revision recommendations generated successfully."
                if revision_topics
                else (
                    "No weak topics found yet. Complete a quiz "
                    "to receive revision recommendations."
                )
            ),
        })



class TopicRevisionQuizView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        document_id = request.data.get("document_id")
        topic = str(request.data.get("topic", "")).strip()
        language = request.data.get("language", "Tamil")

        try:
            number_of_questions = int(
                request.data.get("number_of_questions", 5)
            )
        except (TypeError, ValueError):
            return Response(
                {"error": "number_of_questions must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate request data
        if not document_id or not topic:
            return Response(
                {"error": "document_id and topic are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not 1 <= number_of_questions <= 10:
            return Response(
                {"error": "Choose between 1 and 10 questions."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if language not in ["Tamil", "English"]:
            return Response(
                {"error": "Language must be Tamil or English."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Only allow access to the current user's document
        document = get_object_or_404(
            Document,
            pk=document_id,
            owner=request.user,
        )

        pages = DocumentPage.objects.filter(
            document=document
        ).order_by("page_number")

        # 1. Try exact topic matching first
        matching_pages = [
            page
            for page in pages
            if topic.casefold()
            in (page.extracted_text or "").casefold()
        ]

        # 2. If exact matching fails, use semantic search
        if not matching_pages:
            try:
                search_results = search_pdf_pages(
                    topic,
                    limit=5,
                    document_id=document.id,
                    owner_id=request.user.id,
                )

                matching_page_numbers = {
                    item.get("page_number")
                    for item in search_results
                    if item.get("page_number") is not None
                }

                matching_pages = [
                    page
                    for page in pages
                    if page.page_number in matching_page_numbers
                ]

            except Exception:
                return Response(
                    {
                        "error": (
                            "PDF search failed. Please try again."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        # 3. Stop if no pages were found
        if not matching_pages:
            return Response(
                {
                    "error": (
                        "இந்த topic-க்கு பொருத்தமான text PDF-ல் "
                        "கிடைக்கவில்லை. வேறு topic தேர்வு செய்யவும்."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 4. Prepare PDF context for the AI
        pdf_text = "\n\n".join(
            f"Page {page.page_number}:\n{page.extracted_text}"
            for page in matching_pages[:5]
            if page.extracted_text
        )

        if not pdf_text.strip():
            return Response(
                {"error": "The selected PDF pages contain no readable text."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # 5. Generate topic-based revision questions
        try:
          questions = generate_topic_revision_questions(
            topic=topic,
            pdf_text=pdf_text,
            number_of_questions=number_of_questions,
            language=language,
    )

        except Exception as e:
            import traceback
            print("TOPIC REVISION ERROR:", repr(e), flush=True)
            traceback.print_exc()
            return Response(
               {"error": "Revision questions could not be generated."},
               status=status.HTTP_502_BAD_GATEWAY,
    )

         


        print("GENERATED QUESTIONS COUNT:", len(questions))
        if not questions:
            return Response(
                {
                    "error": (
                        "இந்த topic-க்கு போதுமான கேள்விகளை "
                        "உருவாக்க முடியவில்லை."
                    )
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # 6. Save the quiz attempt with answers on the server
        attempt = QuizAttempt.objects.create(
            user=request.user,
            document=document,
            quiz_type="revision",
            total_questions=len(questions),
            correct_answers=0,
            score=0,
            questions_data=questions,
        )

        # Never send correct answers or explanations before submission
        public_questions = [
            {
                "question": question["question"],
                "topic": question["topic"],
                "options": question["options"],
                "source_page": question.get("source_page"),
            }
            for question in questions
        ]

        return Response(
            {
                "attempt_id": attempt.id,
                "document_id": document.id,
                "topic": topic,
                "total_questions": len(public_questions),
                "questions": public_questions,
                "message": "Topic revision quiz created successfully.",
            },
            status=status.HTTP_201_CREATED,
        )

class SavedFlashcardSetListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = SavedFlashcardSet.objects.filter(
            user=request.user
        ).select_related("document")

        return Response([
            {
                "id": item.id,
                "title": item.title,
                "document_id": item.document_id,
                "document_title": item.document.title,
                "language": item.language,
                "page_start": item.page_start,
                "page_end": item.page_end,
                "cards": item.cards,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "item_type": "flashcards",
            }
            for item in items
        ])


class SavedStudyPlanListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = SavedStudyPlan.objects.filter(
            user=request.user
        ).order_by("-updated_at")

        return Response([
            {
                "id": item.id,
                "title": item.title,
                "exam_date": item.exam_date.isoformat(),
                "daily_hours": item.daily_hours,
                "topics": item.topics,
                "plan": item.plan,
                "days_available": item.days_available,
                "total_study_hours": item.total_study_hours,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "item_type": "plans",
            }
            for item in items
        ])

class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 1. PDFs uploaded by the logged-in user
        documents = Document.objects.filter(owner=user)

        pdf_count = documents.count()

        # 2. Notes and summaries saved in DocumentAnalysis
        notes_count = DocumentAnalysis.objects.filter(
            owner=user
        ).filter(
            Q(notes__gt="") | Q(summary__gt="")
        ).count()

        # 3. Completed quizzes only
        completed_attempts = (
            QuizAttempt.objects
            .filter(
                user=user,
                answers__isnull=False,
            )
            .distinct()
        )

        quizzes_completed = completed_attempts.count()

        # 4. Overall quiz performance
        performance = completed_attempts.aggregate(
            total_questions=Count("answers__id"),
            correct_answers=Count(
                "answers__id",
                filter=Q(answers__is_correct=True),
            ),
        )

        total_questions = performance["total_questions"] or 0
        correct_answers = performance["correct_answers"] or 0

        accuracy = (
            round(correct_answers / total_questions * 100, 1)
            if total_questions
            else 0
        )

        # 5. Seven-day quiz activity
        today = timezone.localdate()
        start_date = today - timedelta(days=6)

        recent_attempts = completed_attempts.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=today,
        )

        activity_by_date = {
            item["day"]: item["count"]
            for item in (
                recent_attempts

                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(count=Count("id", distinct=True))
            )
        }

        weekly_activity = []

        for day_offset in range(7):
            current_day = start_date + timedelta(days=day_offset)

            weekly_activity.append({
                "date": current_day.isoformat(),
                "label": current_day.strftime("%a"),
                "quizzes": activity_by_date.get(current_day, 0),
            })

        # 6. Recent PDFs
        recent_documents = documents.order_by(
            "-uploaded_at"
        )[:5]

        recent_pdfs = [
            {
                "id": doc.id,
                "title": doc.title,
                "subject": doc.subject,
                "uploaded_at": doc.uploaded_at,
            }
            for doc in recent_documents
        ]


                       # 7. Saved flashcards and study plans
        flashcard_count = SavedFlashcardSet.objects.filter(
            user=user
        ).count()

        study_plan_count = SavedStudyPlan.objects.filter(
            user=user
        ).count()
                
        # 7A. Latest study plan completion progress
        latest_plan = (
            SavedStudyPlan.objects
            .filter(user=user)
            .order_by("-created_at")
            .first()
        )

        planner_progress = {
            "completed_days": 0,
            "pending_days": 0,
            "total_days": 0,
            "completion_percentage": 0,
        }

        if latest_plan and isinstance(latest_plan.plan, list):
            valid_days = [
                day for day in latest_plan.plan
                if isinstance(day, dict) and day.get("date")
            ]

            completed_days = sum(
                1 for day in valid_days
                if day.get("completed") is True
            )

            total_days = len(valid_days)
            pending_days = total_days - completed_days

            planner_progress = {
                "completed_days": completed_days,
                "pending_days": pending_days,
                "total_days": total_days,
                "completion_percentage": (
                    round(completed_days / total_days * 100, 1)
                    if total_days else 0
                ),
            }

        # 8. Calculate total saved study time
        study_time_seconds = (
            StudyTimeSession.objects
            .filter(user=user)
            .aggregate(total=Sum("total_seconds"))["total"]
            or 0
        )

        study_time_minutes = study_time_seconds // 60

        return Response({
            "pdf_count": pdf_count,
            "notes_count": notes_count,
            "quizzes_completed": quizzes_completed,
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "accuracy": accuracy,
            "weekly_activity": weekly_activity,
            "recent_pdfs": recent_pdfs,
            "flashcard_sets": flashcard_count,
            "study_plans": study_plan_count,
           "planner_progress": planner_progress,
            # Study time tracking
            "study_time_minutes": study_time_minutes,
            "study_time_seconds": study_time_seconds,
            "study_time_tracked": True,
        })
    
class StudyTimeTrackingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        elapsed_seconds = request.data.get("elapsed_seconds")
        page_type = request.data.get("page_type", "notes")

        allowed_pages = {
            "notes",
            "quiz",
            "revision",
            "flashcards",
        }

        if not isinstance(session_id, str) or not session_id.strip():
            return Response(
                {"error": "session_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # bool is a subclass of int in Python, so reject it explicitly.
        if (
            isinstance(elapsed_seconds, bool)
            or not isinstance(elapsed_seconds, int)
            or elapsed_seconds < 0
        ):
            return Response(
                {"error": "elapsed_seconds must be a non-negative integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if page_type not in allowed_pages:
            return Response(
                {"error": "Invalid study page."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            study_session, created = StudyTimeSession.objects.get_or_create(
                user=request.user,
                session_id=session_id.strip(),
                defaults={
                    "page_type": page_type,
                    "total_seconds": elapsed_seconds,
                },
            )

            if not created:
                study_session = (
                    StudyTimeSession.objects
                    .select_for_update()
                    .get(pk=study_session.pk)
                )

                # Cumulative total is idempotent:
                # a repeated or older request won't add time again.
                if elapsed_seconds > study_session.total_seconds:
                    study_session.total_seconds = elapsed_seconds

                study_session.page_type = page_type
                study_session.save(
                    update_fields=[
                        "total_seconds",
                        "page_type",
                        "updated_at",
                    ]
                )

        return Response({
            "success": True,
            "session_seconds": study_session.total_seconds,
        })

    


class AIStudyChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        question = request.data.get("question", "")
        chat_id = request.data.get("chat_id")
        history = request.data.get("history", [])
        mode = request.data.get("mode", "explain")
        language = request.data.get("language", "Tamil")

        # Validate question
        if not isinstance(question, str) or not question.strip():
            return Response(
                {"error": "Please enter a question."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        question = question.strip()

        if len(question) > 1000:
            return Response(
                {"error": "Question must be 1000 characters or fewer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate mode and language
        valid_modes = {
            "explain",
            "diagram",
            "sticky_notes",
            "visualize",
            "practice",
        }

        valid_languages = {"Tamil", "English", "Tanglish"}

        if not isinstance(mode, str) or mode not in valid_modes:
            mode = "explain"

        if not isinstance(language, str) or language not in valid_languages:
            language = "Tamil"

        # Mode-specific instructions
        mode_instructions = {
            "explain": (
                "Explain the topic step by step in simple language. "
                "Use clear headings, important points, and examples "
                "when useful. Keep the answer easy to understand."
            ),

            "diagram": (
                "Create a diagram-focused answer, not a normal essay. "
                "Show the concept using a clear text flowchart with "
                "labels, arrows, and relationships. When suitable, "
                "include a Mermaid flowchart inside a fenced mermaid "
                "code block. Keep the diagram accurate and readable. "
                "Briefly explain the diagram after it."
            ),

            "sticky_notes": (
                "Create revision sticky notes instead of a long essay. "
                "Organize the answer into compact notes titled "
                "'Note 1', 'Note 2', and so on. Each note should contain "
                "one important fact, definition, example, or exam point. "
                "Use short bullet points and highlight key terms. "
                "Make the notes easy to revise quickly."
            ),

                



"visualize": (
    "You are Smart Study AI in VISUAL LEARNING mode. "
    "Create an attractive, easy-to-scan visual learning response, "
    "not an essay and not a flowchart by default. "

    "Return content using these exact section markers:\n"
    "TITLE: A short topic title\n"
    "OVERVIEW: A simple 1-2 sentence introduction\n"
    "KEY IDEA: The central concept in simple words\n"
    "VISUAL CARDS:\n"
    "- CARD: First concept | Short explanation\n"
    "- CARD: Second concept | Short explanation\n"
    "- CARD: Third concept | Short explanation\n"
    "IMPORTANT FACTS:\n"
    "- Fact one\n"
    "- Fact two\n"
    "- Fact three\n"
    "REMEMBER: A short memory tip\n"

    "Choose the best visual organization for the topic: "
    "concept cards, comparison cards, timelines, categories, "
    "labelled parts, or step-by-step stages. "
    "Use a flowchart only when relationships or sequences "
    "genuinely need one. "

    "Use 3-6 relevant cards when sufficient facts are available. "
    "Do not invent facts or force irrelevant sections. "
    "Use the requested response language for all displayed text. "
    "Keep explanations concise and useful for exam revision. "
    "Do not output ASCII art or Unicode trees. "
    "Do not claim that an actual image was generated."
),

            "practice": (
                "Create exactly 5 practice MCQs about the requested topic. "
                "Each question must have four options labelled A, B, C, D "
                "and exactly one correct answer. After each question, "
                "show the correct answer and a short explanation. "
                "Use questions suitable for the learner's topic and "
                "TNPSC Group 2/2A preparation when relevant. "
                "Do not provide a normal essay instead of MCQs."
            ),
        }

        # Open this user's existing chat or create a new one
        if chat_id not in (None, ""):
            try:
                chat_id = int(chat_id)

                if chat_id <= 0:
                    raise ValueError

            except (TypeError, ValueError):
                return Response(
                    {"error": "Invalid chat_id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                chat = StudyChat.objects.get(
                    id=chat_id,
                    user=request.user,
                )

            except StudyChat.DoesNotExist:
                return Response(
                    {"error": "Chat not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        else:
            chat = StudyChat.objects.create(
                user=request.user,
                title=question[:60],
                mode=mode,
                language=language,
            )

        # Load recent saved messages for follow-up context
        saved_messages = list(
            chat.messages.order_by("-created_at", "-id")[:8]
        )
        saved_messages.reverse()

        safe_history = [
            f"{message.role.title()}: {message.content[:1500]}"
            for message in saved_messages
        ]

        # Backward compatibility with the existing frontend
        if not safe_history and isinstance(history, list):
            for item in history[-8:]:
                if not isinstance(item, dict):
                    continue

                role = item.get("role")
                content = item.get("content")

                if (
                    role in ("user", "assistant")
                    and isinstance(content, str)
                    and content.strip()
                ):
                    safe_history.append(
                        f"{role.title()}: {content.strip()[:1500]}"
                    )

        # Build AI prompt with the selected mode instructions
        prompt = (
            "You are Smart Study AI, a friendly study tutor for school, "
            "college subjects, and TNPSC Group 2/2A preparation.\n"
            "Answer study-related questions accurately. Politely redirect "
            "unrelated questions to study topics.\n"
            "Use simple language in the requested response language.\n"
            "Do not invent facts. If uncertain, say so clearly.\n"
            f"Response language: {language}\n"
            f"Selected study mode: {mode}\n"
            f"Mode-specific instructions: {mode_instructions[mode]}\n"
        )

        if safe_history:
            prompt += (
                "\nRecent conversation for context only:\n"
                + "\n".join(safe_history)
                + "\nAnswer the current question directly. "
                "Do not simply repeat an earlier response. "
                "Follow the currently selected study mode, even if "
                "the earlier messages used a different mode.\n"
            )

        prompt += (
            "\nCurrent user question:\n"
            f"{question}\n"
        )

        try:
            answer = generate_general_answer(prompt)

            if not isinstance(answer, str) or not answer.strip():
                return Response(
                    {
                        "error": (
                            "AI returned an empty answer. Please try again."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            answer = answer.strip()

            # Save messages and activity together
            with transaction.atomic():
                StudyChatMessage.objects.create(
                    chat=chat,
                    role="user",
                    content=question,
                    mode=mode,
                )

                StudyChatMessage.objects.create(
                    chat=chat,
                    role="assistant",
                    content=answer,
                    mode=mode,
                )

                chat.mode = mode
                chat.language = language
                chat.save(
                    update_fields=["mode", "language", "updated_at"]
                )

                activity_type = {
                    "diagram": "diagram",
                    "sticky_notes": "sticky_notes",
                    "visualize": "visualize",
                    "practice": "practice",
                }.get(mode, "question")

                StudyActivity.objects.create(
                    user=request.user,
                    chat=chat,
                    activity_type=activity_type,
                    topic=question[:255],
                    details={
                        "mode": mode,
                        "language": language,
                    },
                )

            return Response(
                {
                    "chat_id": chat.id,
                    "title": chat.title,
                    "question": question,
                    "answer": answer,
                    "mode": mode,
                    "language": language,
                },
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception("AI Study Chat failed")

            return Response(
                {
                    "error": (
                        "AI could not answer right now. Please try again."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
