<script setup>
/**
 * IdeLayout - Main layout component for the IDE.
 *
 * Features:
 * - Three-pane layout: File tree | Editor | Terminal
 * - Configurable terminal position (right or bottom)
 * - Resizable panes
 * - Collapsible panels
 */

import { useIdeStore } from '@/stores/ide'
import { useFileSystem } from '@/composables/useFileSystem'
import SplitPane from './common/SplitPane.vue'
import FileTree from './file-tree/FileTree.vue'
import EditorPane from './editor/EditorPane.vue'
import TerminalPane from './terminal/TerminalPane.vue'

const props = defineProps({
  /**
   * Task ID to connect to
   */
  taskId: {
    type: [Number, String],
    required: true,
  },
  /**
   * Connection type: 'task' or 'container'
   */
  type: {
    type: String,
    default: 'task',
  },
  /**
   * Container name (for host containers)
   */
  containerName: {
    type: String,
    default: null,
  },
  /**
   * File tree mode: 'vps' shows sections, 'container' shows only root
   */
  fileTreeMode: {
    type: String,
    default: 'vps',
  },
})

const emit = defineEmits(['close', 'terminal-connected', 'terminal-disconnected'])

const ideStore = useIdeStore()
const fs = useFileSystem()

// Refs
const fileTreeRef = ref(null)
const editorRef = ref(null)
const terminalRef = ref(null)

// Computed for terminal position
const isTerminalRight = computed(() => ideStore.terminalPosition === 'right')

/**
 * Handle file selection in tree.
 */
function handleFileSelect(entry) {
  // Just select, don't open
}

/**
 * Handle file open (double-click in tree).
 */
async function handleFileOpen(entry) {
  if (entry.type !== 'file') return

  try {
    await fs.openFileInEditor(entry.path, entry.size || 0)
  } catch (e) {
    ElMessage.error(`Failed to open file: ${e.message}`)
  }
}

/**
 * Handle tree refresh.
 */
function handleTreeRefresh(path) {
  // Could show a notification or update status
}

/**
 * Handle keyboard shortcuts.
 */
function handleKeydown(e) {
  const ctrl = e.ctrlKey || e.metaKey

  // Ctrl+B: Toggle file tree
  if (ctrl && e.key === 'b') {
    e.preventDefault()
    ideStore.toggleFileTree()
    return
  }

  // Ctrl+`: Toggle terminal
  if (ctrl && e.key === '`') {
    e.preventDefault()
    ideStore.toggleTerminal()
    return
  }

  // Ctrl+S: Save (handled by editor)
  // Ctrl+W: Close tab (handled by editor tabs)

  // Ctrl+Tab / Ctrl+Shift+Tab: Switch tabs
  if (ctrl && e.key === 'Tab') {
    e.preventDefault()
    if (e.shiftKey) {
      ideStore.prevTab()
    } else {
      ideStore.nextTab()
    }
    return
  }

  // Escape: Close IDE (with confirmation)
  if (e.key === 'Escape') {
    if (ideStore.hasUnsavedChanges) {
      ElMessageBox.confirm(
        'You have unsaved changes. Close anyway?',
        'Unsaved Changes',
        {
          confirmButtonText: 'Close',
          cancelButtonText: 'Cancel',
          type: 'warning',
        }
      )
        .then(() => {
          emit('close')
        })
        .catch(() => {})
    } else {
      emit('close')
    }
  }
}

/**
 * Handle terminal connected event.
 */
function handleTerminalConnected() {
  ideStore.connected = true
  emit('terminal-connected', terminalRef.value)
}

/**
 * Handle terminal disconnected event.
 */
function handleTerminalDisconnected() {
  ideStore.connected = false
  emit('terminal-disconnected')
}

/**
 * Disconnect terminal.
 */
function disconnect() {
  if (terminalRef.value) {
    terminalRef.value.disconnect()
  }
}

// Setup keyboard listener
onMounted(() => {
  window.addEventListener('keydown', handleKeydown)

  // Set connection info in store (but not connected state - that comes from terminal)
  ideStore.taskId = props.taskId
  ideStore.connectionType = props.type
  ideStore.containerName = props.containerName
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)

  // Clear store on close
  ideStore.$reset()
})

// Expose methods
defineExpose({
  refreshTree: () => fileTreeRef.value?.refreshAll(),
  focusEditor: () => editorRef.value?.focus(),
  focusTerminal: () => terminalRef.value?.fit(),
  disconnect,
})
</script>

<template>
  <div class="ide-layout">
    <!-- Layout with terminal on right -->
    <template v-if="isTerminalRight">
      <!-- File Tree | (Editor | Terminal) -->
      <SplitPane
        v-if="ideStore.showFileTree"
        direction="horizontal"
        :initial-size="ideStore.fileTreeWidth"
        :min-size="150"
        :max-size="400"
        storage-key="ide-file-tree"
        @update:size="ideStore.setFileTreeWidth"
      >
        <template #first>
          <FileTree
            ref="fileTreeRef"
            :show-hidden="true"
            :mode="fileTreeMode"
            @file-select="handleFileSelect"
            @file-open="handleFileOpen"
            @refresh="handleTreeRefresh"
          />
        </template>
        <template #second>
          <!-- Editor | Terminal -->
          <SplitPane
            v-if="ideStore.showTerminal"
            direction="horizontal"
            :initial-size="ideStore.terminalSize"
            :min-size="200"
            :max-size="600"
            storage-key="ide-terminal-right"
            :reverse="true"
            @update:size="ideStore.setTerminalSize"
          >
            <template #first>
              <EditorPane ref="editorRef" />
            </template>
            <template #second>
              <TerminalPane
                ref="terminalRef"
                :task-id="taskId"
                :type="type"
                :container-name="containerName"
                @connected="handleTerminalConnected"
                @disconnected="handleTerminalDisconnected"
              />
            </template>
          </SplitPane>
          <EditorPane v-else ref="editorRef" />
        </template>
      </SplitPane>

      <!-- No file tree - just Editor | Terminal -->
      <template v-else>
        <SplitPane
          v-if="ideStore.showTerminal"
          direction="horizontal"
          :initial-size="ideStore.terminalSize"
          :min-size="200"
          :max-size="600"
          storage-key="ide-terminal-right"
          :reverse="true"
          @update:size="ideStore.setTerminalSize"
        >
          <template #first>
            <EditorPane ref="editorRef" />
          </template>
          <template #second>
            <TerminalPane
              ref="terminalRef"
              :task-id="taskId"
              :type="type"
              :container-name="containerName"
              @connected="handleTerminalConnected"
              @disconnected="handleTerminalDisconnected"
            />
          </template>
        </SplitPane>
        <EditorPane v-else ref="editorRef" />
      </template>
    </template>

    <!-- Layout with terminal on bottom -->
    <template v-else>
      <!-- File Tree | (Editor / Terminal) -->
      <SplitPane
        v-if="ideStore.showFileTree"
        direction="horizontal"
        :initial-size="ideStore.fileTreeWidth"
        :min-size="150"
        :max-size="400"
        storage-key="ide-file-tree"
        @update:size="ideStore.setFileTreeWidth"
      >
        <template #first>
          <FileTree
            ref="fileTreeRef"
            :show-hidden="true"
            :mode="fileTreeMode"
            @file-select="handleFileSelect"
            @file-open="handleFileOpen"
            @refresh="handleTreeRefresh"
          />
        </template>
        <template #second>
          <!-- Editor / Terminal (vertical) -->
          <SplitPane
            v-if="ideStore.showTerminal"
            direction="vertical"
            :initial-size="ideStore.terminalSize"
            :min-size="100"
            :max-size="400"
            storage-key="ide-terminal-bottom"
            :reverse="true"
            @update:size="ideStore.setTerminalSize"
          >
            <template #first>
              <EditorPane ref="editorRef" />
            </template>
            <template #second>
              <TerminalPane
                ref="terminalRef"
                :task-id="taskId"
                :type="type"
                :container-name="containerName"
                @connected="handleTerminalConnected"
                @disconnected="handleTerminalDisconnected"
              />
            </template>
          </SplitPane>
          <EditorPane v-else ref="editorRef" />
        </template>
      </SplitPane>

      <!-- No file tree -->
      <template v-else>
        <SplitPane
          v-if="ideStore.showTerminal"
          direction="vertical"
          :initial-size="ideStore.terminalSize"
          :min-size="100"
          :max-size="400"
          storage-key="ide-terminal-bottom"
          :reverse="true"
          @update:size="ideStore.setTerminalSize"
        >
          <template #first>
            <EditorPane ref="editorRef" />
          </template>
          <template #second>
            <TerminalPane
              ref="terminalRef"
              :task-id="taskId"
              :type="type"
              :container-name="containerName"
              @connected="handleTerminalConnected"
              @disconnected="handleTerminalDisconnected"
            />
          </template>
        </SplitPane>
        <EditorPane v-else ref="editorRef" />
      </template>
    </template>
  </div>
</template>

<style scoped>
.ide-layout {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--el-bg-color);
}
</style>
