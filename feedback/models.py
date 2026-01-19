from django.db import models
from users.models import User
from documents.models import Module, Document
from quizzes.models import QuizAttempt


class FeedbackReport(models.Model):
    """Personalized feedback reports"""
    
    attempt = models.OneToOneField(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name='feedback_report',
        db_index=True
    )
    overall_feedback = models.TextField()
    strengths = models.JSONField(default=list, blank=True)  # ["Good understanding of X", ...]
    weaknesses = models.JSONField(default=list, blank=True)  # ["Struggled with Y", ...]
    recommended_topics = models.JSONField(default=list, blank=True)  # ["Topic A", "Topic B"]
    personalized_message = models.TextField(null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'feedback_reports'
        indexes = [
            models.Index(fields=['attempt_id'], name='idx_feedback_attempt_id'),
        ]
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"Feedback for {self.attempt}"


class UserModuleProgress(models.Model):
    """User progress tracking at module level"""
    
    COMPLETION_STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='module_progress',
        db_index=True
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='user_progress',
        db_index=True
    )
    completion_status = models.CharField(
        max_length=50,
        choices=COMPLETION_STATUS_CHOICES,
        default='NOT_STARTED'
    )
    best_score = models.FloatField(null=True, blank=True)
    attempts_count = models.IntegerField(default=0)
    mastery_level = models.FloatField(null=True, blank=True)  # 0.0 to 1.0
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'user_module_progress'
        indexes = [
            models.Index(fields=['user_id'], name='idx_progress_user_id'),
        ]
        unique_together = [['user', 'module']]
    
    def __str__(self):
        return f"{self.user.email} - {self.module.title} ({self.completion_status})"


class UserDocumentStats(models.Model):
    """Aggregate statistics for overall performance"""
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='document_stats',
        db_index=True
    )
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='user_stats',
        db_index=True
    )
    total_modules = models.IntegerField(default=0)
    completed_modules = models.IntegerField(default=0)
    average_score = models.FloatField(null=True, blank=True)
    total_time_spent_seconds = models.IntegerField(default=0)
    weak_concepts = models.JSONField(default=list, blank=True)
    strong_concepts = models.JSONField(default=list, blank=True)
    last_updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_document_stats'
        indexes = [
            models.Index(fields=['user_id'], name='idx_doc_stats_user_id'),
        ]
        unique_together = [['user', 'document']]
    
    def __str__(self):
        return f"{self.user.email} - {self.document.title} Stats"
