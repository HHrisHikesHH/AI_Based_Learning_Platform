from django.db import models
from django.contrib.postgres.indexes import GinIndex
from users.models import User

# Try to import pgvector, fallback to regular field if not available
try:
    from pgvector.django import VectorField, IvfflatIndex
    HAS_PGVECTOR = True
except ImportError:
    # pgvector not installed, use TextField as fallback
    HAS_PGVECTOR = False
    VectorField = models.TextField
    IvfflatIndex = None


class DocumentManager(models.Manager):
    """Custom manager for Document model"""
    
    def with_modules(self):
        """Prefetch related modules"""
        return self.prefetch_related('modules')


class Document(models.Model):
    """Document model for uploaded files"""
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('EXTRACTING', 'Extracting'),
        ('CHUNKING', 'Chunking'),
        ('GENERATING_MODULES', 'Generating Modules'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='documents',
        db_index=True
    )
    title = models.CharField(max_length=500)
    file_path = models.CharField(max_length=1000)
    file_size = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True
    )
    processing_progress = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = DocumentManager()
    
    class Meta:
        db_table = 'documents'
        indexes = [
            models.Index(fields=['user_id'], name='idx_documents_user_id'),
            models.Index(fields=['status'], name='idx_documents_status'),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} ({self.status})"
    
    def get_processing_status(self):
        """Get current processing status with progress details"""
        return {
            'status': self.status,
            'progress': self.processing_progress,
            'error': self.error_message,
        }


class ProcessingJob(models.Model):
    """Idempotency tracking for document processing"""
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='processing_jobs'
    )
    idempotency_key = models.CharField(max_length=64, unique=True, db_index=True)
    task_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PENDING')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'processing_jobs'
        indexes = [
            models.Index(fields=['idempotency_key'], name='idx_proc_jobs_idemp'),
        ]
    
    def __str__(self):
        return f"Job {self.idempotency_key[:8]}... - {self.status}"


class Module(models.Model):
    """Module structure for organized content"""
    
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='modules',
        db_index=True
    )
    title = models.CharField(max_length=500)
    summary = models.TextField(null=True, blank=True)
    module_order = models.IntegerField()
    total_chunks = models.IntegerField(null=True, blank=True)
    is_quiz_ready = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'modules'
        indexes = [
            models.Index(fields=['document_id'], name='idx_modules_document_id'),
            models.Index(fields=['document_id', 'module_order'], name='idx_modules_order'),
        ]
        ordering = ['document', 'module_order']
        unique_together = [['document', 'module_order']]
    
    def __str__(self):
        return f"{self.document.title} - Module {self.module_order}: {self.title}"
    
    def is_ready_for_quiz(self):
        """Check if module is ready for quiz generation"""
        return self.is_quiz_ready and self.total_chunks and self.total_chunks > 0


class ModuleChunk(models.Model):
    """Chunks with vector embeddings for semantic search"""
    
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='chunks',
        db_index=True
    )
    content = models.TextField()
    chunk_order = models.IntegerField()
    metadata = models.JSONField(default=dict, blank=True)
    embedding = VectorField(dimensions=768, null=True, blank=True) if HAS_PGVECTOR else models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'module_chunks'
        indexes = [
            models.Index(fields=['module_id'], name='idx_chunks_module_id'),
        ] + ([
            IvfflatIndex(
                fields=['embedding'],
                name='idx_chunks_embedding',
                opclasses=['vector_cosine_ops'],
            ),
        ] if (HAS_PGVECTOR and IvfflatIndex) else [])
        ordering = ['module', 'chunk_order']
    
    def __str__(self):
        return f"Chunk {self.chunk_order} of {self.module.title}"
