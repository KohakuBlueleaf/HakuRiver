import axios from 'axios'

// Default timeout: 10 minutes for long operations (create env, create tar, submit task/vps)
const DEFAULT_TIMEOUT = 10 * 60 * 1000

// Main API client
const apiClient = axios.create({
  baseURL: '/api',
  timeout: DEFAULT_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Log client with same timeout and text response
const logClient = axios.create({
  baseURL: '/api',
  timeout: DEFAULT_TIMEOUT,
  responseType: 'text',
})

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.response?.data?.message || error.message
    console.error('API Error:', message)
    return Promise.reject(error)
  }
)

logClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('Log fetch error:', error.message)
    return Promise.reject(error)
  }
)

export { apiClient, logClient }
export default apiClient
