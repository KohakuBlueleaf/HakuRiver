import { apiClient } from './client'

export const dockerAPI = {
  /**
   * List host environment containers
   */
  listContainers() {
    return apiClient.get('/docker/host/containers')
  },

  /**
   * Create a new environment container
   * @param {Object} data
   * @param {string} data.container_name - Container/environment name
   * @param {string} data.image_name - Base Docker image
   */
  createContainer(data) {
    return apiClient.post('/docker/host/create', data)
  },

  /**
   * Delete an environment container
   * @param {string} envName
   */
  deleteContainer(envName) {
    return apiClient.post(`/docker/host/delete/${envName}`)
  },

  /**
   * Start an environment container
   * @param {string} envName
   */
  startContainer(envName) {
    return apiClient.post(`/docker/host/start/${envName}`)
  },

  /**
   * Stop an environment container
   * @param {string} envName
   */
  stopContainer(envName) {
    return apiClient.post(`/docker/host/stop/${envName}`)
  },

  /**
   * List available container tarballs
   */
  listTarballs() {
    return apiClient.get('/docker/list')
  },

  /**
   * Create tarball from container
   * @param {string} envName
   */
  createTarball(envName) {
    return apiClient.post(`/docker/create_tar/${envName}`)
  },

  /**
   * Delete container tarball(s)
   * @param {string} name - Tarball name
   */
  deleteTarball(name) {
    return apiClient.delete(`/docker/container/${name}`)
  },

  /**
   * List available Docker images on runners
   */
  listImages() {
    return apiClient.get('/docker/images')
  },
}

export default dockerAPI
