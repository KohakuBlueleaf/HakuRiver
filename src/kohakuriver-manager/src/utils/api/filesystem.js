import { apiClient } from './client'

/**
 * Determine the API endpoint prefix based on the ID type.
 *
 * - For integer task IDs: /fs/{taskId} (proxied to runner)
 * - For string container names: /fs/container/{containerName} (direct to host)
 *
 * @param {number|string} id - Task ID or container name
 * @returns {string} API endpoint prefix
 */
function getEndpointPrefix(id) {
  // Check if it's a numeric task ID
  if (typeof id === 'number' || (typeof id === 'string' && /^\d+$/.test(id))) {
    return `/fs/${id}`
  }
  // Container name (string)
  return `/fs/container/${encodeURIComponent(id)}`
}

/**
 * Filesystem API for accessing files inside task/VPS containers or host containers.
 *
 * Automatically routes requests:
 * - Integer IDs -> /fs/{taskId} (task/VPS on runners)
 * - String names -> /fs/container/{name} (host containers)
 */
export const filesystemAPI = {
  /**
   * List directory contents
   * @param {number|string} taskId - Task ID or container name
   * @param {string} path - Directory path (default: '/')
   * @param {boolean} showHidden - Include hidden files (default: false)
   * @returns {Promise<{data: {path: string, entries: Array, parent: string|null}}>}
   */
  listDirectory(taskId, path = '/', showHidden = false) {
    const prefix = getEndpointPrefix(taskId)
    return apiClient.get(`${prefix}/list`, {
      params: { path, show_hidden: showHidden },
    })
  },

  /**
   * Read file contents
   * @param {number|string} taskId - Task ID or container name
   * @param {string} path - File path
   * @param {string} encoding - Output encoding ('utf-8' or 'base64')
   * @param {number} limit - Max bytes to read
   * @returns {Promise<{data: {path: string, content: string, encoding: string, size: number, truncated: boolean}}>}
   */
  readFile(taskId, path, encoding = 'utf-8', limit = 10485760) {
    const prefix = getEndpointPrefix(taskId)
    return apiClient.get(`${prefix}/read`, {
      params: { path, encoding, limit },
    })
  },

  /**
   * Write file contents
   * @param {number|string} taskId - Task ID or container name
   * @param {string} path - File path
   * @param {string} content - File content
   * @param {object} options - Additional options
   * @param {string} options.encoding - Content encoding ('utf-8' or 'base64')
   * @param {boolean} options.createParents - Create parent directories if missing
   * @returns {Promise<{data: {path: string, size: number, success: boolean}}>}
   */
  writeFile(taskId, path, content, options = {}) {
    const prefix = getEndpointPrefix(taskId)
    return apiClient.post(`${prefix}/write`, {
      path,
      content,
      encoding: options.encoding || 'utf-8',
      create_parents: options.createParents !== false,
    })
  },

  /**
   * Create a directory
   * @param {number|string} taskId - Task ID or container name
   * @param {string} path - Directory path
   * @param {boolean} parents - Create parent directories if missing
   * @returns {Promise<{data: {message: string, path: string}}>}
   */
  mkdir(taskId, path, parents = true) {
    const prefix = getEndpointPrefix(taskId)
    return apiClient.post(`${prefix}/mkdir`, {
      path,
      parents,
    })
  },

  /**
   * Rename or move a file/directory
   * @param {number|string} taskId - Task ID or container name
   * @param {string} source - Source path
   * @param {string} destination - Destination path
   * @param {boolean} overwrite - Overwrite if destination exists
   * @returns {Promise<{data: {message: string, source: string, destination: string}}>}
   */
  rename(taskId, source, destination, overwrite = false) {
    const prefix = getEndpointPrefix(taskId)
    return apiClient.post(`${prefix}/rename`, {
      source,
      destination,
      overwrite,
    })
  },

  /**
   * Delete a file or directory
   * @param {number|string} taskId - Task ID or container name
   * @param {string} path - Path to delete
   * @param {boolean} recursive - Delete directories recursively
   * @returns {Promise<{data: {message: string, path: string}}>}
   */
  deleteItem(taskId, path, recursive = false) {
    const prefix = getEndpointPrefix(taskId)
    return apiClient.delete(`${prefix}/delete`, {
      params: { path, recursive },
    })
  },

  /**
   * Get file/directory metadata
   * @param {number|string} taskId - Task ID or container name
   * @param {string} path - Path to stat
   * @returns {Promise<{data: {path: string, type: string, size: number, mtime: string, permissions: string, owner: string, is_readable: boolean, is_writable: boolean, is_binary: boolean}}>}
   */
  stat(taskId, path) {
    const prefix = getEndpointPrefix(taskId)
    return apiClient.get(`${prefix}/stat`, {
      params: { path },
    })
  },
}
