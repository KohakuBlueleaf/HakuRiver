<script setup>
/**
 * IdeModal - Main IDE modal component.
 *
 * Replaces the TerminalModal with a full VSCode-like IDE experience.
 *
 * Features:
 * - Full-screen modal
 * - File browser
 * - Monaco editor with tabs
 * - Integrated terminal
 * - Configurable layout
 */

import { useIdeStore } from '@/stores/ide'
import IdeLayout from './IdeLayout.vue'
import IdeStatusBar from './common/IdeStatusBar.vue'

const props = defineProps({
  /**
   * Whether the modal is visible
   */
  visible: {
    type: Boolean,
    default: false,
  },
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
   * Modal title
   */
  title: {
    type: String,
    default: 'IDE',
  },
  /**
   * Connection type: 'task' or 'container'
   */
  type: {
    type: String,
    default: 'task',
  },
})

const emit = defineEmits(['update:visible', 'close'])

const ideStore = useIdeStore()

// Layout ref
const layoutRef = ref(null)

// Computed visibility for v-model
const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit('update:visible', value),
})

/**
 * Handle dialog close request.
 */
function handleClose() {
  // Check for unsaved changes
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
        closeDialog()
      })
      .catch(() => {})
  } else {
    closeDialog()
  }
}

/**
 * Close the dialog.
 */
function closeDialog() {
  dialogVisible.value = false
  emit('close')
}

/**
 * Handle dialog opened.
 */
function handleOpened() {
  // Focus editor after open
  nextTick(() => {
    layoutRef.value?.focusEditor()
  })
}

/**
 * Handle dialog closed.
 */
function handleClosed() {
  // Reset store state
  ideStore.$reset()
}
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="null"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    :fullscreen="true"
    class="ide-dialog"
    @opened="handleOpened"
    @closed="handleClosed"
  >
    <!-- Custom header -->
    <template #header>
      <div class="ide-header">
        <div class="ide-title">
          <span class="i-carbon-code mr-2" />
          <span>{{ title }}</span>
          <span v-if="taskId" class="ide-task-id"> - Task #{{ taskId }}</span>
        </div>

        <div class="ide-header-actions">
          <!-- Toggle file tree -->
          <el-tooltip
            :content="ideStore.showFileTree ? 'Hide Files' : 'Show Files'"
            placement="bottom"
          >
            <el-button
              link
              :type="ideStore.showFileTree ? 'primary' : 'default'"
              @click="ideStore.toggleFileTree()"
            >
              <span class="i-carbon-folder-details" />
            </el-button>
          </el-tooltip>

          <!-- Toggle terminal -->
          <el-tooltip
            :content="ideStore.showTerminal ? 'Hide Terminal' : 'Show Terminal'"
            placement="bottom"
          >
            <el-button
              link
              :type="ideStore.showTerminal ? 'primary' : 'default'"
              @click="ideStore.toggleTerminal()"
            >
              <span class="i-carbon-terminal" />
            </el-button>
          </el-tooltip>

          <!-- Terminal position toggle -->
          <el-tooltip
            :content="
              ideStore.terminalPosition === 'right'
                ? 'Terminal to Bottom'
                : 'Terminal to Right'
            "
            placement="bottom"
          >
            <el-button link @click="ideStore.toggleTerminalPosition()">
              <span
                :class="
                  ideStore.terminalPosition === 'right'
                    ? 'i-carbon-split-screen'
                    : 'i-carbon-row'
                "
              />
            </el-button>
          </el-tooltip>

          <el-divider direction="vertical" />

          <!-- Close button -->
          <el-tooltip content="Close (Esc)" placement="bottom">
            <el-button link @click="handleClose">
              <span class="i-carbon-close text-lg" />
            </el-button>
          </el-tooltip>
        </div>
      </div>
    </template>

    <!-- Main content -->
    <div class="ide-content">
      <IdeLayout
        v-if="visible && taskId"
        ref="layoutRef"
        :task-id="taskId"
        :type="type"
        :container-name="containerName"
        @close="handleClose"
      />
    </div>

    <!-- Status bar -->
    <template #footer>
      <IdeStatusBar />
    </template>
  </el-dialog>
</template>

<style scoped>
/* Force fullscreen dialog to use fixed positioning and explicit dimensions */
.ide-dialog :deep(.el-overlay) {
  position: fixed !important;
  inset: 0 !important;
  overflow: hidden !important;
}

.ide-dialog :deep(.el-dialog) {
  display: flex !important;
  flex-direction: column !important;
  position: fixed !important;
  inset: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  max-width: 100vw !important;
  max-height: 100vh !important;
  overflow: hidden !important;
}

.ide-dialog :deep(.el-dialog__header) {
  padding: 0 !important;
  margin: 0 !important;
  flex: 0 0 auto !important;
}

.ide-dialog :deep(.el-dialog__body) {
  flex: 1 1 auto !important;
  padding: 0 !important;
  overflow: hidden !important;
  min-height: 0 !important; /* Critical for flex child containment */
}

.ide-dialog :deep(.el-dialog__footer) {
  padding: 0 !important;
  flex: 0 0 auto !important;
}

.ide-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--el-bg-color-page);
  border-bottom: 1px solid var(--el-border-color-light);
}

.ide-title {
  display: flex;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
}

.ide-task-id {
  font-weight: 400;
  color: var(--el-text-color-secondary);
  margin-left: 4px;
}

.ide-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ide-content {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
</style>
