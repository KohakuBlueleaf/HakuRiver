// src/services/api.js - (No changes needed from previous example)
import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.DEV ? '/api' : 'http://your-production-hakuriver-host:8000', // Adjust production URL
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default {
  getNodes() {
    return apiClient.get('/nodes');
  },
  submitTask(taskData) {
    return apiClient.post('/submit', taskData);
  },
  getTaskStatus(taskId) {
    return apiClient.get(`/status/${taskId}`);
  },
  killTask(taskId) {
    return apiClient.post(`/kill/${taskId}`);
  },
  getTasks() {
    // This assumes the backend endpoint GET /tasks exists and returns an array.
    return apiClient.get('/tasks');
  },
};
