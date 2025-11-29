<script setup>
/**
 * TerminalPane - Terminal panel for IDE.
 *
 * Wraps the existing useTerminal composable for use in the IDE layout.
 */

import { useTerminal } from '@/composables/useTerminal'
import { useIdeStore } from '@/stores/ide'

const props = defineProps({
  /**
   * Task ID to connect to
   */
  taskId: {
    type: [Number, String],
    default: null,
  },
  /**
   * Container name (for host containers)
   */
  containerName: {
    type: String,
    default: null,
  },
  /**
   * Connection type: 'task' or 'container'
   */
  type: {
    type: String,
    default: 'task',
  },
})

const emit = defineEmits(['connected', 'disconnected', 'error'])

const ideStore = useIdeStore()
const terminal = useTerminal()

// DOM ref for terminal container
const terminalContainer = ref(null)

// Resize observer for fitting terminal
let resizeObserver = null
let resizeTimeout = null
let lastWidth = 0
let lastHeight = 0

/**
 * Debounced fit function to prevent resize loops.
 */
function debouncedFit() {
  if (resizeTimeout) {
    clearTimeout(resizeTimeout)
  }
  resizeTimeout = setTimeout(() => {
    terminal.fit()
  }, 100)
}

/**
 * Initialize terminal.
 */
function initTerminal() {
  if (!terminalContainer.value) return

  terminal.createTerminal(terminalContainer.value, {
    fontSize: 13,
    fontFamily: 'Consolas, "Courier New", monospace',
    theme: {
      background: '#1e1e1e',
      foreground: '#d4d4d4',
      cursor: '#d4d4d4',
      cursorAccent: '#1e1e1e',
      selection: 'rgba(255, 255, 255, 0.3)',
    },
  })

  // Setup resize observer with debounce and size change check
  resizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0]
    if (!entry) return

    const { width, height } = entry.contentRect
    // Only trigger fit if size actually changed significantly (> 5px)
    if (Math.abs(width - lastWidth) > 5 || Math.abs(height - lastHeight) > 5) {
      lastWidth = width
      lastHeight = height
      debouncedFit()
    }
  })
  resizeObserver.observe(terminalContainer.value)
}

/**
 * Connect to terminal.
 */
function connect() {
  if (props.type === 'container' && props.containerName) {
    terminal.connectToContainer(props.containerName)
  } else if (props.taskId) {
    terminal.connect(props.taskId, props.type)
  }
}

/**
 * Disconnect terminal.
 */
function disconnect() {
  terminal.disconnect()
}

/**
 * Clear terminal.
 */
function clear() {
  terminal.clear()
}

/**
 * Fit terminal to container.
 */
function fit() {
  terminal.fit()
}

// Watch connection state
watch(
  () => terminal.connected.value,
  (connected) => {
    if (connected) {
      emit('connected')
    } else {
      emit('disconnected')
    }
  }
)

// Watch for errors
watch(
  () => terminal.error.value,
  (error) => {
    if (error) {
      emit('error', error)
    }
  }
)

// Initialize on mount
onMounted(() => {
  initTerminal()

  // Auto-connect if taskId is provided
  if (props.taskId || props.containerName) {
    nextTick(() => {
      connect()
    })
  }
})

// Cleanup on unmount
onBeforeUnmount(() => {
  if (resizeTimeout) {
    clearTimeout(resizeTimeout)
  }
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
  terminal.dispose()
})

// Reconnect when taskId changes
watch(
  () => props.taskId,
  (newId, oldId) => {
    if (newId !== oldId) {
      disconnect()
      if (newId) {
        nextTick(() => connect())
      }
    }
  }
)

// Expose methods
defineExpose({
  connect,
  disconnect,
  clear,
  fit,
  connected: terminal.connected,
  connecting: terminal.connecting,
  error: terminal.error,
})
</script>

<template>
  <div class="terminal-pane">
    <!-- Header -->
    <div class="terminal-header">
      <div class="terminal-title">
        <span class="i-carbon-terminal mr-2" />
        <span>Terminal</span>
      </div>
      <div class="terminal-status">
        <span
          class="status-dot"
          :class="{
            connected: terminal.connected.value,
            connecting: terminal.connecting.value,
            disconnected: !terminal.connected.value && !terminal.connecting.value,
          }" />
        <span class="status-text">
          {{ terminal.connecting.value ? 'Connecting...' : terminal.connected.value ? 'Connected' : 'Disconnected' }}
        </span>
      </div>
      <div class="terminal-actions">
        <el-tooltip
          content="Clear"
          placement="top">
          <el-button
            link
            size="small"
            @click="clear">
            <span class="i-carbon-clean" />
          </el-button>
        </el-tooltip>
        <el-tooltip
          :content="terminal.connected.value ? 'Disconnect' : 'Connect'"
          placement="top">
          <el-button
            link
            size="small"
            @click="terminal.connected.value ? disconnect() : connect()">
            <span :class="terminal.connected.value ? 'i-carbon-plug-filled' : 'i-carbon-plug'" />
          </el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- Terminal wrapper - uses position relative/absolute to contain terminal -->
    <div class="terminal-wrapper">
      <div
        ref="terminalContainer"
        class="terminal-container" />
    </div>
  </div>
</template>

<style scoped>
.terminal-pane {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  min-width: 0;
  background: #1e1e1e;
  overflow: hidden;
}

.terminal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: #252526;
  border-bottom: 1px solid #3c3c3c;
  flex: 0 0 auto;
  height: 32px;
}

.terminal-title {
  display: flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  color: #cccccc;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.terminal-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #888888;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.connected {
  background: #4caf50;
}

.status-dot.connecting {
  background: #ff9800;
  animation: pulse 1s infinite;
}

.status-dot.disconnected {
  background: #f44336;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.terminal-actions {
  display: flex;
  gap: 4px;
}

.terminal-actions .el-button {
  color: #cccccc;
}

.terminal-actions .el-button:hover {
  color: #ffffff;
}

/* Wrapper creates a positioning context - this is the key to containment */
.terminal-wrapper {
  flex: 1 1 auto;
  position: relative;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

/* Terminal container uses absolute positioning to fill the wrapper without affecting layout */
.terminal-container {
  position: absolute;
  inset: 8px; /* Use inset for padding instead of padding property */
  overflow: hidden;
}

/* Ensure xterm fills the container */
.terminal-container :deep(.xterm) {
  width: 100%;
  height: 100%;
}

.terminal-container :deep(.xterm-viewport) {
  overflow-y: auto !important;
}

/* Ensure xterm-screen doesn't exceed container bounds */
.terminal-container :deep(.xterm-screen) {
  width: 100% !important;
  height: 100% !important;
}
</style>
