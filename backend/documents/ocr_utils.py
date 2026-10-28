
import subprocess
from pathlib import Path

import pymupdf


TESSERACT_PATH = Path(
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def extract_page_text_with_ocr(page, languages="tam+eng"):
    """
    Convert one PDF page to an image and extract text using OCR.
    """
    if not TESSERACT_PATH.is_file():
        raise FileNotFoundError(
            f"Tesseract executable not found: {TESSERACT_PATH}"
        )

    pix = page.get_pixmap(dpi=300, alpha=False)
    image_bytes = pix.tobytes("png")

    result = subprocess.run(
        [
            str(TESSERACT_PATH),
            "stdin",
            "stdout",
            "-l",
            languages,
        ],
        input=image_bytes,
        capture_output=True,
        timeout=120,
    )

    if result.returncode != 0 and not result.stdout:
        error_message = result.stderr.decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(
            f"Tesseract OCR failed: {error_message}"
        )

    return result.stdout.decode(
        "utf-8", errors="replace"
    ).strip()
