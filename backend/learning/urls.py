


from django.urls import path
from .views import (
    PDFQuestionAnswerView,
    StudyContentView,
    StudyQuizView,
    DetectPDFLessonsView,
    LessonSummaryView,
    StudyFlashcardView,
    StudyPlannerView,
    NotesPDFExportView,
    QuizSubmitView,
    SmartRevisionView,
    TopicRevisionQuizView,
    SavedFlashcardSetListView,
    SavedStudyPlanListView,
    DashboardStatsView,
    StudyTimeTrackingView,
    StudyPlanProgressView,
    AIStudyChatView,
    AIStudyChatHistoryView,
    AIStudyChatDetailView,
)


urlpatterns = [
    path(
        "ask/",
        PDFQuestionAnswerView.as_view(),
        name="pdf-question-answer",
    ),
    path(
      "study-content/",
       StudyContentView.as_view(),
       name="study-content",
), 
path(
    "detect-lessons/",
    DetectPDFLessonsView.as_view(),
    name="detect-pdf-lessons",
),
path(
    "lesson-summary/",
    LessonSummaryView.as_view(),
    name="lesson-summary",
),

     path("quiz/", StudyQuizView.as_view(), name="study-quiz"),
     path(
        "flashcards/",
        StudyFlashcardView.as_view(),
        name="study-flashcards",
    ),
    path(
    "planner/",
    StudyPlannerView.as_view(),
    name="study-planner",
),
path(
    "export-pdf/",
    NotesPDFExportView.as_view(),
    name="export-notes-pdf",
),
path("quiz/submit/", QuizSubmitView.as_view(), name="quiz-submit"),
path(
    "revision/",
    SmartRevisionView.as_view(),
    name="smart-revision",
),
path(
    "revision/quiz/",
    TopicRevisionQuizView.as_view(),
    name="topic-revision-quiz",
),
path(
    "saved-flashcards/",
    SavedFlashcardSetListView.as_view(),
    name="saved-flashcards",
),
path(
    "saved-plans/",
    SavedStudyPlanListView.as_view(),
    name="saved-plans",
),
path(
    "dashboard-stats/",
    DashboardStatsView.as_view(),
    name="dashboard-stats",
),
path(
    "study-time/",
    StudyTimeTrackingView.as_view(),
    name="study-time-tracking",
),
path(
    "saved-plans/<int:plan_id>/progress/",
    StudyPlanProgressView.as_view(),
    name="study-plan-progress",
),
path(
    "ai-study-chat/",
    AIStudyChatView.as_view(),
    name="ai-study-chat",
),
path(
    "ai-study-chat/history/",
    AIStudyChatHistoryView.as_view(),
    name="ai-study-chat-history",
),
path(
    "ai-study-chat/<int:chat_id>/",
    AIStudyChatDetailView.as_view(),
    name="ai-study-chat-detail",
),
]
