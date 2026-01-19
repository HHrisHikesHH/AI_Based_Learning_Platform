import { useState, useEffect } from 'react';
import { documentsAPI } from '../api';
import './Dashboard.css';

function Dashboard({ onUploadClick, onQuizStart }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // For now, we'll show upload option
    // In a full implementation, you'd fetch user's documents here
    setLoading(false);
  }, []);

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>
      <div className="dashboard-actions">
        <button className="primary-button" onClick={onUploadClick}>
          📤 Upload New Document
        </button>
      </div>
      <div className="dashboard-info">
        <p>Upload a PDF document to start learning. The system will:</p>
        <ul>
          <li>Extract and process the document</li>
          <li>Create learning modules</li>
          <li>Generate quizzes automatically</li>
          <li>Provide personalized feedback</li>
        </ul>
      </div>
    </div>
  );
}

export default Dashboard;

