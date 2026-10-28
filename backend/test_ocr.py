

import pymupdf
import subprocess
from pathlib import Path

# PDF file path
pdf_path = Path(
    r"C:\Users\SANJANIRA\Documents\TNPSC-Materials\02_SAMACHEER_TAMIL\06_TAMIL\6_Tamil_Term_1.pdf"
)

# Tesseract executable path
tesseract_path = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Output files in the current backend folder
image_path = Path("test_page.png")
output_path = Path("ocr_output.txt")

# Check whether required files exist
if not pdf_path.is_file():
    raise FileNotFoundError(f"PDF not found: {pdf_path}")

if not Path(tesseract_path).is_file():
    raise FileNotFoundError(
        f"Tesseract not found: {tesseract_path}"
    )

# Convert the second PDF page to an image
with pymupdf.open(pdf_path) as pdf:
    if len(pdf) < 2:
        raise ValueError("The PDF has fewer than 2 pages.")

    page = pdf[1]
    pix = page.get_pixmap(dpi=300, alpha=False)
    pix.save(str(image_path))

print("Page image created:", image_path)

# Run Tamil + English OCR
result = subprocess.run(
    [
        tesseract_path,
        str(image_path),
        "stdout",
        "-l",
        "tam+eng",
    ],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)

# Save OCR text using UTF-8 encoding
with output_path.open(
    "w",
    encoding="utf-8-sig",
    newline="",
) as file:
    file.write(result.stdout)

# Display the result
print("\nReturn code:", result.returncode)
print("OCR text length:", len(result.stdout))
print("OCR OUTPUT:")
print(result.stdout[:3000])

if result.stderr:
    print("\nOCR MESSAGES:")
    print(result.stderr[:1000])

print("\nOCR text saved to:", output_path.resolve())
