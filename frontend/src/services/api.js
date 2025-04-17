// src/services/api.js
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api', // Adjust production URL
  timeout: 10000, // Default timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

// Specific client for potentially long log requests, expecting text
const logClient = axios.create({
  baseURL: '/api',
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
    // Payload now expects 'targets' list instead of individual target info
    const payload = {
      command: taskData.command,
      arguments: taskData.arguments, // Assume taskData provides this already parsed
      env_vars: taskData.env_vars, // Assume taskData provides this already parsed
      required_cores: taskData.required_cores,
      required_memory_bytes: taskData.required_memory_bytes, // Already handled bytes conversion
      use_private_network: taskData.use_private_network,
      use_private_pid: taskData.use_private_pid,
      targets: taskData.targets, // Pass the array of target strings
    };
    // Filter out null/undefined optional values if necessary
    Object.keys(payload).forEach((key) => payload[key] == null && delete payload[key]);
    // Return the whole response data, as it might contain task_ids and failed_targets
    return apiClient.post('/submit', payload).then((response) => response.data);
    // Previous version returned only response.data.task_id
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
