import { useState, useEffect } from 'react';
import { quizzesAPI } from '../api';
import './QuizTaking.css';

function QuizTaking({ attemptId, quizId, onSubmit, onCancel }) {
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [timeSpent, setTimeSpent] = useState({});
  const [questionStartTimes, setQuestionStartTimes] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // Fetch questions when component mounts
    const fetchQuestions = async () => {
      try {
        // Try to get from localStorage first (if we just started)
        const savedQuestions = localStorage.getItem('current_quiz_questions');
        if (savedQuestions) {
          const parsed = JSON.parse(savedQuestions);
          setQuestions(parsed);
          // Initialize start times for each question
          const startTimes = {};
          parsed.forEach((q) => {
            startTimes[q.id] = Date.now();
          });
          setQuestionStartTimes(startTimes);
        } else if (quizId) {
          // If not in localStorage, fetch from API
          const result = await quizzesAPI.start(quizId);
          setQuestions(result.questions || []);
          const startTimes = {};
          (result.questions || []).forEach((q) => {
            startTimes[q.id] = Date.now();
          });
          setQuestionStartTimes(startTimes);
        } else {
          setError('Quiz ID not provided. Please start the quiz again.');
        }
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load quiz questions');
      } finally {
        setLoading(false);
      }
    };
    fetchQuestions();
  }, [attemptId, quizId]);

  const handleAnswerChange = (questionId, answer) => {
    setAnswers({ ...answers, [questionId]: answer });
    // Calculate time spent on this question
    if (questionStartTimes[questionId]) {
      const elapsed = Math.floor((Date.now() - questionStartTimes[questionId]) / 1000);
      setTimeSpent({ ...timeSpent, [questionId]: elapsed });
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
      const answersArray = questions.map((q) => {
        // Calculate final time if not already set
        let finalTime = timeSpent[q.id];
        if (!finalTime && questionStartTimes[q.id]) {
          finalTime = Math.floor((Date.now() - questionStartTimes[q.id]) / 1000);
        }
        const userAnswer = answers[q.id];
        // Ensure user_answer is a string and matches one of the options
        if (!userAnswer) {
          throw new Error(`Please answer question ${q.question_order}`);
        }
        return {
          question_id: q.id,
          user_answer: String(userAnswer),
          time_spent_seconds: finalTime || 0,
        };
      });

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
              {Array.isArray(question.options) ? (
                question.options.map((option, optIndex) => (
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
                ))
              ) : (
                <p className="error-message">Invalid options format</p>
              )}
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

