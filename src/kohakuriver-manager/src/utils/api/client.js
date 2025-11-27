import axios from 'axios'

// Main API client
const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Log client with longer timeout and text response
const logClient = axios.create({
  baseURL: '/api',
  timeout: 60000,
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
