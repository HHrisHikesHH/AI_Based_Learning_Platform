from django.contrib import admin
from .models import FeedbackReport, UserModuleProgress, UserDocumentStats


@admin.register(FeedbackReport)
class FeedbackReportAdmin(admin.ModelAdmin):
    """Admin interface for FeedbackReport model"""
    list_display = ['attempt', 'generated_at']
    list_filter = ['generated_at']
    search_fields = ['attempt__user__email', 'attempt__quiz__module__title']
    readonly_fields = ['generated_at']
    raw_id_fields = ['attempt']


@admin.register(UserModuleProgress)
class UserModuleProgressAdmin(admin.ModelAdmin):
    """Admin interface for UserModuleProgress model"""
    list_display = ['user', 'module', 'completion_status', 'best_score', 'attempts_count', 'mastery_level', 'last_accessed_at']
    list_filter = ['completion_status', 'last_accessed_at']
    search_fields = ['user__email', 'module__title']
    readonly_fields = ['last_accessed_at']
    raw_id_fields = ['user', 'module']


@admin.register(UserDocumentStats)
class UserDocumentStatsAdmin(admin.ModelAdmin):
    """Admin interface for UserDocumentStats model"""
    list_display = ['user', 'document', 'total_modules', 'completed_modules', 'average_score', 'last_updated_at']
    list_filter = ['last_updated_at']
    search_fields = ['user__email', 'document__title']
    readonly_fields = ['last_updated_at']
    raw_id_fields = ['user', 'document']
