<script setup>
/**
 * EditorPane - Container for editor tabs and Monaco editor.
 *
 * Features:
 * - Tab management
 * - Editor content binding
 * - Auto-save integration
 * - Empty state
 */

import { useIdeStore } from '@/stores/ide'
import { useAutoSave } from '@/composables/useAutoSave'
import EditorTabs from './EditorTabs.vue'
import MonacoEditor from './MonacoEditor.vue'

const ideStore = useIdeStore()
const autoSave = useAutoSave()

const editorRef = ref(null)

// Current file content (two-way binding)
const content = computed({
  get: () => ideStore.activeFile?.content || '',
  set: (value) => {
    if (ideStore.activeFilePath) {
      ideStore.updateFileContent(ideStore.activeFilePath, value)

      // Schedule auto-save
      if (ideStore.autoSaveEnabled) {
        autoSave.scheduleAutoSave(ideStore.activeFilePath)
      }
    }
  },
})

// Current language
const language = computed(() => ideStore.activeFile?.language || 'plaintext')

// Read-only if binary
const readOnly = computed(() => ideStore.activeFile?.encoding === 'base64')

// Handle file close
function handleClose(file) {
  // Check for unsaved changes
  if (file.isDirty) {
    ElMessageBox.confirm(
      `Do you want to save changes to "${file.name}"?`,
      'Unsaved Changes',
      {
        confirmButtonText: 'Save',
        cancelButtonText: "Don't Save",
        distinguishCancelAndClose: true,
        type: 'warning',
      }
    )
      .then(() => {
        // Save and close
        autoSave.saveNow(file.path).then(() => {
          ideStore.closeFile(file.path)
        })
      })
      .catch((action) => {
        if (action === 'cancel') {
          // Don't save, just close
          ideStore.closeFile(file.path)
        }
        // 'close' means they clicked X, do nothing
      })
  } else {
    ideStore.closeFile(file.path)
  }
}

// Handle close others
function handleCloseOthers() {
  const currentPath = ideStore.activeFilePath
  const otherFiles = ideStore.openFiles.filter((f) => f.path !== currentPath)

  // Check for unsaved files
  const dirtyFiles = otherFiles.filter((f) => f.isDirty)
  if (dirtyFiles.length > 0) {
    ElMessageBox.confirm(
      `${dirtyFiles.length} file(s) have unsaved changes. Close anyway?`,
      'Unsaved Changes',
      {
        confirmButtonText: 'Close All',
        cancelButtonText: 'Cancel',
        type: 'warning',
      }
    )
      .then(() => {
        ideStore.closeOtherFiles(currentPath)
      })
      .catch(() => {})
  } else {
    ideStore.closeOtherFiles(currentPath)
  }
}

// Handle close all
function handleCloseAll() {
  const dirtyFiles = ideStore.openFiles.filter((f) => f.isDirty)
  if (dirtyFiles.length > 0) {
    ElMessageBox.confirm(
      `${dirtyFiles.length} file(s) have unsaved changes. Close anyway?`,
      'Unsaved Changes',
      {
        confirmButtonText: 'Close All',
        cancelButtonText: 'Cancel',
        type: 'warning',
      }
    )
      .then(() => {
        ideStore.closeAllFiles()
      })
      .catch(() => {})
  } else {
    ideStore.closeAllFiles()
  }
}

// Handle save from editor Ctrl+S
function handleSave() {
  if (ideStore.activeFilePath) {
    autoSave.saveNow(ideStore.activeFilePath)
  }
}

// Handle cursor change
function handleCursorChange(position) {
  if (ideStore.activeFilePath) {
    ideStore.updateFileCursor(ideStore.activeFilePath, position.line, position.column)
  }
}

// Expose editor ref methods
defineExpose({
  focus: () => editorRef.value?.focus(),
  formatDocument: () => editorRef.value?.formatDocument(),
})
</script>

<template>
  <div class="editor-pane">
    <!-- Tabs -->
    <EditorTabs
      v-if="ideStore.openFiles.length > 0"
      @close="handleClose"
      @close-others="handleCloseOthers"
      @close-all="handleCloseAll"
    />

    <!-- Editor -->
    <div class="editor-content">
      <MonacoEditor
        v-if="ideStore.activeFile"
        ref="editorRef"
        v-model="content"
        :language="language"
        :read-only="readOnly"
        :path="ideStore.activeFilePath"
        theme="vs-dark"
        @save="handleSave"
        @cursor-change="handleCursorChange"
      />

      <!-- Empty state -->
      <div v-else class="editor-empty">
        <div class="empty-icon">
          <span class="i-carbon-document-blank text-6xl text-gray-500" />
        </div>
        <div class="empty-text">
          <p>No file open</p>
          <p class="text-sm text-gray-500">
            Select a file from the file tree to edit
          </p>
        </div>
        <div class="empty-shortcuts">
          <div class="shortcut">
            <kbd>Ctrl</kbd> + <kbd>S</kbd>
            <span>Save</span>
          </div>
          <div class="shortcut">
            <kbd>Ctrl</kbd> + <kbd>B</kbd>
            <span>Toggle Files</span>
          </div>
          <div class="shortcut">
            <kbd>Ctrl</kbd> + <kbd>`</kbd>
            <span>Toggle Terminal</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
  overflow: hidden;
}

.editor-content {
  flex: 1;
  overflow: hidden;
  position: relative;
}

.editor-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
  color: var(--el-text-color-secondary);
  padding: 24px;
}

.empty-icon {
  opacity: 0.5;
}

.empty-text {
  text-align: center;
}

.empty-shortcuts {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 24px;
  opacity: 0.6;
}

.shortcut {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.shortcut kbd {
  display: inline-block;
  padding: 2px 6px;
  font-family: monospace;
  font-size: 11px;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}

.shortcut span {
  color: var(--el-text-color-secondary);
}
</style>
