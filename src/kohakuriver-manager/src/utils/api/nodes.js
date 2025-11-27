import { apiClient } from './client'

export const nodesAPI = {
  /**
   * Get all registered nodes
   */
  getAll() {
    return apiClient.get('/nodes')
  },

  /**
   * Get cluster health metrics
   * @param {string|null} hostname - Optional filter by hostname
   */
  getHealth(hostname = null) {
    const params = hostname ? { hostname } : {}
    return apiClient.get('/health', { params })
  },
}

export default nodesAPI
