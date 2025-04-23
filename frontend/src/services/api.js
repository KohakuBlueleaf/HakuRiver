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
  // --- Existing API Calls ---
  getNodes() {
    return apiClient.get('/nodes');
  },
  submitTask(taskData) {
    const payload = {
      command: taskData.command,
      arguments: taskData.arguments,
      env_vars: taskData.env_vars,
      required_cores: taskData.required_cores,
      required_memory_bytes: taskData.required_memory_bytes,
      targets: taskData.targets,
      container_name: taskData.container_name,
      privileged: taskData.privileged,
      additional_mounts: taskData.additional_mounts,
    };
    Object.keys(payload).forEach((key) => payload[key] == null && delete payload[key]);
    return apiClient.post('/submit', payload).then((response) => response.data);
  },
  submitCommand(commandData) {
    const task_id = commandData.task_id;
    const command = commandData.command;
    return apiClient.post(`/command/${task_id}/${command}`);
  },
  getTaskStatus(taskId) {
    return apiClient.get(`/status/${taskId}`);
  },
  killTask(taskId) {
    return apiClient.post(`/kill/${taskId}`);
  },
  getTasks() {
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

  // --- New Docker/Tarball API Calls ---
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
  // Note: Backend endpoint for deleting specific tarball is needed
  // deleteTarball(containerName, timestamp) {
  //   return apiClient.delete(`/docker/tar/${containerName}/${timestamp}`);
  // }
};
