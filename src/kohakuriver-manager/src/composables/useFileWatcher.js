/**
 * File Watcher Composable
 *
 * Provides real-time filesystem change notifications via WebSocket.
 * Automatically reconnects on disconnection and emits events for file changes.
 */

import { useIdeStore } from '@/stores/ide'

/**
 * File change event types.
 */
export const FileChangeEvent = {
  CREATE: 'CREATE',
  MODIFY: 'MODIFY',
  DELETE: 'DELETE',
  MOVE: 'MOVE',
}

/**
 * Composable for watching filesystem changes in a container.
 *
 * @returns {Object} File watcher state and methods
 */
export function useFileWatcher() {
  const ideStore = useIdeStore()

  // State
  const connected = ref(false)
  const connecting = ref(false)
  const error = ref(null)
  const watchMethod = ref(null) // 'inotify' or 'polling'
  const watchedPaths = ref([])

  // Internal state
  let ws = null
  let reconnectTimeout = null
  let pingInterval = null
  const RECONNECT_DELAY = 3000
  const PING_INTERVAL = 30000

  // Event callbacks
  const changeCallbacks = new Set()
  const errorCallbacks = new Set()

  /**
   * Get WebSocket URL for file watching.
   */
  function getWsUrl(taskId, paths = ['/shared', '/local_temp']) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const pathsParam = encodeURIComponent(paths.join(','))
    return `${protocol}//${host}/api/fs/${taskId}/watch?paths=${pathsParam}`
  }

  /**
   * Connect to file watcher WebSocket.
   *
   * @param {number|string} taskId - Task ID to watch
   * @param {string[]} paths - Paths to watch (default: ['/shared', '/local_temp'])
   */
  function connect(taskId, paths = ['/shared', '/local_temp']) {
    if (ws) {
      disconnect()
    }

    if (!taskId) {
      error.value = 'No task ID provided'
      return
    }

    connecting.value = true
    error.value = null

    const url = getWsUrl(taskId, paths)
    console.log('[FileWatcher] Connecting to:', url)

    try {
      ws = new WebSocket(url)

      ws.onopen = () => {
        console.log('[FileWatcher] Connected')
        connected.value = true
        connecting.value = false
        error.value = null

        // Start ping interval
        startPingInterval()
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleMessage(data)
        } catch (e) {
          console.error('[FileWatcher] Failed to parse message:', e)
        }
      }

      ws.onerror = (event) => {
        console.error('[FileWatcher] WebSocket error:', event)
        error.value = 'WebSocket connection error'
        notifyError(error.value)
      }

      ws.onclose = (event) => {
        console.log('[FileWatcher] Disconnected, code:', event.code)
        connected.value = false
        connecting.value = false
        stopPingInterval()

        // Auto-reconnect if not intentional close
        if (event.code !== 1000 && ideStore.connected) {
          scheduleReconnect(taskId, paths)
        }
      }
    } catch (e) {
      console.error('[FileWatcher] Failed to create WebSocket:', e)
      error.value = e.message
      connecting.value = false
      notifyError(error.value)
    }
  }

  /**
   * Disconnect from file watcher.
   */
  function disconnect() {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout)
      reconnectTimeout = null
    }
    stopPingInterval()

    if (ws) {
      ws.close(1000, 'User disconnect')
      ws = null
    }

    connected.value = false
    connecting.value = false
    watchMethod.value = null
    watchedPaths.value = []
  }

  /**
   * Schedule reconnection attempt.
   */
  function scheduleReconnect(taskId, paths) {
    if (reconnectTimeout) return

    console.log(`[FileWatcher] Reconnecting in ${RECONNECT_DELAY}ms...`)
    reconnectTimeout = setTimeout(() => {
      reconnectTimeout = null
      if (ideStore.connected) {
        connect(taskId, paths)
      }
    }, RECONNECT_DELAY)
  }

  /**
   * Start ping interval to keep connection alive.
   */
  function startPingInterval() {
    stopPingInterval()
    pingInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }))
      }
    }, PING_INTERVAL)
  }

  /**
   * Stop ping interval.
   */
  function stopPingInterval() {
    if (pingInterval) {
      clearInterval(pingInterval)
      pingInterval = null
    }
  }

  /**
   * Handle incoming WebSocket message.
   */
  function handleMessage(data) {
    switch (data.type) {
      case 'watching':
        // Watcher started
        watchMethod.value = data.method
        watchedPaths.value = data.paths || []
        console.log('[FileWatcher] Watching paths:', data.paths, 'method:', data.method)
        break

      case 'change':
        // File change event
        notifyChange({
          event: data.event,
          path: data.path,
          isDir: data.is_dir,
        })
        break

      case 'error':
        // Error message
        error.value = data.message
        console.error('[FileWatcher] Server error:', data.message)
        notifyError(data.message)
        break

      case 'pong':
        // Ping response, ignore
        break

      default:
        console.warn('[FileWatcher] Unknown message type:', data.type)
    }
  }

  /**
   * Notify all change listeners.
   */
  function notifyChange(change) {
    for (const callback of changeCallbacks) {
      try {
        callback(change)
      } catch (e) {
        console.error('[FileWatcher] Change callback error:', e)
      }
    }
  }

  /**
   * Notify all error listeners.
   */
  function notifyError(errorMsg) {
    for (const callback of errorCallbacks) {
      try {
        callback(errorMsg)
      } catch (e) {
        console.error('[FileWatcher] Error callback error:', e)
      }
    }
  }

  /**
   * Register a callback for file change events.
   *
   * @param {Function} callback - Called with {event, path, isDir}
   * @returns {Function} Unsubscribe function
   */
  function onChange(callback) {
    changeCallbacks.add(callback)
    return () => changeCallbacks.delete(callback)
  }

  /**
   * Register a callback for error events.
   *
   * @param {Function} callback - Called with error message
   * @returns {Function} Unsubscribe function
   */
  function onError(callback) {
    errorCallbacks.add(callback)
    return () => errorCallbacks.delete(callback)
  }

  /**
   * Get the parent directory of a path.
   */
  function getParentDir(path) {
    const lastSlash = path.lastIndexOf('/')
    if (lastSlash <= 0) return '/'
    return path.substring(0, lastSlash)
  }

  /**
   * Check if a path is within one of the watched paths.
   */
  function isPathWatched(path) {
    return watchedPaths.value.some((wp) => path === wp || path.startsWith(wp + '/'))
  }

  // Cleanup on unmount
  onBeforeUnmount(() => {
    disconnect()
    changeCallbacks.clear()
    errorCallbacks.clear()
  })

  return {
    // State
    connected,
    connecting,
    error,
    watchMethod,
    watchedPaths,

    // Methods
    connect,
    disconnect,
    onChange,
    onError,

    // Utilities
    getParentDir,
    isPathWatched,
  }
}
