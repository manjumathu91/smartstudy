
import hashlib
from django.conf import settings
from django.db import models



class Document(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )

    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")

    subject = models.CharField(max_length=100, blank=True)
    language = models.CharField(
        max_length=20,
        default="Both",
    )
    class_level = models.CharField(max_length=50, blank=True)
    DOCUMENT_TYPE_CHOICES = [
        ("textbook", "Textbook / Study Book"),
        ("general", "General PDF / Document"),
    ]

    document_type = models.CharField(
        max_length=20,
        choices=DOCUMENT_TYPE_CHOICES,
        default="general",
        db_index=True,
    )
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    extracted_text = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class DocumentPage(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="pages",
    )
    page_number = models.PositiveIntegerField()
    extracted_text = models.TextField(blank=True)
    needs_ocr = models.BooleanField(default=False)

    class Meta:
        ordering = ["page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "page_number"],
                name="unique_document_page",
            )
        ]

    def __str__(self):
        return f"{self.document.title} - Page {self.page_number}"
    
class SavedNote(models.Model):
    NOTE_TYPES = [
        ("page", "Page-wise"),
        ("topic", "Topic-wise"),
        ("lesson", "Lesson-wise"),
        ("study", "Study Notes"),
    ]

    LANGUAGE_CHOICES = [
        ("Tamil", "Tamil"),
        ("English", "English"),
        ("Both", "Tamil + English"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_notes",
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="saved_notes",
    )

    title = models.CharField(max_length=255)
    note_type = models.CharField(
        max_length=20,
        choices=NOTE_TYPES,
    )
    content = models.TextField()

    topic = models.CharField(max_length=255, blank=True)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(
        max_length=20,
        choices=LANGUAGE_CHOICES,
        default="Both",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} - {self.owner}"

class DocumentAnalysis(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="document_analyses",
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="analyses",
    )

    analysis_type = models.CharField(
        max_length=50,
        default="summary",
    )

    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    extracted_text = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} - {self.owner}"