

from django.conf import settings
from django.db import models

class QuizSession(models.Model):
    SCOPE_CHOICES = [
        ("page", "Page"),
        ("topic", "Topic"),
        ("lesson", "Lesson"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_sessions",
    )

    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="quiz_sessions",
    )

    scope = models.CharField(
        max_length=10,
        choices=SCOPE_CHOICES,
    )

    scope_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
    )

    page_number = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    language = models.CharField(
        max_length=10,
        default="Tamil",
    )

    batch_size = models.PositiveIntegerField(default=5)

    # Previously generated question text is tracked here.
    seen_questions = models.JSONField(default=list, blank=True)

    # Progress across submitted batches.
    attempt_ids = models.JSONField(default=list, blank=True)
    questions_practiced = models.PositiveIntegerField(default=0)
    correct_answers_total = models.PositiveIntegerField(default=0)

    is_completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.scope} quiz session #{self.pk}"
        )
    
class QuizAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    session = models.ForeignKey(
    "QuizSession",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="attempts",
)
    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    score = models.FloatField(default=0)
    questions_data = models.JSONField(default=list)
    quiz_type = models.CharField(
    max_length=20,
    choices=[
        ("quiz", "Quiz"),
        ("revision", "Revision"),
    ],
    default="quiz",
    db_index=True,
)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def accuracy(self):
        if self.total_questions == 0:
            return 0
        return round(
            self.correct_answers / self.total_questions * 100, 2
        )

    def __str__(self):
        return f"{self.user.username} - {self.score}%"


class QuizAnswer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.TextField()
    topic = models.CharField(max_length=200, db_index=True)
    selected_answer = models.CharField(max_length=500, blank=True)
    correct_answer = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.topic} - {'Correct' if self.is_correct else 'Incorrect'}"

class SavedFlashcardSet(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_flashcard_sets",
    )
    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="saved_flashcard_sets",
    )
    title = models.CharField(max_length=255)
    language = models.CharField(max_length=20, default="Tamil")
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    cards = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} - {self.user}"


class SavedStudyPlan(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_study_plans",
    )
    title = models.CharField(max_length=255, default="My Study Plan")
    exam_date = models.DateField()
    daily_hours = models.FloatField()
    topics = models.JSONField(default=list, blank=True)
    plan = models.JSONField(default=list, blank=True)
    days_available = models.PositiveIntegerField(default=1)
    total_study_hours = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} - {self.user}"
class StudyTimeSession(models.Model):
    PAGE_CHOICES = [
        ("notes", "Notes / PDF Analysis"),
        ("quiz", "Quiz"),
        ("revision", "Revision"),
        ("flashcards", "Flashcards"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_time_sessions",
    )
    session_id = models.CharField(max_length=100)
    page_type = models.CharField(
        max_length=20,
        choices=PAGE_CHOICES,
        default="notes",
    )
    total_seconds = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "session_id"],
                name="unique_user_study_time_session",
            ),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.page_type} - {self.total_seconds}s"
    
class StudyChat(models.Model):
    MODE_CHOICES = [
        ("explain", "Explain"),
        ("diagram", "Diagram"),
        ("sticky_notes", "Sticky Notes"),
        ("visualize", "Visualize"),
        ("practice", "Practice"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_study_chats",
    )
    title = models.CharField(max_length=200, default="New Chat")
    mode = models.CharField(
        max_length=20,
        choices=MODE_CHOICES,
        default="explain",
    )
    language = models.CharField(max_length=20, default="Tamil")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} - {self.user}"


class StudyChatMessage(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    chat = models.ForeignKey(
        StudyChat,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    mode = models.CharField(max_length=20, default="explain")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.role} - Chat #{self.chat_id}"


class StudyChatAttachment(models.Model):
    chat = models.ForeignKey(
        StudyChat,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    message = models.ForeignKey(
        StudyChatMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to="study_chat_uploads/%Y/%m/",
    )
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    file_size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.original_name


class StudyActivity(models.Model):
    ACTIVITY_CHOICES = [
        ("question", "Study Question"),
        ("image_question", "Image Question"),
        ("diagram", "Diagram"),
        ("sticky_notes", "Sticky Notes"),
        ("visualize", "Visualize"),
        ("practice", "Practice"),
        ("voice", "Voice Chat"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_study_activities",
    )
    chat = models.ForeignKey(
        StudyChat,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities",
    )
    activity_type = models.CharField(
        max_length=20,
        choices=ACTIVITY_CHOICES,
    )
    topic = models.CharField(max_length=255, blank=True, default="")
    duration_seconds = models.PositiveIntegerField(default=0)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.activity_type}"
