import { useState } from 'react';
import { documentsAPI } from '../api';
import './DocumentUpload.css';

function DocumentUpload({ onUploaded, onCancel }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      if (selectedFile.type !== 'application/pdf') {
        setError('Only PDF files are allowed');
        return;
      }
      if (selectedFile.size > 50 * 1024 * 1024) {
        setError('File size must be less than 50MB');
        return;
      }
      setFile(selectedFile);
      setError('');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a file');
      return;
    }

    setUploading(true);
    setError('');

    try {
      const result = await documentsAPI.upload(file);
      onUploaded(result.document_id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="upload-container">
      <h1>Upload Document</h1>
      <form onSubmit={handleSubmit} className="upload-form">
        {error && <div className="error-message">{error}</div>}
        <div className="file-input-wrapper">
          <label htmlFor="file-input" className="file-label">
            {file ? file.name : 'Choose PDF file (max 50MB)'}
          </label>
          <input
            id="file-input"
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            disabled={uploading}
            className="file-input"
          />
        </div>
        <div className="form-actions">
          <button type="button" onClick={onCancel} disabled={uploading}>
            Cancel
          </button>
          <button type="submit" disabled={!file || uploading} className="primary-button">
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </div>
      </form>
    </div>
  );
}

export default DocumentUpload;

