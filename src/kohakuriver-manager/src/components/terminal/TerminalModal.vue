<script setup>
import { useTerminal } from '@/composables/useTerminal'

const props = defineProps({
  visible: Boolean,
  taskId: [String, Number],
  containerName: String,
  title: {
    type: String,
    default: 'Terminal',
  },
  type: {
    type: String,
    default: 'task', // 'task' or 'container'
  },
})

const emit = defineEmits(['update:visible', 'close'])

const terminalRef = ref(null)
const isDisposed = ref(false)
const { terminal, connected, connecting, error, createTerminal, connect, connectToContainer, fit, dispose } =
  useTerminal()

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
})

function handleOpened() {
  isDisposed.value = false
  if (terminalRef.value) {
    createTerminal(terminalRef.value)

    if (props.type === 'container' && props.containerName) {
      connectToContainer(props.containerName)
    } else if (props.taskId) {
      connect(props.taskId, props.type)
    }
  }
}

function handleClosed() {
  // Called when dialog is fully closed (after animation)
  if (!isDisposed.value) {
    isDisposed.value = true
    dispose()
  }
  emit('close')
}

function closeDialog() {
  emit('update:visible', false)
}

// Handle resize
const resizeObserver = ref(null)

onMounted(() => {
  resizeObserver.value = new ResizeObserver(() => {
    if (terminal.value) {
      fit()
    }
  })
})

// Watch for external close (when visible prop changes to false)
watch(
  () => props.visible,
  (visible, oldVisible) => {
    if (oldVisible && !visible && !isDisposed.value) {
      isDisposed.value = true
      dispose()
    }
  }
)

onUnmounted(() => {
  resizeObserver.value?.disconnect()
  if (!isDisposed.value) {
    dispose()
  }
})
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="title"
    width="80%"
    top="5vh"
    :close-on-click-modal="false"
    :close-on-press-escape="true"
    destroy-on-close
    @opened="handleOpened"
    @closed="handleClosed"
    class="terminal-dialog"
  >
    <div class="terminal-container">
      <!-- Status bar -->
      <div class="flex items-center justify-between px-3 py-2 bg-gray-800 border-b border-gray-700">
        <div class="flex items-center gap-2">
          <span
            class="w-2 h-2 rounded-full"
            :class="connected ? 'bg-green-500' : connecting ? 'bg-yellow-500' : 'bg-red-500'"
          ></span>
          <span class="text-xs text-gray-400">
            {{ connected ? 'Connected' : connecting ? 'Connecting...' : 'Disconnected' }}
          </span>
        </div>
        <div v-if="error" class="text-xs text-red-400">{{ error }}</div>
      </div>

      <!-- Terminal -->
      <div ref="terminalRef" class="terminal-content"></div>
    </div>
  </el-dialog>
</template>

<style scoped>
.terminal-container {
  background: #1e1e1e;
  border-radius: 8px;
  overflow: hidden;
}

.terminal-content {
  height: 60vh;
  padding: 8px;
}

:deep(.terminal-dialog .el-dialog__body) {
  padding: 0;
}
</style>
