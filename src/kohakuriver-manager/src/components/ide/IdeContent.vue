<script setup>
/**
 * IdeContent - IDE content component for modal display.
 *
 * Wraps IdeLayout with header controls.
 */

import { useIdeStore } from '@/stores/ide'
import IdeLayout from './IdeLayout.vue'
import IdeStatusBar from './common/IdeStatusBar.vue'

const props = defineProps({
  /**
   * Task ID to connect to (or container name for container mode)
   */
  taskId: {
    type: [Number, String],
    required: true,
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
  /**
   * File tree mode: 'vps' shows sections, 'container' shows only root
   */
  fileTreeMode: {
    type: String,
    default: 'vps',
  },
  /**
   * Title to display in the toolbar
   */
  title: {
    type: String,
    default: null,
  },
})

const emit = defineEmits(['close'])

const ideStore = useIdeStore()

// Layout ref
const layoutRef = ref(null)

/**
 * Handle close request.
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
        doClose()
      })
      .catch(() => {})
  } else {
    doClose()
  }
}

/**
 * Actually close the IDE.
 */
function doClose() {
  console.log('IdeContent: doClose called, emitting close')
  emit('close')
}

// Expose methods
defineExpose({
  focusEditor: () => layoutRef.value?.focusEditor(),
  refreshTree: () => layoutRef.value?.refreshTree(),
})
</script>

<template>
  <div class="ide-content-wrapper">
    <!-- Header toolbar -->
    <div class="ide-toolbar">
      <div class="ide-toolbar-left">
        <span class="i-carbon-code mr-2" />
        <span class="ide-title">{{ title || `VPS #${taskId}` }}</span>
      </div>

      <div class="ide-toolbar-actions">
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
        <el-tooltip content="Close IDE" placement="bottom">
          <el-button type="danger" size="small" @click="handleClose">
            <span class="i-carbon-close" />
          </el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- Main content -->
    <div class="ide-main">
      <IdeLayout
        ref="layoutRef"
        :task-id="taskId"
        :type="type"
        :container-name="containerName"
        :file-tree-mode="fileTreeMode"
        @close="handleClose"
      />
    </div>

    <!-- Status bar -->
    <div class="ide-statusbar">
      <IdeStatusBar />
    </div>
  </div>
</template>

<style scoped>
.ide-content-wrapper {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: var(--el-bg-color);
  overflow: hidden;
}

.ide-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--el-bg-color-page);
  border-bottom: 1px solid var(--el-border-color-light);
  flex: 0 0 auto;
}

.ide-toolbar-left {
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.ide-title {
  font-family: monospace;
}

.ide-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ide-main {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

.ide-statusbar {
  flex: 0 0 auto;
}
</style>
