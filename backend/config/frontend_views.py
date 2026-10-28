

from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404


ALLOWED_PAGES = {
    "index.html",
    "login.html",
    "register.html",
    "dashboard.html",
    "upload.html",
    "notes.html",
    "quiz.html",
    "flashcards.html",
    "planners.html",
    "revision.html",
    "mylibrary.html",
    "forgotpassword.html",
    "reset-password.html",
    "aistudychat.html",
    
}


def frontend_page(request, page="index.html"):
    if page not in ALLOWED_PAGES:
        raise Http404("Page not found")

    file_path = Path(settings.FRONTEND_DIR) / page

    if not file_path.is_file():
        raise Http404(f"Frontend file not found: {page}")

    return FileResponse(
        open(file_path, "rb"),
        content_type="text/html; charset=utf-8",
    )
