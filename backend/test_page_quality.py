

import pymupdf

from documents.text_processing import (
    clean_text,
    text_quality_score,
)
from documents.ocr_utils import extract_page_text_with_ocr


pdf_path = r"C:\Users\SANJANIRA\Documents\TNPSC-Materials\02_SAMACHEER_TAMIL\06_TAMIL\6_Tamil_Term_1.pdf"


with pymupdf.open(pdf_path) as pdf:
    for page_number in [2, 3, 4]:
        if page_number >= len(pdf):
            continue

        page = pdf[page_number]

        # Normal PDF text extraction
        normal_text = clean_text(page.get_text())

        # OCR extraction
        ocr_text = clean_text(
            extract_page_text_with_ocr(page)
        )

        print(f"\n{'=' * 20} PAGE {page_number + 1} {'=' * 20}")

        print("Normal text length:", len(normal_text))
        print("OCR text length:", len(ocr_text))

        print(
            "Normal quality score:",
            round(text_quality_score(normal_text), 2),
        )
        print(
            "OCR quality score:",
            round(text_quality_score(ocr_text), 2),
        )

        print("\nNORMAL TEXT (first 300 chars):")
        print(normal_text[:300])

        print("\nOCR TEXT (first 300 chars):")
        print(ocr_text[:300])
