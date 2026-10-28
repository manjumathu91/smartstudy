
import pymupdf
from documents.ocr_utils import extract_page_text_with_ocr

pdf_path = r"C:\Users\SANJANIRA\Documents\TNPSC-Materials\02_SAMACHEER_TAMIL\06_TAMIL\6_Tamil_Term_1.pdf"

with pymupdf.open(pdf_path) as pdf:
    page = pdf[1]  # Second page
    text = extract_page_text_with_ocr(page)

print("OCR TEXT LENGTH:", len(text))
print("\nOCR OUTPUT:")
print(text[:2000])
