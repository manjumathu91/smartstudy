from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)


FONT_PATH = (
    Path(__file__).resolve().parent.parent
    / "NirmalaUI-Regular.ttf"
)


def create_notes_pdf(title, content):
    if not FONT_PATH.exists():
        raise FileNotFoundError(
            f"Font file not found: {FONT_PATH}"
        )

    if "NirmalaUI" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont("NirmalaUI", str(FONT_PATH))
        )

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    styles["Title"].fontName = "NirmalaUI"
    styles["BodyText"].fontName = "NirmalaUI"
    styles["BodyText"].leading = 18

    story = [
        Paragraph(title, styles["Title"]),
        Spacer(1, 8 * mm),
        Paragraph(
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>"),
            styles["BodyText"],
        ),
    ]

    document.build(story)
    buffer.seek(0)
    return buffer
