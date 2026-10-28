

from rest_framework import serializers
from .models import Document,SavedNote,DocumentAnalysis


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "file",
            "subject",
            "language",
            "class_level",
            "document_type",
            "extracted_text",
            "uploaded_at",
        ]
        read_only_fields = [
            "id",
            "extracted_text",
            "uploaded_at",
        ]
class SavedNoteSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(
        source="document.title",
        read_only=True
    )

    class Meta:
        model = SavedNote
        fields = [
            "id",
            "document",
            "document_title",
            "title",
            "note_type",
            "content",
            "topic",
            "page_number",
            "language",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "document_title",
            "created_at",
            "updated_at",
        ]
        
class DocumentAnalysisSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(
        source="document.title",
        read_only=True,
    )

    class Meta:
        model = DocumentAnalysis
        fields = [
            "id",
            "document",
            "document_title",
            "analysis_type",
            "title",
            "summary",
            "notes",
            "extracted_text",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "document_title",
            "created_at",
            "updated_at",
        ]
