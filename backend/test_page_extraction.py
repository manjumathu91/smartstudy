
from pathlib import Path

from documents.text_processing import extract_pages_from_pdf

pdf_path = Path(
    r"C:\Users\SANJANIRA\Documents\TNPSC-Materials\02_SAMACHEER_TAMIL\06_TAMIL\6_Tamil_Term_1.pdf"
)

pdf_bytes = pdf_path.read_bytes()
pages = extract_pages_from_pdf(pdf_bytes)

print("Total pages:", len(pages))

for page in pages[:3]:
    print("\n------------------------------")
    print("Page number:", page["page_number"])
    print("Needs OCR:", page["needs_ocr"])
    print("Text preview:", page["text"][:300])
