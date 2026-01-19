from django.contrib import admin
from .models import Quiz, Question, QuizAttempt, UserAnswer


class QuestionInline(admin.TabularInline):
    """Inline admin for Questions"""
    model = Question
    extra = 0
    fields = ['question_order', 'question_text', 'question_type', 'correct_answer', 'concept_covered']


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    """Admin interface for Quiz model"""
    list_display = ['module', 'difficulty', 'total_questions', 'estimated_duration_minutes', 'created_at']
    list_filter = ['difficulty', 'created_at']
    search_fields = ['module__title', 'module__document__title']
    readonly_fields = ['created_at']
    raw_id_fields = ['module']
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Admin interface for Question model"""
    list_display = ['question_text', 'quiz', 'question_type', 'concept_covered', 'difficulty_score', 'question_order']
    list_filter = ['question_type', 'concept_covered', 'created_at']
    search_fields = ['question_text', 'concept_covered', 'quiz__module__title']
    readonly_fields = ['created_at']
    raw_id_fields = ['quiz']


class UserAnswerInline(admin.TabularInline):
    """Inline admin for UserAnswers"""
    model = UserAnswer
    extra = 0
    readonly_fields = ['question', 'user_answer', 'is_correct', 'answered_at']


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    """Admin interface for QuizAttempt model"""
    list_display = ['user', 'quiz', 'score', 'attempt_number', 'started_at', 'completed_at']
    list_filter = ['started_at', 'completed_at']
    search_fields = ['user__email', 'quiz__module__title']
    readonly_fields = ['started_at', 'completed_at']
    raw_id_fields = ['user', 'quiz']
    inlines = [UserAnswerInline]


@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    """Admin interface for UserAnswer model"""
    list_display = ['attempt', 'question', 'is_correct', 'confidence_level', 'time_spent_seconds', 'answered_at']
    list_filter = ['is_correct', 'confidence_level', 'answered_at']
    search_fields = ['attempt__user__email', 'question__question_text']
    readonly_fields = ['answered_at']
    raw_id_fields = ['attempt', 'question']
