<script setup>
/**
 * FileTreeNode - A single node in the file tree.
 *
 * Recursive component that renders files and directories.
 */

import { useIdeStore } from '@/stores/ide'
import { getFileIcon, getFileIconColor } from '@/utils/fileIcons'

const props = defineProps({
  /**
   * File/directory entry object
   */
  entry: {
    type: Object,
    required: true,
  },
  /**
   * Nesting depth (for indentation)
   */
  depth: {
    type: Number,
    default: 0,
  },
  /**
   * Function to get children from cache
   */
  getChildren: {
    type: Function,
    required: true,
  },
  /**
   * Function to load directory
   */
  loadDirectory: {
    type: Function,
    required: true,
  },
})

const emit = defineEmits(['click', 'dblclick', 'toggle-expand', 'contextmenu'])

const ideStore = useIdeStore()

// Computed properties
const isDirectory = computed(() => props.entry.type === 'directory')
const isExpanded = computed(() => ideStore.isExpanded(props.entry.path))
const isLoading = computed(() => ideStore.isLoading(props.entry.path))
const isSelected = computed(() => ideStore.selectedPath === props.entry.path)
const isOpen = computed(() => ideStore.openFilePaths.includes(props.entry.path))

// Get children for this directory
const children = computed(() => {
  if (!isDirectory.value || !isExpanded.value) return []
  return props.getChildren(props.entry.path)
})

// Icon
const iconClass = computed(() =>
  getFileIcon(props.entry.name, props.entry.type, isExpanded.value)
)
const iconColor = computed(() => getFileIconColor(props.entry.name, props.entry.type))

// Indentation style
const indentStyle = computed(() => ({
  paddingLeft: `${props.depth * 16 + 8}px`,
}))

// Handle click
function handleClick(e) {
  e.stopPropagation()
  emit('click', props.entry)
}

// Handle double click
function handleDblClick(e) {
  e.stopPropagation()
  if (isDirectory.value) {
    emit('toggle-expand', props.entry)
  } else {
    emit('dblclick', props.entry)
  }
}

// Handle expand/collapse click
function handleToggle(e) {
  e.stopPropagation()
  emit('toggle-expand', props.entry)
}

// Handle right-click context menu
function handleContextMenu(e) {
  e.preventDefault()
  e.stopPropagation()
  emit('contextmenu', e, props.entry)
}

// Format file size
function formatSize(bytes) {
  if (bytes < 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <div class="file-tree-node">
    <!-- Node row -->
    <div
      class="node-row"
      :class="{
        selected: isSelected,
        open: isOpen,
        directory: isDirectory,
      }"
      :style="indentStyle"
      @click="handleClick"
      @dblclick="handleDblClick"
      @contextmenu="handleContextMenu"
    >
      <!-- Expand/collapse arrow for directories -->
      <span v-if="isDirectory" class="node-arrow" @click="handleToggle">
        <el-icon v-if="isLoading" class="is-loading">
          <span class="i-carbon-circle-dash" />
        </el-icon>
        <span
          v-else
          class="i-carbon-chevron-right"
          :class="{ 'rotate-90': isExpanded }"
        />
      </span>
      <span v-else class="node-arrow-placeholder" />

      <!-- File/folder icon -->
      <span class="node-icon" :class="[iconClass, iconColor]" />

      <!-- File name -->
      <span class="node-name" :title="entry.path">
        {{ entry.name }}
      </span>

      <!-- File size (for files only) -->
      <span v-if="!isDirectory && entry.size > 0" class="node-size">
        {{ formatSize(entry.size) }}
      </span>
    </div>

    <!-- Children (recursive) -->
    <div v-if="isDirectory && isExpanded && children.length > 0" class="node-children">
      <FileTreeNode
        v-for="child in children"
        :key="child.path"
        :entry="child"
        :depth="depth + 1"
        :get-children="getChildren"
        :load-directory="loadDirectory"
        @click="emit('click', $event)"
        @dblclick="emit('dblclick', $event)"
        @toggle-expand="emit('toggle-expand', $event)"
        @contextmenu="(e, entry) => emit('contextmenu', e, entry)"
      />
    </div>
  </div>
</template>

<style scoped>
.file-tree-node {
  user-select: none;
}

.node-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 13px;
  border-radius: 4px;
  margin: 1px 4px;
  transition: background-color 0.1s ease;
}

.node-row:hover {
  background: var(--el-fill-color-light);
}

.node-row.selected {
  background: var(--el-color-primary-light-9);
}

.node-row.open {
  font-weight: 500;
}

.node-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  transition: transform 0.1s ease;
}

.node-arrow:hover {
  background: var(--el-fill-color);
  border-radius: 2px;
}

.node-arrow .rotate-90 {
  transform: rotate(90deg);
}

.node-arrow-placeholder {
  width: 16px;
  flex-shrink: 0;
}

.node-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-primary);
}

.node-size {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
  flex-shrink: 0;
}

.node-children {
  /* Children are already indented via padding */
}
</style>
