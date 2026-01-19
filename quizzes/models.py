from django.db import models
from django.contrib.postgres.indexes import GinIndex
from users.models import User
from documents.models import Module


class QuizManager(models.Manager):
    """Custom manager for Quiz model"""
    
    def with_questions(self):
        """Prefetch related questions"""
        return self.prefetch_related('questions')


class Quiz(models.Model):
    """Pre-generated quiz for a module"""
    
    DIFFICULTY_CHOICES = [
        ('EASY', 'Easy'),
        ('MEDIUM', 'Medium'),
        ('HARD', 'Hard'),
    ]
    
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='quizzes',
        db_index=True
    )
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default='MEDIUM'
    )
    total_questions = models.IntegerField(null=True, blank=True)
    estimated_duration_minutes = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    objects = QuizManager()
    
    class Meta:
        db_table = 'quizzes'
        indexes = [
            models.Index(fields=['module_id'], name='idx_quizzes_module_id'),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Quiz for {self.module.title} ({self.difficulty})"


class Question(models.Model):
    """Questions with validation metadata"""
    
    QUESTION_TYPE_CHOICES = [
        ('MCQ', 'Multiple Choice'),
        ('TRUE_FALSE', 'True/False'),
        ('SHORT_ANSWER', 'Short Answer'),
    ]
    
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='questions',
        db_index=True
    )
    question_text = models.TextField()
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default='MCQ'
    )
    options = models.JSONField()  # ["option1", "option2", "option3", "option4"]
    correct_answer = models.CharField(max_length=500)
    explanation = models.TextField(null=True, blank=True)
    concept_covered = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    difficulty_score = models.FloatField(null=True, blank=True)
    distractor_quality_score = models.FloatField(null=True, blank=True)
    question_order = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'questions'
        indexes = [
            models.Index(fields=['quiz_id'], name='idx_questions_quiz_id'),
            models.Index(fields=['concept_covered'], name='idx_questions_concept'),
        ]
        ordering = ['quiz', 'question_order']
    
    def __str__(self):
        return f"Q{self.question_order}: {self.question_text[:50]}..."


class QuizAttemptManager(models.Manager):
    """Custom manager for QuizAttempt model"""
    
    def with_answers(self):
        """Prefetch related user answers"""
        return self.prefetch_related('user_answers')


class QuizAttempt(models.Model):
    """User quiz attempts"""
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
        db_index=True
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts',
        db_index=True
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)  # Percentage
    time_spent_seconds = models.IntegerField(null=True, blank=True)
    attempt_number = models.IntegerField(default=1)
    
    objects = QuizAttemptManager()
    
    class Meta:
        db_table = 'quiz_attempts'
        indexes = [
            models.Index(fields=['user_id'], name='idx_attempts_user_id'),
            models.Index(fields=['quiz_id'], name='idx_attempts_quiz_id'),
        ]
        unique_together = [['user', 'quiz', 'attempt_number']]
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.quiz} (Attempt {self.attempt_number})"
    
    def calculate_score(self):
        """Calculate score based on user answers"""
        answers = self.user_answers.all()
        if not answers.exists():
            return None
        
        correct_count = answers.filter(is_correct=True).count()
        total_count = answers.count()
        
        if total_count == 0:
            return None
        
        score = (correct_count / total_count) * 100
        self.score = score
        self.save(update_fields=['score'])
        return score


class UserAnswer(models.Model):
    """Individual answer tracking for personalization"""
    
    CONFIDENCE_LEVEL_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]
    
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name='user_answers',
        db_index=True
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='user_answers',
        db_index=True
    )
    user_answer = models.TextField()
    is_correct = models.BooleanField()
    time_spent_seconds = models.IntegerField(null=True, blank=True)
    confidence_level = models.CharField(
        max_length=20,
        choices=CONFIDENCE_LEVEL_CHOICES,
        null=True,
        blank=True
    )
    answered_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'user_answers'
        indexes = [
            models.Index(fields=['attempt_id'], name='idx_answers_attempt_id'),
            models.Index(fields=['question_id'], name='idx_answers_question_id'),
        ]
    
    def __str__(self):
        return f"Answer for {self.question} - {'Correct' if self.is_correct else 'Incorrect'}"
