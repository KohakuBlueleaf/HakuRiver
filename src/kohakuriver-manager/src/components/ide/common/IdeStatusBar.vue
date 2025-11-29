<script setup>
/**
 * IdeStatusBar - Bottom status bar for the IDE.
 *
 * Shows:
 * - Cursor position (line, column)
 * - Language
 * - Encoding
 * - Auto-save status
 * - Connection status
 */

import { useIdeStore } from '@/stores/ide'

const ideStore = useIdeStore()

// Current file info
const cursorLine = computed(() => ideStore.activeFile?.cursorPosition?.line || 1)
const cursorColumn = computed(() => ideStore.activeFile?.cursorPosition?.column || 1)
const language = computed(() => {
  const lang = ideStore.activeFile?.language || 'plaintext'
  // Capitalize first letter
  return lang.charAt(0).toUpperCase() + lang.slice(1)
})
const encoding = computed(() => {
  const enc = ideStore.activeFile?.encoding || 'utf-8'
  return enc.toUpperCase()
})

// Save status
const isSaving = computed(() => {
  if (!ideStore.activeFilePath) return false
  return ideStore.isSaving(ideStore.activeFilePath)
})

const isDirty = computed(() => ideStore.activeFile?.isDirty || false)
</script>

<template>
  <div class="ide-status-bar">
    <!-- Left side -->
    <div class="status-left">
      <!-- Connection status -->
      <div class="status-item">
        <span class="status-dot connected" />
        <span>Connected</span>
      </div>
    </div>

    <!-- Right side -->
    <div class="status-right">
      <!-- Cursor position -->
      <div v-if="ideStore.activeFile" class="status-item">
        <span>Ln {{ cursorLine }}, Col {{ cursorColumn }}</span>
      </div>

      <!-- Language -->
      <div v-if="ideStore.activeFile" class="status-item clickable">
        <span>{{ language }}</span>
      </div>

      <!-- Encoding -->
      <div v-if="ideStore.activeFile" class="status-item">
        <span>{{ encoding }}</span>
      </div>

      <!-- Auto-save status -->
      <div class="status-item" :class="{ saving: isSaving, dirty: isDirty }">
        <el-tooltip
          :content="
            isSaving
              ? 'Saving...'
              : isDirty
                ? 'Unsaved changes'
                : ideStore.autoSaveEnabled
                  ? 'Auto-save enabled'
                  : 'Auto-save disabled'
          "
          placement="top"
        >
          <span class="auto-save-status">
            <span v-if="isSaving" class="i-carbon-circle-dash is-loading" />
            <span v-else-if="isDirty" class="i-carbon-circle-filled dirty-icon" />
            <span v-else class="i-carbon-checkmark-filled saved-icon" />
            <span>{{ isSaving ? 'Saving...' : 'Auto-save' }}</span>
          </span>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ide-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  height: 24px;
  background: var(--el-color-primary);
  color: white;
  font-size: 12px;
}

.status-left,
.status-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border-radius: 2px;
}

.status-item.clickable {
  cursor: pointer;
}

.status-item.clickable:hover {
  background: rgba(255, 255, 255, 0.1);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.connected {
  background: #4caf50;
}

.status-dot.disconnected {
  background: #f44336;
}

.auto-save-status {
  display: flex;
  align-items: center;
  gap: 4px;
}

.dirty-icon {
  color: #ff9800;
}

.saved-icon {
  color: #4caf50;
}

.status-item.saving {
  opacity: 0.8;
}

.is-loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
