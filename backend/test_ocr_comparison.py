
import pymupdf
from documents.ocr_utils import extract_page_text_with_ocr

pdf_path = r"C:\Users\SANJANIRA\Documents\TNPSC-Materials\02_SAMACHEER_TAMIL\06_TAMIL\6_Tamil_Term_1.pdf"

with pymupdf.open(pdf_path) as pdf:
    page = pdf[1]  # Second page

    # Normal PDF text extraction
    normal_text = page.get_text().strip()

    # OCR text extraction
    ocr_text = extract_page_text_with_ocr(page)

print("===== NORMAL EXTRACTION =====")
print("Length:", len(normal_text))
print(normal_text[:800])

print("\n===== OCR EXTRACTION =====")
print("Length:", len(ocr_text))
print(ocr_text[:800])
