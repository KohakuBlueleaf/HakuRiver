<template>
  <div>
    <h1>Tasks</h1>

    <!-- Submit Task Button -->
    <el-button type="primary" @click="openSubmitDialog"> Submit New Task </el-button>

    <!-- Submit Task Dialog -->
    <el-dialog
      v-model="submitDialogVisible"
      title="Submit New Task"
      width="600px"
      :close-on-click-modal="false"
      @closed="resetForm"
    >
      <el-form
        ref="taskFormRef"
        :model="taskForm"
        :rules="taskFormRules"
        label-position="top"
        @submit.prevent="handleTaskSubmit"
      >
        <el-form-item label="Command" prop="command">
          <el-input v-model="taskForm.command" placeholder="e.g., /path/to/shared/scripts/my_script.sh or python" />
        </el-form-item>
        <el-form-item label="Arguments (one per line)" prop="arguments_text">
          <el-input
            v-model="taskForm.arguments_text"
            type="textarea"
            :rows="3"
            placeholder="e.g., --input data.txt
--output results.out"
          />
          <el-text size="small" type="info">Arguments are split by newline.</el-text>
        </el-form-item>
        <el-form-item label="Environment Variables (KEY=VALUE, one per line)" prop="env_vars_text">
          <el-input
            v-model="taskForm.env_vars_text"
            type="textarea"
            :rows="3"
            placeholder="e.g., MY_VAR=ABC
OTHER_VAR=123"
          />
          <el-text size="small" type="info">Variables are split by newline, format KEY=VALUE.</el-text>
        </el-form-item>
        <el-form-item label="Required CPU Cores" prop="required_cores">
          <el-input-number v-model="taskForm.required_cores" :min="1" :max="maxCoresHint" controls-position="right" />
          <!-- Optional: Show max available cores hint -->
          <!-- <el-text size="small" type="info"> Max hint: {{ maxCoresHint }} </el-text> -->
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="submitDialogVisible = false">Cancel</el-button>
          <el-button type="primary" @click="handleTaskSubmit" :loading="isSubmitting"> Submit </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Task List -->
    <el-divider />
    <h2>Task List</h2>
    <el-button @click="fetchTasks" :loading="isLoadingTasks" text size="small" style="margin-bottom: 10px"
      >Refresh List</el-button
    >
    <el-alert v-if="taskError" :title="taskError" type="error" show-icon :closable="false" style="margin-bottom: 10px" />
    <el-alert
      v-if="!backendHasGetTasks"
      title="Backend API Missing"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 10px"
    >
      The backend currently lacks an endpoint to list all tasks. Task list functionality is limited.
    </el-alert>

    <el-table
      :data="tasks"
      style="width: 100%"
      v-loading="isLoadingTasks"
      empty-text="No tasks found or backend endpoint missing"
    >
      <el-table-column prop="task_id" label="Task ID" width="180" sortable />
      <el-table-column prop="command" label="Command" />
      <el-table-column prop="arguments" label="Arguments" width="200">
        <template #default="scope">
          <!-- Display limited arguments, maybe tooltip for full list -->
          <el-tooltip
            :content="formatArgsTooltip(scope.row.arguments)"
            placement="top"
            :disabled="!formatArgsTooltip(scope.row.arguments)"
          >
            <span class="arg-preview">{{ formatArgsPreview(scope.row.arguments) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="required_cores" label="Cores" width="80" sortable />
      <el-table-column prop="status" label="Status" width="120" sortable>
        <template #default="scope">
          <el-tag :type="getTaskStatusType(scope.row.status)">
            {{ scope.row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="assigned_node" label="Assigned Node" width="150" sortable />
      <el-table-column prop="submitted_at" label="Submitted" width="170" sortable>
        <template #default="scope">{{ formatDateTime(scope.row.submitted_at) }}</template>
      </el-table-column>
      <el-table-column prop="started_at" label="Started" width="170" sortable>
        <template #default="scope">{{ formatDateTime(scope.row.started_at) }}</template>
      </el-table-column>
      <el-table-column prop="completed_at" label="Completed" width="170" sortable>
        <template #default="scope">{{ formatDateTime(scope.row.completed_at) }}</template>
      </el-table-column>
      <el-table-column label="Actions" width="100" fixed="right">
        <template #default="scope">
          <el-button
            link
            type="danger"
            size="small"
            @click="handleKill(scope.row.task_id)"
            :disabled="!isKillable(scope.row.status)"
            v-loading="killingState[scope.row.task_id]"
          >
            Kill
          </el-button>
          <!-- Add View Logs button later -->
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue';
import api from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';

// --- State ---
const tasks = ref([]);
const isLoadingTasks = ref(false);
const taskError = ref(null);
let taskPollingInterval = null;
const TASK_POLLING_RATE_MS = 5000; // Poll tasks every 5 seconds
const backendHasGetTasks = ref(typeof api.getTasks === 'function'); // Check if the assumed function exists

const submitDialogVisible = ref(false);
const taskFormRef = ref(null); // Reference to the ElForm component
const isSubmitting = ref(false);
const taskForm = reactive({
  command: '',
  arguments_text: '', // Use textareas for multi-line input
  env_vars_text: '',
  required_cores: 1,
});
// Simple validation rules
const taskFormRules = reactive({
  command: [{ required: true, message: 'Command is required', trigger: 'blur' }],
  required_cores: [{ required: true, message: 'Number of cores is required', trigger: 'blur' }],
  // Arguments and env vars are optional
});

const killingState = reactive({}); // Track loading state for individual kill buttons

// --- API Functions ---

// *** IMPORTANT: Assumes api.getTasks() exists and calls a backend endpoint like GET /tasks ***
const fetchTasks = async () => {
  if (!backendHasGetTasks.value) {
    taskError.value = "Backend API '/tasks' endpoint not implemented.";
    isLoadingTasks.value = false;
    tasks.value = [];
    // Stop polling if the endpoint doesn't exist
    if (taskPollingInterval) clearInterval(taskPollingInterval);
    return;
  }
  if (isLoadingTasks.value) return; // Prevent overlap

  isLoadingTasks.value = true;
  taskError.value = null;
  try {
    // This is the assumed function call
    const response = await api.getTasks(); // Assumes this returns an array of tasks
    tasks.value = response.data; // Update local task list
  } catch (err) {
    console.error('Error fetching tasks:', err);
    taskError.value = 'Failed to fetch task list.';
    tasks.value = [];
  } finally {
    isLoadingTasks.value = false;
  }
};

const submitTaskApi = async (formData) => {
  isSubmitting.value = true;
  try {
    // 1. Parse arguments and env vars from textareas
    const argsList = formData.arguments_text
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line !== ''); // Remove empty lines

    const envDict = formData.env_vars_text
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line !== '' && line.includes('='))
      .reduce((acc, line) => {
        const [key, ...valueParts] = line.split('=');
        acc[key.trim()] = valueParts.join('=').trim(); // Handle values with '='
        return acc;
      }, {});

    // 2. Prepare payload for the API
    const payload = {
      command: formData.command,
      arguments: argsList,
      env_vars: envDict,
      required_cores: formData.required_cores,
    };

    // 3. Call API
    const response = await api.submitTask(payload);
    ElMessage({
      message: `Task submitted successfully! ID: ${response.data.task_id}`,
      type: 'success',
    });
    submitDialogVisible.value = false;
    fetchTasks(); // Refresh the task list after submission
  } catch (error) {
    console.error('Error submitting task:', error);
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({
      message: `Failed to submit task: ${errorDetail}`,
      type: 'error',
    });
  } finally {
    isSubmitting.value = false;
  }
};

const killTaskApi = async (taskId) => {
  killingState[taskId] = true; // Set loading for specific button
  try {
    await api.killTask(taskId);
    ElMessage({
      message: `Kill request sent for task ${taskId}.`,
      type: 'info', // Use info as it might take time
    });
    // Optimistic UI update or wait for poll
    const task = tasks.value.find((t) => t.task_id === taskId);
    if (task) {
      task.status = 'killed'; // Or 'killing' if backend confirms later
    }
    // Alternatively, trigger fetchTasks() immediately after a short delay
    // setTimeout(fetchTasks, 1000);
  } catch (error) {
    console.error(`Error killing task ${taskId}:`, error);
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({
      message: `Failed to kill task ${taskId}: ${errorDetail}`,
      type: 'error',
    });
  } finally {
    killingState[taskId] = false; // Reset loading state
  }
};

// --- Dialog and Form Handling ---
const openSubmitDialog = () => {
  submitDialogVisible.value = true;
};

const resetForm = () => {
  if (taskFormRef.value) {
    taskFormRef.value.resetFields();
  }
  // Also manually reset textarea content if resetFields doesn't cover it
  taskForm.arguments_text = '';
  taskForm.env_vars_text = '';
};

const handleTaskSubmit = async () => {
  if (!taskFormRef.value) return;
  await taskFormRef.value.validate((valid, fields) => {
    if (valid) {
      submitTaskApi(taskForm); // Call the API submission function
    } else {
      console.log('Form validation failed:', fields);
      ElMessage({ message: 'Please fill in all required fields correctly.', type: 'warning' });
    }
  });
};

// --- Kill Handling ---
const handleKill = (taskId) => {
  ElMessageBox.confirm(`Are you sure you want to kill task ${taskId}? This cannot be undone.`, 'Confirm Kill', {
    confirmButtonText: 'Kill Task',
    cancelButtonText: 'Cancel',
    type: 'warning',
    draggable: true,
  })
    .then(() => {
      killTaskApi(taskId);
    })
    .catch(() => {
      // Action cancelled
      ElMessage({ type: 'info', message: 'Kill action cancelled.' });
    });
};

// --- Lifecycle Hooks ---
onMounted(() => {
  fetchTasks(); // Initial fetch
  if (backendHasGetTasks.value) {
    // Only poll if endpoint exists
    taskPollingInterval = setInterval(fetchTasks, TASK_POLLING_RATE_MS);
  }
});

onUnmounted(() => {
  if (taskPollingInterval) {
    clearInterval(taskPollingInterval);
  }
});

// --- Helper Functions ---
const formatDateTime = (isoString) => {
  if (!isoString) return '-';
  try {
    return new Date(isoString).toLocaleString();
  } catch (e) {
    return 'Invalid Date';
  }
};

const getTaskStatusType = (status) => {
  status = status?.toLowerCase();
  if (status === 'completed') return 'success';
  if (status === 'running') return ''; // Default blue
  if (status === 'pending' || status === 'assigning') return 'warning';
  if (status === 'failed' || status === 'lost' || status === 'killed') return 'danger';
  return 'info'; // Default for unknown states
};

const isKillable = (status) => {
  status = status?.toLowerCase();
  return ['pending', 'assigning', 'running'].includes(status);
};

const formatArgsPreview = (args) => {
  if (!args || args.length === 0) return '-';
  return args.join(' ').substring(0, 50) + (args.join(' ').length > 50 ? '...' : '');
};

const formatArgsTooltip = (args) => {
  if (!args || args.length === 0) return null;
  return args.join(' ');
};

// Placeholder for max cores hint (could be fetched from nodes)
const maxCoresHint = ref(32); // Default value
</script>

<style scoped>
.el-table {
  margin-top: 20px;
}
.el-alert {
  margin-bottom: 15px;
}
.dialog-footer {
  text-align: right;
}
.arg-preview {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: inline-block; /* Required for text-overflow */
  max-width: 100%; /* Ensure it doesn't overflow cell */
  vertical-align: bottom; /* Align with potential tooltip icon */
}
</style>
