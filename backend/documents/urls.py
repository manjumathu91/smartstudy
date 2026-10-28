

from django.urls import path
from .views import (DocumentUploadView, DocumentListView,DocumentDetailView,DocumentPageView,DocumentTopicSearchView,SavedNoteListCreateView,
               SavedNoteDetailView,MultiFormatDocumentUploadView, DocumentAnalysisListView,
    DocumentAnalysisDetailView, MyLibraryView,)

urlpatterns = [
    path("", DocumentListView.as_view(), name="document-list"),
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path(
    "<int:document_id>/pages/<int:page_number>/",
    DocumentPageView.as_view(),
    name="document-page",
),
path(
    "search/",
    DocumentTopicSearchView.as_view(),
    name="document-topic-search",
),
path("saved-notes/", SavedNoteListCreateView.as_view(), name="saved-note-list-create"),
path("saved-notes/<int:pk>/", SavedNoteDetailView.as_view(), name="saved-note-detail"),
path(
    "analyze-upload/",
    MultiFormatDocumentUploadView.as_view(),
    name="multi-format-document-upload",
),
# Saved analysis APIs
    path(
        "analyses/",
        DocumentAnalysisListView.as_view(),
        name="document-analysis-list",
    ),
    path(
        "analyses/<int:pk>/",
        DocumentAnalysisDetailView.as_view(),
        name="document-analysis-detail",
    ),
    path(
    "my-library/",
    MyLibraryView.as_view(),
    name="my-library",
),

]
