

import json

from django.conf import settings
from google import genai
from google.genai import types

from google.genai.errors import ServerError


MODEL_NAME = "gemini-3.5-flash-lite"


def get_gemini_client():
    if not settings.GEMINI_API_KEY:
        raise ValueError("Gemini API key is not configured.")


    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=120000
        ),
    )







def generate_pdf_answer(question, context):
    client = get_gemini_client()

    prompt = f"""
You are a helpful teacher answering questions from an uploaded PDF.

IMPORTANT RULES:
1. Use only facts present in the supplied PDF context.
2. Answer the exact question directly.
3. If the answer is not supported by the context, say so.
4. If the question is in Tamil, answer in simple, clear Tamil.
5. Do not invent facts, page numbers, or unrelated information.

Question:
{question}

PDF context:
{context[:12000]}

Answer:
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "temperature": 0.1,
            "max_output_tokens": 500,
        },
    )

    result = response.text or ""

    if not result.strip():
        raise ValueError(
            "The AI returned an empty answer. Please try again."
        )

    return result.strip()


def generate_general_answer(question):
    client = get_gemini_client()

    prompt = f"""
You are a helpful AI study assistant and patient teacher.

GENERAL RULES:
- Answer the user's exact question.
- Answer general questions even when no PDF is uploaded.
- If the user greets you, reply with a friendly greeting.
- If the question is in Tamil, answer in simple Tamil.
- If the question is in English, answer in clear English.
- Explain concepts clearly with useful examples when appropriate.
- Never claim to use a PDF when no PDF was provided.
- If you are unsure about a fact, be honest.
- Keep the answer relevant to the user's request.

RELATED-QUESTION RULES:
- If the user asks for related questions, use the original
  question and any context included in the user's message.
- Generate exactly the number of questions requested.
- Keep all questions on the same subject and topic.
- Match the original question's difficulty level.
- Do not switch to unrelated subjects.
- Include step-by-step solutions and verify each answer
  when the questions involve calculations.
- If the original question or context is genuinely missing,
  ask the user to provide it instead of inventing a topic.
- Follow the requested language.

User question and context:
{question}

Answer:
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "temperature": 0.2,
            "max_output_tokens": 1200,
        },
    )

    result = response.text or ""

    if not result.strip():
        raise ValueError(
            "The AI returned an empty answer. Please try again."
        )

    return result.strip()

def generate_study_content(content_type, context, language="Tamil"):
    prompts = {
        "notes": (
            "Create clear, well-organized study notes from the supplied PDF text. "
            "Use a title, short headings, bullet points, important facts, "
            "definitions, and examples only when supported by the source. "
            "Preserve important details and do not add outside information."
        ),
        "summary": (
            "Create a useful summary of the supplied PDF text. "
            "Cover the main ideas, important facts, definitions, and key terms. "
            "Use headings and bullet points where helpful."
        ),
    }

    if content_type not in prompts:
        raise ValueError("Unsupported study content type.")

    language_instructions = {
        "Tamil": (
            "Write the entire response in simple, clear Tamil. "
            "Keep useful technical terms in English in parentheses."
        ),
        "English": (
            "Write the entire response in clear, simple English."
        ),
        "Both": (
            "Write two clearly separated sections: first Tamil, then English. "
            "Both sections must cover the same important information."
        ),
    }

    if language not in language_instructions:
        raise ValueError("Unsupported language.")

    if not isinstance(context, str) or not context.strip():
        raise ValueError("PDF text is empty. Please check the uploaded PDF.")

    client = get_gemini_client()

    prompt = f"""
You are a careful textbook study teacher.

Rules:
- Use only the supplied PDF text.
- Never invent facts, dates, definitions, examples, or page numbers.
- If text is unclear or missing, state that clearly.
- {language_instructions[language]}
- {prompts[content_type]}

PDF text:
{context}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "temperature": 0.2,
            "max_output_tokens": 2000,
        },
    )

    result = response.text or ""

    if not result.strip():
        raise ValueError(
            "The AI returned empty study content. Please try again."
        )

    return result.strip()






def detect_pdf_lessons(pages):
    """
    Detect lesson beginnings across PDF pages using Gemini.
    Continue after individual batch failures, remove duplicates,
    and calculate lesson end pages.
    """
    import json
    import re

    if not pages:
        raise ValueError("No PDF pages were provided.")

    # Step 1: Collect readable PDF pages.
    readable_pages = []

    for page in pages:
        text = page.get("text", "")
        page_number = page.get("page_number")

        if not isinstance(text, str) or not text.strip():
            continue

        if (
            not isinstance(page_number, int)
            or isinstance(page_number, bool)
            or page_number < 1
        ):
            continue

        readable_pages.append({
            "page_number": page_number,
            "text": text.strip(),
        })

    if not readable_pages:
        raise ValueError("No readable PDF text was found.")

    readable_pages.sort(key=lambda p: p["page_number"])

    print(
        "READABLE PDF PAGES:",
        len(readable_pages),
        flush=True,
    )

    # Step 2: Initialize Gemini and batch settings.
    client = get_gemini_client()

    batch_size = 12
    overlap = 2
    step = batch_size - overlap

    detected = []

    # Step 3: Process PDF pages in overlapping batches.
    for offset in range(0, len(readable_pages), step):
        batch = readable_pages[offset:offset + batch_size]

        if not batch:
            continue

        page_parts = "\n".join(
            f"\n--- PDF PAGE {p['page_number']} ---\n"
            f"{p['text'][:4000]}"
            for p in batch
        )

        prompt = f"""
You are analyzing a school textbook PDF.

Identify actual main lesson or chapter beginnings
in the supplied PDF pages.

STRICT RULES:
- Use only the supplied PDF text.
- PDF page labels are authoritative.
- start_page MUST equal a supplied PDF PAGE label.
- Identify a lesson only when its actual beginning is visible.
- Do not treat table-of-contents entries as lesson beginnings.
- Do not treat poems, exercises, grammar headings, examples,
  or ordinary subheadings as separate main lessons unless
  they clearly begin a main lesson in the textbook.
- Do not invent or translate lesson titles.
- Preserve the original title language and wording.
- If uncertain, omit the candidate.
- Do not return end_page.
- Return valid JSON only.

Required format:
{{
  "lessons": [
    {{
      "title": "Exact lesson title",
      "start_page": 11
    }}
  ]
}}

PDF pages:
{page_parts}
"""

        # Step 4: Handle Gemini errors without losing previous results.
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 2500,
                    "response_mime_type": "application/json",
                },
            )

            raw = response.text or ""

        except Exception as exc:
            print(
                f"Gemini failed for batch starting at PDF page "
                f"{batch[0]['page_number']}: {exc}",
                flush=True,
            )
            continue

        print(
            "GEMINI RAW RESPONSE:",
            repr(raw[:2000]),
            flush=True,
        )

        valid_batch_pages = {
            p["page_number"]: p["text"]
            for p in batch
        }

        # Step 5: Parse the response JSON.
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            print(
                f"Invalid JSON for batch starting at PDF page "
                f"{batch[0]['page_number']}: {exc}",
                flush=True,
            )
            continue

        if not isinstance(data, dict):
            continue

        lessons = data.get("lessons", [])

        if not isinstance(lessons, list):
            continue

        # Step 6: Validate each detected lesson.
        for lesson in lessons:
            if not isinstance(lesson, dict):
                continue

            title = lesson.get("title")
            start = lesson.get("start_page")

            if not isinstance(title, str) or not title.strip():
                continue

            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or start not in valid_batch_pages
            ):
                continue

            title = re.sub(r"\s+", " ", title).strip()

            if len(title) > 200:
                continue

            detected.append({
                "title": title,
                "start_page": start,
            })

        print(
            "DETECTED LESSON CANDIDATES:",
            detected,
            flush=True,
        )

    # Step 7: Fail only if no batch found any lessons.
    if not detected:
        raise ValueError(
            "No lesson beginnings were detected. "
            "Check the PDF text or retry Gemini later."
        )

    # Step 8: Deduplicate by normalized lesson title.
    unique = {}

    for lesson in detected:
        key = re.sub(
            r"\s+", " ", lesson["title"]
        ).strip().casefold()

        if (
            key not in unique
            or lesson["start_page"] < unique[key]["start_page"]
        ):
            unique[key] = lesson

    ordered = sorted(
        unique.values(),
        key=lambda item: item["start_page"],
    )

    # Step 9: Keep only one lesson per starting page.
    page_unique = {}

    for lesson in ordered:
        page_unique.setdefault(
            lesson["start_page"],
            lesson,
        )

    ordered = sorted(
        page_unique.values(),
        key=lambda item: item["start_page"],
    )

    # Step 10: Calculate each lesson's end page.
    last_page = max(
        page["page_number"]
        for page in readable_pages
    )

    result = []

    for index, lesson in enumerate(ordered):
        start = lesson["start_page"]

        if index + 1 < len(ordered):
            end = ordered[index + 1]["start_page"] - 1
        else:
            end = last_page

        if end >= start:
            result.append({
                "title": lesson["title"],
                "start_page": start,
                "end_page": end,
            })

    if not result:
        raise ValueError("No valid lesson ranges were detected.")

    print("FINAL LESSON RANGES:", result, flush=True)

    return result







def generate_quiz_questions(
    context,
    number_of_questions=5,
    language="Tamil",
    excluded_questions=None,
):
    # 1. Validate question count
    if (
        not isinstance(number_of_questions, int)
        or isinstance(number_of_questions, bool)
        or not 1 <= number_of_questions <= 10
    ):
        raise ValueError(
            "Question count must be between 1 and 10."
        )

    # 2. Validate PDF text
    if not isinstance(context, str) or not context.strip():
        raise ValueError(
            "PDF text is empty. Please check the uploaded PDF."
        )

    # 3. Normalize question text for duplicate checking
    def normalize_question(text):
        return " ".join(
            text.casefold().split()
        ).strip(" ?.!")

    # 4. Prepare previously generated questions
    if excluded_questions is None:
        excluded_questions = []

    if not isinstance(excluded_questions, (list, tuple, set)):
        excluded_questions = []

    excluded_questions = [
        question.strip()
        for question in excluded_questions
        if isinstance(question, str) and question.strip()
    ]

    seen_questions = {
        normalize_question(question)
        for question in excluded_questions
    }

    previous_questions_text = "\n".join(
        f"- {question}"
        for question in excluded_questions
    )

    # 5. Get Gemini client
    client = get_gemini_client()

    # 6. Build prompt
    prompt = f"""
You are a careful school textbook quiz creator.

Use only the supplied PDF text. Never invent facts.

Create up to {number_of_questions} multiple-choice questions
in {language}, based only on the supplied text.

IMPORTANT RULES:
1. Try to return exactly {number_of_questions} questions.
2. Never repeat any previous question listed below.
3. Avoid slightly reworded versions of previous questions.
4. Test different facts, concepts, definitions, and ideas.
5. Every question must be supported by the supplied PDF text.
6. Return fewer questions if the text does not contain enough facts.
7. Every question must have four distinct answer options.
8. Only one option should be correct.
9. Do not include answers outside the JSON structure.
10. Return questions in the requested language.

Previously generated questions — DO NOT REPEAT:
{previous_questions_text or "None"}

Return ONLY valid JSON without Markdown fences:
{{
  "questions": [
    {{
      "question": "Question text",
      "topic": "Specific textbook topic",
      "options": {{
        "A": "Option A",
        "B": "Option B",
        "C": "Option C",
        "D": "Option D"
      }},
      "correct_answer": "A",
      "explanation": "Explanation supported by the PDF",
      "source_page": 1
    }}
  ]
}}

Requirements:
- correct_answer must be A, B, C, or D.
- Topics must be meaningful and supported by the PDF.
- Do not use page numbers as topic names.
- Use source_page only when the source page is known.
- Return only questions supported by the supplied text.

PDF text:
{context[:5000]}
"""

    # 7. Generate questions
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "temperature": 0.2,
            "max_output_tokens": 4096,
            "response_mime_type": "application/json",
        },
    )

    raw_content = response.text or ""

    # 8. Parse JSON response
    try:
        quiz_data = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(
            "The AI returned invalid quiz JSON. Please try again."
        ) from exc

    if not isinstance(quiz_data, dict):
        raise ValueError(
            "The AI quiz response must be a JSON object."
        )

    questions = quiz_data.get("questions")

    if not isinstance(questions, list):
        raise ValueError(
            "The AI quiz response has no valid questions list."
        )

    print(
        f"Requested: {number_of_questions}, "
        f"AI returned: {len(questions)}"
    )

    # 9. Validate questions and remove duplicates
    validated_questions = []

    for item in questions:
        if len(validated_questions) >= number_of_questions:
            break

        if not isinstance(item, dict):
            continue

        question = item.get("question")
        topic = item.get("topic")
        options = item.get("options")

        correct_answer = str(
            item.get("correct_answer", "")
        ).strip().upper()

        explanation = item.get("explanation", "")
        source_page = item.get("source_page")

        # Validate question
        if not isinstance(question, str) or not question.strip():
            continue

        question = question.strip()
        normalized_question = normalize_question(question)

        if not normalized_question:
            continue

        # Skip previously seen or repeated questions
        if normalized_question in seen_questions:
            continue

        # Validate options
        if not isinstance(options, dict):
            continue

        if not all(
            isinstance(options.get(key), str)
            and options[key].strip()
            for key in ("A", "B", "C", "D")
        ):
            continue

        # Require four distinct options
        normalized_options = [
            " ".join(options[key].casefold().split())
            for key in ("A", "B", "C", "D")
        ]

        if len(set(normalized_options)) != 4:
            continue

        # Validate correct answer
        if correct_answer not in ("A", "B", "C", "D"):
            continue

        # Validate topic
        if not isinstance(topic, str) or not topic.strip():
            topic = "General Revision"

        # Validate explanation
        if not isinstance(explanation, str):
            explanation = ""

        # Validate source page
        if (
            not isinstance(source_page, int)
            or isinstance(source_page, bool)
            or source_page < 1
        ):
            source_page = None

        # Save the validated question
        validated_questions.append({
            "question": question,
            "topic": topic.strip()[:200],
            "options": {
                key: options[key].strip()
                for key in ("A", "B", "C", "D")
            },
            "correct_answer": correct_answer,
            "explanation": explanation.strip(),
            "source_page": source_page,
        })

        # Add immediately to prevent duplicates in this response
        seen_questions.add(normalized_question)

    # 10. Log results
    print(
        f"Valid questions after validation: "
        f"{len(validated_questions)}"
    )

    # 11. Return validated questions
    if not validated_questions:
        raise ValueError(
            "No new valid quiz questions could be generated. "
            "Try a different page, topic, or lesson."
        )

    return validated_questions





def generate_flashcards(
    context,
    number_of_cards=5,
    language="Tamil",
):
    import json
    import random
    import time
    import httpx

    if not 1 <= number_of_cards <= 10:
        raise ValueError("Card count must be between 1 and 10.")

    if not isinstance(context, str) or not context.strip():
        raise ValueError(
            "PDF text is empty. Please check the uploaded PDF."
        )

    client = get_gemini_client()

    context = context.strip()

    # Limit the number of Gemini requests for large PDFs.
    chunk_size = 8000
    all_chunks = [
        context[i:i + chunk_size]
        for i in range(0, len(context), chunk_size)
        if context[i:i + chunk_size].strip()
    ]

    if len(all_chunks) <= 3:
        chunks = all_chunks
    else:
        # Sample from the beginning, middle and end of the PDF.
        indexes = [
            0,
            len(all_chunks) // 2,
            len(all_chunks) - 1,
        ]
        chunks = [all_chunks[i] for i in indexes]

    candidates = []

    for chunk_number, chunk in enumerate(chunks, start=1):
        prompt = f"""
You are an accurate textbook flashcard generator.

Create up to 5 useful question-answer flashcards from the
provided PDF text.

Rules:
- Use only facts present in the supplied text.
- Write all cards in {language}.
- Prefer important definitions, concepts and facts.
- Keep source_page from the page labels when available.
- Do not invent page numbers.
- Avoid duplicate questions.
- Keep each answer concise and useful for revision.
- Return only valid JSON.

Required JSON format:
{{
  "flashcards": [
    {{
      "front": "Question",
      "back": "Answer",
      "explanation": "Short explanation",
      "source_page": 1
    }}
  ]
}}

PDF text section {chunk_number}:
{chunk}
"""

        response = None

        # Retry once if the request times out.
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config={
                        "temperature": 0.3,
                        "max_output_tokens": 1800,
                        "response_mime_type": "application/json",
                    },
                )
                break


            except (
                httpx.TimeoutException,
                TimeoutError,
                ServerError,
            ) as exc:
                if attempt == 1:
                    raise ValueError(
                      "Gemini is temporarily unavailable or taking too long. "
                       "Please wait a little and try generating flashcards again."
               ) from exc

            time.sleep(3)

        if response is None or not response.text:
            continue

        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            continue

        section_cards = data.get("flashcards", [])

        if isinstance(section_cards, list):
            candidates.extend(
                card
                for card in section_cards
                if isinstance(card, dict)
            )

    if not candidates:
        raise ValueError(
            "No flashcards could be extracted from the PDF. "
            "Please try again."
        )

    # Remove duplicate questions.
    unique_candidates = []
    seen_questions = set()

    for card in candidates:
        front = card.get("front")
        back = card.get("back")

        if not isinstance(front, str) or not front.strip():
            continue

        if not isinstance(back, str) or not back.strip():
            continue

        normalized_front = " ".join(front.casefold().split())

        if normalized_front in seen_questions:
            continue

        seen_questions.add(normalized_front)

        unique_candidates.append(card)

    if not unique_candidates:
        raise ValueError(
            "No valid flashcards could be generated."
        )

    random.shuffle(unique_candidates)
    selected = unique_candidates[:number_of_cards]

    return [
        {
            "front": card["front"].strip(),
            "back": card["back"].strip(),
            "explanation": (
                card.get("explanation", "").strip()
                if isinstance(card.get("explanation", ""), str)
                else ""
            ),
            "source_page": (
                card.get("source_page")
                if isinstance(card.get("source_page"), int)
                and not isinstance(card.get("source_page"), bool)
                and card.get("source_page") >= 1
                else None
            ),
        }
        for card in selected
    ]



def generate_topic_revision_questions(
    topic,
    pdf_text,
    number_of_questions=5,
    language="Tamil",
):
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("Topic is required.")

    if not isinstance(pdf_text, str) or not pdf_text.strip():
        raise ValueError("PDF content is required.")

    if not 1 <= number_of_questions <= 10:
        raise ValueError("Question count must be between 1 and 10.")

    client = get_gemini_client()

    prompt = f"""
Create multiple-choice revision questions for students.

Requested topic: {topic}
Language: {language}
Number of questions: {number_of_questions}

IMPORTANT:
- Use ONLY the supplied PDF content.
- First determine whether the requested topic is covered in the PDF.
- If the topic is not covered, return:
  {{"error": "Requested topic is not covered in the provided PDF content."}}
- Do not create questions about unrelated topics.
- Never invent facts or use outside knowledge.
- If covered, create up to the requested number of questions.
- Each question must have exactly four non-empty options: A, B, C, D.
- correct_answer must be A, B, C, or D.
- Explanations must be supported by the PDF.
- Use source_page only when page labels are supplied.
- Return valid JSON only, without Markdown fences.

Expected JSON:
{{
  "questions": [
    {{
      "question": "Question text",
      "topic": "{topic}",
      "options": {{
        "A": "Option A",
        "B": "Option B",
        "C": "Option C",
        "D": "Option D"
      }},
      "correct_answer": "A",
      "explanation": "Explanation supported by the PDF",
      "source_page": 1
    }}
  ]
}}

PDF content:
{pdf_text[:5000]}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "temperature": 0.2,
            "max_output_tokens": 1800,
            "response_mime_type": "application/json",
        },
    )

    raw_response = response.text or ""

    print(
        "AI RAW RESPONSE:",
        repr(raw_response[:2000]),
        flush=True,
    )

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "The AI returned invalid revision quiz JSON. Please try again."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("The AI revision response must be a JSON object.")

    if data.get("error"):
        print(
            "TOPIC NOT COVERED:",
            data["error"],
            flush=True,
        )
        return []

    questions = data.get("questions", [])

    if not isinstance(questions, list):
        raise ValueError(
            "The AI revision response has no valid questions list."
        )

    print("AI QUESTIONS RECEIVED:", len(questions), flush=True)

    validated = []

    for item in questions[:number_of_questions]:
        if not isinstance(item, dict):
            continue

        question = item.get("question")
        options = item.get("options", {})
        correct = str(item.get("correct_answer", "")).upper()
        explanation = item.get("explanation", "")
        source_page = item.get("source_page")

        if not isinstance(question, str) or not question.strip():
            continue

        if not isinstance(options, dict):
            continue

        if not all(
            isinstance(options.get(key), str)
            and options[key].strip()
            for key in ("A", "B", "C", "D")
        ):
            continue

        if correct not in ("A", "B", "C", "D"):
            continue

        if not isinstance(explanation, str):
            explanation = ""

        if (
            not isinstance(source_page, int)
            or isinstance(source_page, bool)
            or source_page < 1
        ):
            source_page = None

        validated.append({
            "question": question.strip(),
            "topic": topic.strip()[:200],
            "options": {
                key: options[key].strip()
                for key in ("A", "B", "C", "D")
            },
            "correct_answer": correct,
            "explanation": explanation.strip(),
            "source_page": source_page,
        })

    print("GENERATED QUESTIONS COUNT:", len(validated), flush=True)

    return validated
