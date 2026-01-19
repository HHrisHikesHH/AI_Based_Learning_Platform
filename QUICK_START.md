# Quick Start Guide

## Backend Setup

```bash
# Activate virtual environment
source .venv/bin/activate

# Set environment variables
export USE_POSTGRES=True
export DB_NAME=elearning_db
export DB_USER=postgres
export DB_PASSWORD=postgres
export DB_HOST=localhost
export DB_PORT=5432
export GEMINI_API_KEY=AIzaSyChB5QNN8iT-skPizyQPyFKvAv1AuUz9gk

# Run migrations
python manage.py migrate

# Create superuser (if needed)
python manage.py createsuperuser --username admin --email admin@example.com
# Password: admin

# Start server
python manage.py runserver
```

Backend will run on: **http://localhost:8000**

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend will run on: **http://localhost:5173**

## Complete Flow

1. **Start Backend**: `python manage.py runserver`
2. **Start Frontend**: `cd frontend && npm run dev`
3. **Open Browser**: http://localhost:5173
4. **Login**: username: `admin`, password: `admin`
5. **Upload PDF**: Click "Upload New Document" → Select PDF
6. **Wait for Processing**: Status page shows progress
7. **Get Quiz ID**: 
   - Go to Django admin: http://localhost:8000/admin/
   - Navigate: Documents → Modules → [Your Module] → Quizzes
   - Copy the Quiz ID
8. **Start Quiz**: Enter Quiz ID in status page → Click "Start Quiz"
9. **Answer Questions**: Select answers for all questions
10. **Submit**: Click "Submit Quiz"
11. **View Results**: See score, answers, and personalized feedback

## API Endpoints

- `POST /api/auth/token/` - Login (get JWT token)
- `POST /api/documents/upload/` - Upload PDF
- `GET /api/documents/{id}/status/` - Check processing status
- `POST /api/quizzes/{quiz_id}/start/` - Start quiz
- `POST /api/quizzes/attempts/{attempt_id}/submit/` - Submit answers
- `GET /api/quizzes/attempts/{attempt_id}/feedback/` - Get feedback

## Troubleshooting

### CORS Errors
- Make sure backend CORS settings include `http://localhost:5173`
- Restart Django server after changing CORS settings

### Quiz Submission 400 Error
- Ensure all questions are answered
- Check that `question_id` matches the questions from start endpoint
- Verify `user_answer` matches one of the options exactly

### Questions Not Loading
- Check browser console for errors
- Verify JWT token is valid
- Ensure quiz was started properly (questions stored in localStorage)

