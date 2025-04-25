<!-- frontend/src/components/LogContentModal.vue -->
<template>
  <el-dialog
    v-model="dialogVisible"
    :title="modalTitle"
    width="80vw"
    top="5vh"
    :close-on-click-modal="true"
    class="log-content-modal"
    destroy-on-close
    draggable
  >
    <div class="log-modal-container">
      <el-scrollbar class="log-scrollbar-modal">
        <pre class="code-block log-content-modal">{{ logContent || 'Loading log content...' }}</pre>
      </el-scrollbar>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="dialogVisible = false">Close</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue';
import { ElDialog, ElScrollbar, ElButton } from 'element-plus'; // Explicitly import components

const props = defineProps({
  modelValue: Boolean, // v-model binding for dialog visibility
  title: String, // Title for the modal (e.g., "Stdout for Task XXX")
  content: String, // The actual log content text
});

const emit = defineEmits(['update:modelValue']);

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

const modalTitle = computed(() => props.title || 'Log Content');
const logContent = computed(() => props.content);

// No need for lifecycle hooks or API calls here, just displays passed data
</script>

<style>

.log-modal-container .el-scrollbar__view{
  height: 100%; /* Ensure scrollbar view takes full height */
}
</style>

<style scoped>
/* Specific styles for the Log Content Modal */
.log-content-modal .el-dialog__body {
  padding: 0 20px 20px 20px; /* Adjust padding */
}

.log-modal-container {
  height: calc(90vh - 120px); /* Adjust height based on dialog padding and footer height */
  /* border: 1px solid var(--el-border-color); */ /* Optional border */
  border-radius: 4px;
  overflow: hidden; /* Ensure scrollbar works within container */
}

.log-scrollbar-modal {
  height: 100%; /* Make scrollbar take full height of container */
}

.log-content-modal {
  /* Reusing/adjusting .code-block styles */
  background-color: var(--el-bg-color-overlay); /* Match dialog background */
  color: var(--el-text-color-primary);
  padding: 10px; /* Adjust padding */
  margin: 0; /* Remove default margin */
  font-family: monospace;
  white-space: pre-wrap; /* Preserve newlines and spaces, wrap long lines */
  word-break: break-word; /* Break long words if needed */
  font-size: 0.9em; /* Adjust font size */
  line-height: 1.5; /* Improve readability */
  min-height: 100%; /* Ensure pre tag takes full height if content is short */
  box-sizing: border-box; /* Include padding in height calculation */
}

/* Ensure the pre tag within the scrollbar doesn't cause extra scrollbars */
.log-scrollbar-modal :deep(.el-scrollbar__wrap) {
  overflow-x: hidden !important; /* Hide horizontal scrollbar */
}
</style>
