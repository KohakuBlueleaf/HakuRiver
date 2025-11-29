<script setup>
/**
 * EditorTabs - Tab bar for open files.
 *
 * Features:
 * - Display open files as tabs
 * - Close buttons with dirty indicator
 * - Tab switching
 * - Middle-click to close
 */

import { useIdeStore } from '@/stores/ide'
import { getFileIcon, getFileIconColor } from '@/utils/fileIcons'

const emit = defineEmits(['close', 'close-others', 'close-all'])

const ideStore = useIdeStore()

// Get icon for a file
function getIcon(file) {
  return getFileIcon(file.name, 'file')
}

function getIconColor(file) {
  return getFileIconColor(file.name, 'file')
}

// Handle tab click
function handleTabClick(file) {
  ideStore.setActiveFile(file.path)
}

// Handle close click
function handleClose(e, file) {
  e.stopPropagation()
  emit('close', file)
}

// Handle middle-click to close
function handleMiddleClick(e, file) {
  if (e.button === 1) {
    e.preventDefault()
    emit('close', file)
  }
}

// Handle context menu (right-click)
function handleContextMenu(e, file) {
  e.preventDefault()
  // Could show a context menu here
}
</script>

<template>
  <div class="editor-tabs">
    <div class="tabs-container">
      <div
        v-for="file in ideStore.openFiles"
        :key="file.path"
        class="tab"
        :class="{
          active: ideStore.activeFilePath === file.path,
          dirty: file.isDirty,
        }"
        :title="file.path"
        @click="handleTabClick(file)"
        @mousedown="handleMiddleClick($event, file)"
        @contextmenu="handleContextMenu($event, file)">
        <!-- File icon -->
        <span
          class="tab-icon"
          :class="[getIcon(file), getIconColor(file)]" />

        <!-- File name -->
        <span class="tab-name">{{ file.name }}</span>

        <!-- Dirty indicator or close button -->
        <span
          class="tab-close"
          @click="handleClose($event, file)">
          <span
            v-if="file.isDirty"
            class="dirty-dot" />
          <span
            v-else
            class="i-carbon-close" />
        </span>
      </div>
    </div>

    <!-- Actions -->
    <div
      v-if="ideStore.openFiles.length > 0"
      class="tabs-actions">
      <el-dropdown
        trigger="click"
        size="small">
        <el-button
          link
          size="small">
          <span class="i-carbon-overflow-menu-horizontal" />
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="emit('close-others')">
              <span class="i-carbon-close mr-2" />
              Close Others
            </el-dropdown-item>
            <el-dropdown-item @click="emit('close-all')">
              <span class="i-carbon-close-filled mr-2" />
              Close All
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<style scoped>
.editor-tabs {
  display: flex;
  align-items: center;
  background: var(--el-bg-color-page);
  border-bottom: 1px solid var(--el-border-color-light);
  height: 36px;
  flex-shrink: 0;
  overflow: hidden;
}

.tabs-container {
  display: flex;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.tabs-container::-webkit-scrollbar {
  height: 4px;
}

.tabs-container::-webkit-scrollbar-thumb {
  background: var(--el-border-color);
  border-radius: 2px;
}

.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  height: 36px;
  cursor: pointer;
  border-right: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color-page);
  transition: background-color 0.1s ease;
  flex-shrink: 0;
  max-width: 200px;
}

.tab:hover {
  background: var(--el-fill-color-light);
}

.tab.active {
  background: var(--el-bg-color);
  border-bottom: 2px solid var(--el-color-primary);
  margin-bottom: -1px;
}

.tab-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.tab-name {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tab-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition:
    opacity 0.1s ease,
    background-color 0.1s ease;
}

.tab:hover .tab-close,
.tab.dirty .tab-close {
  opacity: 1;
}

.tab-close:hover {
  background: var(--el-fill-color);
}

.dirty-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-warning);
}

.tabs-actions {
  padding: 0 8px;
  flex-shrink: 0;
}
</style>
