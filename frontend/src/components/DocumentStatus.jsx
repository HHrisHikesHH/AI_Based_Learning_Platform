import { useState, useEffect } from 'react';
import { documentsAPI, quizzesAPI } from '../api';
import './DocumentStatus.css';

function DocumentStatus({ documentId, onQuizStart, onBack }) {
  const [status, setStatus] = useState(null);
  const [quizzes, setQuizzes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const pollStatus = async () => {
      try {
        const data = await documentsAPI.getStatus(documentId);
        setStatus(data);
        setLoading(false);

        // If completed, fetch available quizzes
        if (data.status === 'COMPLETED' && data.modules_ready?.length > 0) {
          try {
            const quizzesData = await documentsAPI.getQuizzes(documentId);
            setQuizzes(quizzesData.quizzes || []);
          } catch (err) {
            console.error('Failed to fetch quizzes:', err);
          }
        }
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to fetch status');
        setLoading(false);
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [documentId]);

  const handleStartQuiz = async () => {
    const quizIdInput = document.getElementById('quiz-id-input');
    const quizId = quizIdInput ? parseInt(quizIdInput.value) : null;
    
    if (!quizId || isNaN(quizId)) {
      setError('Please enter a valid quiz ID');
      return;
    }

    try {
      const result = await quizzesAPI.start(quizId);
      localStorage.setItem('current_quiz_id', quizId.toString());
      localStorage.setItem('current_quiz_questions', JSON.stringify(result.questions || []));
      onQuizStart(quizId, result.attempt_id, result.questions);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start quiz');
    }
  };

  if (loading && !status) {
    return <div className="status-container">Loading...</div>;
  }

  if (error && !status) {
    return (
      <div className="status-container">
        <div className="error-message">{error}</div>
        <button onClick={onBack}>Back to Dashboard</button>
      </div>
    );
  }

  const progress = status?.progress || {};
  const isCompleted = status?.status === 'COMPLETED';
  const modulesReady = status?.modules_ready || [];

  return (
    <div className="status-container">
      <h1>Document Processing Status</h1>
      <div className="status-card">
        <div className="status-badge status-badge-{status?.status?.toLowerCase()}">
          {status?.status || 'UNKNOWN'}
        </div>
        {progress.current_stage && (
          <div className="progress-info">
            <p>Stage: {progress.current_stage}</p>
            {progress.total_modules && (
              <p>
                Modules: {progress.modules_completed || 0} / {progress.total_modules}
              </p>
            )}
          </div>
        )}
      </div>

      {status?.error && (
        <div className="error-message">Error: {status.error}</div>
      )}

      {isCompleted && modulesReady.length > 0 && (
        <div className="quiz-section">
          <h2>Available Quizzes</h2>
          {quizzes.length > 0 ? (
            <div className="quizzes-list">
              {quizzes.map((quiz) => (
                <div key={quiz.id} className="quiz-card">
                  <div className="quiz-info">
                    <h3>{quiz.module__title || `Module ${quiz.module__id}`}</h3>
                    <p>Questions: {quiz.total_questions} | Difficulty: {quiz.difficulty}</p>
                  </div>
                  <button
                    onClick={() => {
                      const quizIdInput = document.getElementById('quiz-id-input');
                      if (quizIdInput) quizIdInput.value = quiz.id;
                      handleStartQuiz();
                    }}
                    className="primary-button"
                  >
                    Start Quiz
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <>
              <p className="info-text">
                Quizzes are being generated. Please wait a moment and refresh.
              </p>
              <div className="quiz-input">
                <input
                  type="number"
                  placeholder="Or enter Quiz ID manually"
                  id="quiz-id-input"
                />
                <button onClick={handleStartQuiz} className="primary-button">
                  Start Quiz
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {!isCompleted && (
        <div className="processing-message">
          <p>Processing your document...</p>
          <p className="info-text">This may take a few minutes. Please wait.</p>
        </div>
      )}

      <button onClick={onBack} className="back-button">
        Back to Dashboard
      </button>
    </div>
  );
}

export default DocumentStatus;

