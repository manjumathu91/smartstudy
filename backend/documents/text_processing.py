

import re


def clean_text(text):
    """
    Clean whitespace in extracted PDF text
    without changing the original words.
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Remove invisible control characters,
    # but preserve tabs and line breaks
    text = re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
        "",
        text,
    )

    # Replace non-breaking spaces
    text = text.replace("\u00a0", " ")

    # Remove unnecessary spaces and tabs
    text = re.sub(r"[ \t]+", " ", text)

    # Remove spaces at the start and end of each line
    text = "\n".join(
        line.strip() for line in text.split("\n")
    )

    # Reduce repeated blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def text_quality_score(text):
    """
    Estimate extracted text quality.
    This is a heuristic, not a Tamil spell checker.
    """
    if not text:
        return 0.0

    text = clean_text(text)

    if not text:
        return 0.0

    total = len(text)
    tamil_chars = sum(
        1 for ch in text
        if "\u0B80" <= ch <= "\u0BFF"
    )
    replacement_chars = text.count("\uFFFD")
    control_chars = sum(
        1 for ch in text
        if ord(ch) < 32 and ch not in "\n\t"
    )

    tamil_ratio = tamil_chars / total
    replacement_ratio = replacement_chars / total
    control_ratio = control_chars / total

    score = (
        tamil_ratio * 100
        - replacement_ratio * 100
        - control_ratio * 100
    )

    # Penalize common extraction-corruption patterns.
    if "\uFFFD" in text:
        score -= 10

    return max(0.0, score)


def needs_ocr(text):
    """
    Identify text that may need OCR review.
    This is a simple heuristic, not a final quality decision.
    """
    if not text or len(text.strip()) < 100:
        return True

    text = clean_text(text)

    # Replacement characters indicate possible extraction errors.
    if "\uFFFD" in text:
        return True

    # Common corrupted-PDF pattern seen in our test.
    if "\uFFFD" in text or "கக" in text:
        return True

    return False



def split_into_chunks(text, chunk_size=1000, overlap=150):
    if chunk_size <= 0:
        raise ValueError(
            "chunk_size must be greater than zero"
        )

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be >= 0 and smaller than chunk_size"
        )

    text = clean_text(text)

    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        # Prefer sentence or line boundaries
        if end < text_length:
            candidates = [
                text.rfind("\n", start, end),
                text.rfind(". ", start, end),
                text.rfind("! ", start, end),
                text.rfind("? ", start, end),
                text.rfind(" ", start, end),
            ]

            boundary = max(candidates)

            if boundary > start + chunk_size // 2:
                end = boundary + 1

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        next_start = max(start + 1, end - overlap)

        # Avoid starting in the middle of a word
        while (
            next_start < end
            and next_start > 0
            and not text[next_start - 1].isspace()
            and not text[next_start].isspace()
        ):
            next_start += 1

        start = next_start

    return chunks

def extract_pages_from_pdf(pdf_bytes):
    """
    Extract text from each PDF page separately.
    Preserve the original PDF page numbers.
    """
    import pymupdf

    pages = []

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        if pdf.needs_pass:
            raise ValueError(
                "Password-protected PDFs are not supported."
            )

        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()

            pages.append({
                "page_number": page_number,
                "text": clean_text(text),
                "needs_ocr": not bool(text),
            })

    return pages

