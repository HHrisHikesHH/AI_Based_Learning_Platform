import { useState, useEffect } from 'react';
import { quizzesAPI } from '../api';
import './QuizResults.css';

function QuizResults({ results, attemptId, onBack }) {
  const [feedback, setFeedback] = useState(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);

  useEffect(() => {
    // Check for feedback immediately, then poll if still generating
    const checkFeedback = async () => {
      try {
        const data = await quizzesAPI.getFeedback(attemptId);
        if (data.status === 'COMPLETED' && data.feedback) {
          setFeedback(data.feedback);
          setLoadingFeedback(false);
        } else if (data.status === 'GENERATING') {
          // Poll for feedback
          setLoadingFeedback(true);
          const pollFeedback = async () => {
            try {
              const pollData = await quizzesAPI.getFeedback(attemptId);
              if (pollData.status === 'COMPLETED' && pollData.feedback) {
                setFeedback(pollData.feedback);
                setLoadingFeedback(false);
              } else if (pollData.status === 'GENERATING') {
                setTimeout(pollFeedback, 2000); // Poll every 2 seconds
              } else {
                setLoadingFeedback(false);
              }
            } catch (err) {
              setLoadingFeedback(false);
            }
          };
          setTimeout(pollFeedback, 2000);
        } else {
          setLoadingFeedback(false);
        }
      } catch (err) {
        setLoadingFeedback(false);
      }
    };

    if (attemptId) {
      checkFeedback();
    }
  }, [attemptId]);

  const scoreColor = results.score >= 70 ? 'green' : results.score >= 50 ? 'orange' : 'red';

  return (
    <div className="results-container">
      <h1>Quiz Results</h1>

      <div className="score-card">
        <div className={`score-circle score-${scoreColor}`}>
          <div className="score-value">{results.score.toFixed(1)}%</div>
          <div className="score-label">Score</div>
        </div>
        <div className="score-details">
          <p>
            <strong>Correct:</strong> {results.correct_answers} / {results.total_questions}
          </p>
          <p>
            <strong>Time Spent:</strong> {Math.floor(results.time_spent_seconds / 60)}m{' '}
            {results.time_spent_seconds % 60}s
          </p>
        </div>
      </div>

      <div className="results-list">
        <h2>Question Results</h2>
        {results.results.map((result, index) => (
          <div
            key={result.question_id}
            className={`result-item ${result.is_correct ? 'correct' : 'incorrect'}`}
          >
            <div className="result-header">
              <span className="result-number">Q{index + 1}</span>
              <span className={`result-badge ${result.is_correct ? 'correct' : 'incorrect'}`}>
                {result.is_correct ? '✓ Correct' : '✗ Incorrect'}
              </span>
            </div>
            <div className="result-answers">
              <p>
                <strong>Your Answer:</strong> {result.your_answer}
              </p>
              {!result.is_correct && (
                <p>
                  <strong>Correct Answer:</strong> {result.correct_answer}
                </p>
              )}
            </div>
            {result.explanation && (
              <div className="result-explanation">
                <strong>Explanation:</strong> {result.explanation}
              </div>
            )}
          </div>
        ))}
      </div>

      {loadingFeedback && (
        <div className="feedback-loading">Generating personalized feedback...</div>
      )}

      {feedback && (
        <div className="feedback-section">
          <h2>Personalized Feedback</h2>
          <div className="feedback-content">
            <p className="feedback-overall">{feedback.overall_feedback}</p>
            {feedback.strengths && feedback.strengths.length > 0 && (
              <div className="feedback-strengths">
                <h3>Strengths</h3>
                <ul>
                  {feedback.strengths.map((strength, i) => (
                    <li key={i}>{strength}</li>
                  ))}
                </ul>
              </div>
            )}
            {feedback.weaknesses && feedback.weaknesses.length > 0 && (
              <div className="feedback-weaknesses">
                <h3>Areas for Improvement</h3>
                <ul>
                  {feedback.weaknesses.map((weakness, i) => (
                    <li key={i}>{weakness}</li>
                  ))}
                </ul>
              </div>
            )}
            {feedback.recommended_topics && feedback.recommended_topics.length > 0 && (
              <div className="feedback-recommendations">
                <h3>Recommended Topics</h3>
                <ul>
                  {feedback.recommended_topics.map((topic, i) => (
                    <li key={i}>{topic}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      <button onClick={onBack} className="primary-button">
        Back to Dashboard
      </button>
    </div>
  );
}

export default QuizResults;

