import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

// Create axios instance with interceptors
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Handle token refresh on 401
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  login: async (username, password) => {
    const response = await api.post('/auth/token/', { username, password });
    localStorage.setItem('access_token', response.data.access);
    localStorage.setItem('refresh_token', response.data.refresh);
    return response.data;
  },
  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  },
  isAuthenticated: () => !!localStorage.getItem('access_token'),
};

// Documents API
export const documentsAPI = {
  upload: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/documents/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  getStatus: async (documentId) => {
    const response = await api.get(`/documents/${documentId}/status/`);
    return response.data;
  },
  getAnalytics: async (documentId) => {
    const response = await api.get(`/documents/${documentId}/analytics/`);
    return response.data;
  },
};

// Quizzes API
export const quizzesAPI = {
  start: async (quizId) => {
    const response = await api.post(`/quizzes/${quizId}/start/`, {});
    return response.data;
  },
  submit: async (attemptId, answers) => {
    const response = await api.post(`/quizzes/attempts/${attemptId}/submit/`, {
      answers,
    });
    return response.data;
  },
  getFeedback: async (attemptId) => {
    const response = await api.get(`/quizzes/attempts/${attemptId}/feedback/`);
    return response.data;
  },
};

export default api;

