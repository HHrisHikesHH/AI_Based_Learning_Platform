from django.contrib import admin
from .models import Document, ProcessingJob, Module, ModuleChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin interface for Document model"""
    list_display = ['title', 'user', 'status', 'file_size', 'created_at', 'updated_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['user']


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    """Admin interface for ProcessingJob model"""
    list_display = ['idempotency_key', 'document', 'status', 'retry_count', 'started_at']
    list_filter = ['status', 'started_at']
    search_fields = ['idempotency_key', 'task_id', 'document__title']
    readonly_fields = ['started_at', 'completed_at']
    raw_id_fields = ['document']


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    """Admin interface for Module model"""
    list_display = ['title', 'document', 'module_order', 'total_chunks', 'is_quiz_ready', 'created_at']
    list_filter = ['is_quiz_ready', 'created_at']
    search_fields = ['title', 'document__title']
    readonly_fields = ['created_at']
    raw_id_fields = ['document']


@admin.register(ModuleChunk)
class ModuleChunkAdmin(admin.ModelAdmin):
    """Admin interface for ModuleChunk model"""
    list_display = ['module', 'chunk_order', 'has_embedding', 'created_at']
    list_filter = ['created_at']
    search_fields = ['module__title', 'content']
    readonly_fields = ['created_at']
    raw_id_fields = ['module']
    
    def has_embedding(self, obj):
        return obj.embedding is not None
    has_embedding.boolean = True
    has_embedding.short_description = 'Has Embedding'
