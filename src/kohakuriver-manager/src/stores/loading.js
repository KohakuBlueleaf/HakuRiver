import { defineStore } from 'pinia'

export const useLoadingStore = defineStore('loading', () => {
  // Active operations map: id -> { message, startTime }
  const operations = ref(new Map())

  // Computed: is any operation in progress
  const isLoading = computed(() => operations.value.size > 0)

  // Computed: current operation message (most recent)
  const currentMessage = computed(() => {
    if (operations.value.size === 0) return ''
    const entries = Array.from(operations.value.values())
    return entries[entries.length - 1]?.message || 'Processing...'
  })

  // Computed: all active messages
  const allMessages = computed(() => {
    return Array.from(operations.value.values()).map((op) => op.message)
  })

  // Start a loading operation
  function startLoading(id, message = 'Processing...') {
    operations.value.set(id, { message, startTime: Date.now() })
    // Force reactivity
    operations.value = new Map(operations.value)
  }

  // Stop a loading operation
  function stopLoading(id) {
    operations.value.delete(id)
    // Force reactivity
    operations.value = new Map(operations.value)
  }

  // Helper to wrap async operations
  async function withLoading(id, message, asyncFn) {
    startLoading(id, message)
    try {
      return await asyncFn()
    } finally {
      stopLoading(id)
    }
  }

  return {
    operations,
    isLoading,
    currentMessage,
    allMessages,
    startLoading,
    stopLoading,
    withLoading,
  }
})
