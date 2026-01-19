# E-Learning Platform

A Django-based e-learning platform with document processing, quiz generation, and personalized feedback using AI.

## Features

- **Document Management**: Upload and process documents (PDF, DOCX, etc.)
- **AI-Powered Processing**: Extract text, chunk content, generate embeddings
- **Module Generation**: Automatically organize content into learning modules
- **Quiz System**: Pre-generated quizzes with multiple question types
- **Personalized Feedback**: AI-generated feedback based on user performance
- **Progress Tracking**: Track user progress at module and document levels
- **Vector Search**: Semantic search using pgvector embeddings

## Tech Stack

- Django 5.0+
- PostgreSQL with pgvector extension
- Celery with Redis
- Django REST Framework
- Langchain for AI processing

## Setup Instructions

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 12+ with pgvector extension
- Redis server

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Database Setup

#### Install pgvector extension in PostgreSQL

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

#### Configure Database

1. Create a `.env` file from `.env.example`:
```bash
cp .env.example .env
```

2. Update `.env` with your database credentials:
```
DB_NAME=elearning_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

3. Set `USE_POSTGRES=True` in `.env` to use PostgreSQL:
```
USE_POSTGRES=True
```

### 4. Run Migrations

```bash
python manage.py migrate
```

**Note**: The initial migrations were created with SQLite. When switching to PostgreSQL, you may need to:

1. Enable pgvector extension (see above)
2. Run migrations again
3. The vector index will be created automatically if pgvector is installed

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Setup Celery

#### Start Redis (if not running)

```bash
redis-server
```

#### Start Celery Worker

```bash
celery -A elearning_platform worker -l info
```

#### Start Celery Beat (for scheduled tasks)

```bash
celery -A elearning_platform beat -l info
```

### 7. Run Development Server

```bash
python manage.py runserver
```

## Project Structure

```
elearning_platform/
├── documents/          # Document processing and module management
├── quizzes/            # Quiz generation and attempts
├── feedback/           # Personalized feedback and progress tracking
├── users/              # Custom user model
└── elearning_platform/ # Project settings and configuration
```

## Models Overview

### Core Models

- **User**: Custom user model extending AbstractUser
- **Document**: Uploaded documents with processing status
- **Module**: Organized content modules
- **ModuleChunk**: Content chunks with vector embeddings
- **ProcessingJob**: Idempotency tracking for document processing

### Quiz Models

- **Quiz**: Pre-generated quizzes for modules
- **Question**: Quiz questions with validation metadata
- **QuizAttempt**: User quiz attempts
- **UserAnswer**: Individual answer tracking

### Progress & Feedback Models

- **FeedbackReport**: Personalized feedback reports
- **UserModuleProgress**: Module-level progress tracking
- **UserDocumentStats**: Document-level aggregate statistics

## Model Managers

- `Document.objects.with_modules()` - Prefetch related modules
- `Quiz.objects.with_questions()` - Prefetch related questions
- `QuizAttempt.objects.with_answers()` - Prefetch related answers

## Model Methods

- `Document.get_processing_status()` - Get processing status with progress
- `Module.is_ready_for_quiz()` - Check if module is ready for quiz generation
- `QuizAttempt.calculate_score()` - Calculate score based on user answers

## Admin Panel

All models are registered in the Django admin. Access at `/admin/` after creating a superuser.

## Environment Variables

See `.env.example` for all available environment variables.

## Validation Checklist

- ✅ Can run: `python manage.py makemigrations`
- ✅ Can run: `python manage.py migrate`
- ⚠️ pgvector extension enabled (requires manual setup in PostgreSQL)
- ⚠️ Celery worker starts without errors (requires Redis and dependencies)
- ✅ Admin panel shows all models

## Notes

- The project is configured to work with or without optional dependencies (pgvector, celery, etc.)
- For production, ensure all dependencies are installed and properly configured
- Vector embeddings require pgvector extension in PostgreSQL
- Celery tasks are defined but need implementation based on your AI processing requirements

