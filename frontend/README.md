# E-Learning Platform Frontend

React frontend for the AI-Based Learning Platform.

## Features

- ✅ JWT Authentication
- ✅ Document Upload (PDF)
- ✅ Real-time Processing Status
- ✅ Quiz Taking Interface
- ✅ Answer Submission
- ✅ Results & Feedback Display

## Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will run on `http://localhost:5173` (Vite default).

## Configuration

Update `src/api.js` if your backend runs on a different port:

```javascript
const API_BASE_URL = 'http://localhost:8000/api';
```

## Usage

1. **Login**: Use your Django credentials (default: admin/admin)
2. **Upload Document**: Click "Upload New Document" and select a PDF
3. **Wait for Processing**: The status page will show progress
4. **Start Quiz**: Enter the quiz ID (from Django admin) and click "Start Quiz"
5. **Take Quiz**: Answer all questions and submit
6. **View Results**: See your score, answers, and personalized feedback

## Backend Integration

Make sure your Django backend is running with CORS enabled:

```python
# In settings.py
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',  # Vite dev server
    'http://localhost:3000',   # Alternative
]
```

## Build for Production

```bash
npm run build
```

The built files will be in `dist/` directory.
