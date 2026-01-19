import { useState, useEffect } from 'react';
import { authAPI } from './api';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import DocumentUpload from './components/DocumentUpload';
import DocumentStatus from './components/DocumentStatus';
import QuizTaking from './components/QuizTaking';
import QuizResults from './components/QuizResults';
import './App.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentView, setCurrentView] = useState('dashboard');
  const [documentId, setDocumentId] = useState(null);
  const [quizId, setQuizId] = useState(null);
  const [attemptId, setAttemptId] = useState(null);
  const [quizResults, setQuizResults] = useState(null);

  useEffect(() => {
    setIsAuthenticated(authAPI.isAuthenticated());
  }, []);

  const handleLogin = async (username, password) => {
    try {
      await authAPI.login(username, password);
      setIsAuthenticated(true);
      setCurrentView('dashboard');
    } catch (error) {
      throw error;
    }
  };

  const handleLogout = () => {
    authAPI.logout();
    setIsAuthenticated(false);
    setCurrentView('login');
    setDocumentId(null);
    setQuizId(null);
    setAttemptId(null);
    setQuizResults(null);
  };

  const handleDocumentUploaded = (docId) => {
    setDocumentId(docId);
    setCurrentView('document-status');
  };

  const handleQuizStart = (qId, attId, questions) => {
    setQuizId(qId);
    setAttemptId(attId);
    // Store questions in localStorage for QuizTaking component
    if (questions) {
      localStorage.setItem('current_quiz_questions', JSON.stringify(questions));
    }
    setCurrentView('quiz-taking');
  };

  const handleQuizSubmit = (results) => {
    setQuizResults(results);
    setCurrentView('quiz-results');
  };

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="app">
      <nav className="navbar">
        <div className="nav-brand">AI Learning Platform</div>
        <div className="nav-links">
          <button onClick={() => setCurrentView('dashboard')}>Dashboard</button>
          <button onClick={() => setCurrentView('upload')}>Upload Document</button>
          <button onClick={handleLogout}>Logout</button>
        </div>
      </nav>

      <main className="main-content">
        {currentView === 'dashboard' && (
          <Dashboard
            onUploadClick={() => setCurrentView('upload')}
            onQuizStart={handleQuizStart}
          />
        )}
        {currentView === 'upload' && (
          <DocumentUpload
            onUploaded={handleDocumentUploaded}
            onCancel={() => setCurrentView('dashboard')}
          />
        )}
        {currentView === 'document-status' && documentId && (
          <DocumentStatus
            documentId={documentId}
            onQuizStart={handleQuizStart}
            onBack={() => setCurrentView('dashboard')}
          />
        )}
        {currentView === 'quiz-taking' && attemptId && quizId && (
          <QuizTaking
            attemptId={attemptId}
            quizId={quizId}
            onSubmit={handleQuizSubmit}
            onCancel={() => setCurrentView('dashboard')}
          />
        )}
        {currentView === 'quiz-results' && quizResults && (
          <QuizResults
            results={quizResults}
            attemptId={attemptId}
            onBack={() => setCurrentView('dashboard')}
          />
        )}
      </main>
    </div>
  );
}

export default App;
