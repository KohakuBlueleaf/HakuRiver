// frontend/src/services/api.js
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api', // Adjust production URL
  timeout: 120000, // Default timeout
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
  // --- Existing API Calls ---
  getNodes() {
    // This endpoint in core/host.py already returns gpu_info if available
    return apiClient.get('/nodes');
  },
  submitTask(taskData) {
    const payload = {
      command: taskData.command,
      arguments: taskData.arguments,
      env_vars: taskData.env_vars,
      required_cores: taskData.required_cores,
      required_memory_bytes: taskData.required_memory_bytes,
      targets: taskData.targets, // This will be an array of hostnames/hostname:numa_id
      required_gpus: taskData.required_gpus, // This will be an array of lists of gpu_ids
      container_name: taskData.container_name,
      privileged: taskData.privileged,
      additional_mounts: taskData.additional_mounts,
      // Added task_type for submission endpoint
      task_type: taskData.task_type, // Add task_type here
    };
    // Clean up payload - remove null/undefined values
    Object.keys(payload).forEach((key) => payload[key] == null && delete payload[key]);
    return apiClient.post('/submit', payload).then((response) => response.data);
  },
  submitCommand(commandData) {
    const task_id = commandData.task_id;
    const command = commandData.command;
    return apiClient.post(`/command/${task_id}/${command}`);
  },
  getTaskStatus(taskId) {
    // This endpoint works for any task type
    return apiClient.get(`/status/${taskId}`);
  },
  killTask(taskId) {
    // This endpoint works for any task type
    return apiClient.post(`/kill/${taskId}`);
  },
  getTasks() {
    // This endpoint specifically gets 'command' tasks
    return apiClient.get('/tasks');
  },
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

  // --- Docker/Tarball API Calls ---
  getContainers() {
    return apiClient.get('/docker/host/containers');
  },
  createContainer(imageData) {
    return apiClient.post('/docker/host/create', imageData); // imageData: { image_name, container_name }
  },
  deleteContainer(containerName) {
    return apiClient.post(`/docker/host/delete/${containerName}`);
  },
  stopContainer(containerName) {
    return apiClient.post(`/docker/host/stop/${containerName}`);
  },
  startContainer(containerName) {
    return apiClient.post(`/docker/host/start/${containerName}`);
  },
  createTarball(containerName) {
    // This can be a long-running task, increase timeout if needed beyond default
    return apiClient.post(`/docker/create_tar/${containerName}`, {}, { timeout: 180000 }); // 3 minutes
  },
  getTarballs() {
    return apiClient.get('/docker/list');
  },

  // --- NEW VPS API Call ---
  getVpsStatus() {
    // This endpoint specifically gets 'vps' tasks that are active
    return apiClient.get('/vps/status');
  },
};
