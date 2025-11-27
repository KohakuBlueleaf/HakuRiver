/**
 * Composable for polling data at regular intervals
 */
export function usePolling(fetchFn, initialInterval = 5000) {
  const isPolling = ref(false)
  const timer = ref(null)
  let currentInterval = initialInterval

  function start() {
    if (isPolling.value) return

    isPolling.value = true
    // Fetch immediately
    fetchFn()
    // Then set up interval using window.setInterval to avoid shadowing
    timer.value = window.setInterval(fetchFn, currentInterval)
  }

  function stop() {
    if (timer.value) {
      window.clearInterval(timer.value)
      timer.value = null
    }
    isPolling.value = false
  }

  function updateInterval(newInterval) {
    currentInterval = newInterval
    if (isPolling.value) {
      stop()
      start()
    }
  }

  // Clean up on unmount
  onUnmounted(() => {
    stop()
  })

  return {
    isPolling,
    start,
    stop,
    updateInterval,
  }
}
