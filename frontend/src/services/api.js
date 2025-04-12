// src/services/api.js
import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.DEV ? '/api' : 'http://your-production-hakuriver-host:8000', // Adjust production URL
  timeout: 10000, // Default timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

// Specific client for potentially long log requests, expecting text
const logClient = axios.create({
  baseURL: import.meta.env.DEV ? '/api' : 'http://your-production-hakuriver-host:8000',
  timeout: 30000, // Longer timeout for logs
  headers: {
    Accept: 'text/plain', // Indicate we prefer plain text
  },
  responseType: 'text', // Expect plain text response
});

export default {
  getNodes() {
    return apiClient.get('/nodes');
  },
  submitTask(taskData) {
    return apiClient.post('/submit', taskData);
  },
  getTaskStatus(taskId) {
    // Note: This fetches full details now via the /status endpoint
    // The dedicated /tasks endpoint is used for the main list view
    return apiClient.get(`/status/${taskId}`);
  },
  killTask(taskId) {
    return apiClient.post(`/kill/${taskId}`);
  },
  getTasks() {
    // Fetches the list of tasks for the table view
    return apiClient.get('/tasks');
  },
  // --- NEW LOG FETCHING FUNCTIONS ---
  getTaskStdout(taskId) {
    return logClient.get(`/task/${taskId}/stdout`);
  },
  getTaskStderr(taskId) {
    return logClient.get(`/task/${taskId}/stderr`);
  },
};
