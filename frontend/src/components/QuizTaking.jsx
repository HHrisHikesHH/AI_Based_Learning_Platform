import { useState, useEffect } from 'react';
import { quizzesAPI } from '../api';
import './QuizTaking.css';

function QuizTaking({ attemptId, onSubmit, onCancel }) {
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [timeSpent, setTimeSpent] = useState({});
  const [startTime] = useState(Date.now());
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // Get questions from localStorage (set when starting quiz)
    const savedQuestions = localStorage.getItem('current_quiz_questions');
    if (savedQuestions) {
      try {
        setQuestions(JSON.parse(savedQuestions));
      } catch (err) {
        setError('Failed to load quiz questions');
      }
    } else {
      setError('Quiz questions not found. Please start the quiz again.');
    }
    setLoading(false);
  }, [attemptId]);

  const handleAnswerChange = (questionId, answer) => {
    setAnswers({ ...answers, [questionId]: answer });
    if (!timeSpent[questionId]) {
      setTimeSpent({ ...timeSpent, [questionId]: Math.floor((Date.now() - startTime) / 1000) });
    }
  };

  const handleSubmit = async () => {
    if (Object.keys(answers).length !== questions.length) {
      setError('Please answer all questions');
      return;
    }

    setSubmitting(true);
    setError('');

    try {
      const answersArray = questions.map((q) => ({
        question_id: q.id,
        user_answer: answers[q.id] || '',
        time_spent_seconds: timeSpent[q.id] || 0,
      }));

      const result = await quizzesAPI.submit(attemptId, answersArray);
      onSubmit(result);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit quiz');
      setSubmitting(false);
    }
  };

  // For demo: if we don't have questions, show a message
  if (loading) {
    return <div className="quiz-container">Loading quiz...</div>;
  }

  if (questions.length === 0) {
    return (
      <div className="quiz-container">
        <div className="error-message">
          Quiz questions not loaded. Please start the quiz from the document status page.
        </div>
        <button onClick={onCancel}>Back</button>
      </div>
    );
  }

  return (
    <div className="quiz-container">
      <h1>Quiz</h1>
      <div className="quiz-progress">
        Answered: {Object.keys(answers).length} / {questions.length}
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="questions-list">
        {questions.map((question, index) => (
          <div key={question.id} className="question-card">
            <h3>
              Question {index + 1}: {question.question_text}
            </h3>
            <div className="options-list">
              {question.options.map((option, optIndex) => (
                <label key={optIndex} className="option-label">
                  <input
                    type="radio"
                    name={`question-${question.id}`}
                    value={option}
                    checked={answers[question.id] === option}
                    onChange={() => handleAnswerChange(question.id, option)}
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="quiz-actions">
        <button onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={submitting || Object.keys(answers).length !== questions.length}
          className="primary-button"
        >
          {submitting ? 'Submitting...' : 'Submit Quiz'}
        </button>
      </div>
    </div>
  );
}

export default QuizTaking;

