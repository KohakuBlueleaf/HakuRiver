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
    // MODIFIED: Add new fields to task submission data if they exist
    const payload = {
      command: taskData.command,
      arguments: taskData.arguments,
      env_vars: taskData.env_vars,
      required_cores: taskData.required_cores,
      required_memory_bytes: taskData.required_memory_bytes,
      use_private_network: taskData.use_private_network,
      use_private_pid: taskData.use_private_pid,
    };
    // Filter out null/undefined optional values if necessary, although backend should handle nulls
    Object.keys(payload).forEach((key) => payload[key] == null && delete payload[key]);
    return apiClient.post('/submit', payload);
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
  getHealth(hostname = null) {
    const params = hostname ? { hostname } : {};
    return apiClient.get('/health', { params });
  },
};
