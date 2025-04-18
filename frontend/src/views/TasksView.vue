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
      top="5vh"
      draggable
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

        <!-- Resource Requirements Row -->
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Required CPU Cores" prop="required_cores">
              <el-input-number v-model="taskForm.required_cores" :min="0" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <!-- MODIFIED: Added Memory Limit Input -->
            <el-form-item label="Memory Limit (Optional)" prop="memory_limit_str">
              <el-input v-model="taskForm.memory_limit_str" placeholder="e.g., 512M, 4G" clearable>
                <template #append>MB/GB</template>
              </el-input>
              <el-text size="small" type="info">Examples: 512M, 4G, 2048K. No suffix means bytes.</el-text>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="Target Node(s) / NUMA Node(s)" prop="selectedTargets">
          <el-select
            v-model="taskForm.selectedTargets"
            multiple
            filterable
            clearable
            placeholder="Select target(s)"
            style="width: 100%"
            :loading="isLoadingNodes"
            loading-text="Loading available nodes..."
            no-data-text="No nodes found or failed to load"
          >
            <el-option v-for="item in targetOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-text size="small" type="info">Select one or more nodes. Suffix :N targets NUMA node N.</el-text>
        </el-form-item>

        <el-card shadow="never" style="margin-top: 10px; background-color: var(--el-fill-color-lighter)">
          <template #header>
            <div class="card-header" style="font-weight: normal; font-size: 0.95em">
              <span>Sandboxing Options (via systemd)</span>
            </div>
          </template>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-tooltip content="Uses systemd PrivateNetwork=yes. Task cannot access network." placement="top">
                <el-checkbox v-model="taskForm.use_private_network" label="Isolate Network" size="large" border />
              </el-tooltip>
            </el-col>
            <el-col :span="12">
              <el-tooltip content="Uses systemd PrivatePID=yes. Task cannot see other processes." placement="top">
                <el-checkbox v-model="taskForm.use_private_pid" label="Isolate Processes (PID)" size="large" border />
              </el-tooltip>
            </el-col>
          </el-row>
        </el-card>
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
    <el-button @click="fetchTasks" :loading="isLoadingTasks" text size="small" style="margin-bottom: 10px">
      Refresh List
    </el-button>
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

    <!-- Task Table with row click handler -->
    <el-table
      :data="tasks"
      style="width: 100%"
      v-loading="isLoadingTasks"
      empty-text="No tasks found or backend endpoint missing"
      @row-click="handleRowClick"
      highlight-current-row
      class="task-table"
    >
      <el-table-column prop="task_id" label="Task ID" sortable />
      <el-table-column prop="command" label="Command" show-overflow-tooltip />
      <el-table-column prop="arguments" label="Arguments">
        <template #default="scope">
          <el-tooltip
            :content="formatArgsTooltip(scope.row.arguments)"
            placement="top"
            :disabled="!formatArgsTooltip(scope.row.arguments)"
          >
            <span class="arg-preview">{{ formatArgsPreview(scope.row.arguments) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="required_cores" label="Cores" sortable />
      <el-table-column prop="status" label="Status" sortable>
        <template #default="scope">
          <el-tag :type="getTaskStatusType(scope.row.status)">
            {{ scope.row.status }}
            <span v-if="scope.row.assignment_suspicion_count > 0" style="margin-left: 4px">(?)</span>
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="assigned_node" label="Assigned Node" sortable />
      <el-table-column prop="target_numa_node_id" label="Target NUMA" sortable width="130">
        <template #default="scope">{{ scope.row.target_numa_node_id ?? 'Node Wide' }}</template>
      </el-table-column>
      <el-table-column prop="submitted_at" label="Submitted" sortable>
        <template #default="scope">{{ formatDateTime(scope.row.submitted_at) }}</template>
      </el-table-column>
      <!-- Removed Started/Completed from main table for brevity -->
      <el-table-column label="Actions" fixed="right">
        <template #default="scope">
          <!-- Stop propagation to prevent row click when clicking buttons -->
          <el-button
            link
            type="danger"
            size="small"
            @click.stop="handleKill(scope.row.task_id)"
            :disabled="!isKillable(scope.row.status)"
            v-loading="killingState[scope.row.task_id]"
          >
            Kill
          </el-button>
          <el-button link type="primary" size="small" @click.stop="handleRowClick(scope.row)"> Details </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Task Detail Dialog -->
    <el-dialog
      v-model="detailDialogVisible"
      :title="'Task Details - ID: ' + (selectedTaskDetail?.task_id ?? '')"
      width="70%"
      top="5vh"
      :close-on-click-modal="false"
      @closed="resetDetailView"
      draggable
    >
      <div v-if="selectedTaskDetail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Task ID">{{ selectedTaskDetail.task_id }}</el-descriptions-item>
          <el-descriptions-item label="Batch ID">{{ selectedTaskDetail.batch_id || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="Target NUMA Node">{{
            selectedTaskDetail.target_numa_node_id ?? 'Node Wide'
          }}</el-descriptions-item>
          <el-descriptions-item label="Status">
            <el-tag :type="getTaskStatusType(selectedTaskDetail.status)">
              {{ selectedTaskDetail.status }}
            </el-tag>
            <el-tag
              v-if="selectedTaskDetail.assignment_suspicion_count > 0"
              type="warning"
              size="small"
              style="margin-left: 5px"
            >
              Suspect Assignment ({{ selectedTaskDetail.assignment_suspicion_count }})
            </el-tag>
          </el-descriptions-item>

          <el-descriptions-item label="Command" :span="2">{{ selectedTaskDetail.command }}</el-descriptions-item>
          <el-descriptions-item label="Arguments" :span="2">
            <pre class="code-block">{{ selectedTaskDetail.arguments?.join('\n') || 'None' }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="Environment Vars" :span="2">
            <pre class="code-block">{{ formatEnvVars(selectedTaskDetail.env_vars) || 'None' }}</pre>
          </el-descriptions-item>

          <el-descriptions-item label="Required Cores">{{ selectedTaskDetail.required_cores }}</el-descriptions-item>
          <el-descriptions-item label="Assigned Node">{{ selectedTaskDetail.assigned_node || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="Exit Code">{{ selectedTaskDetail.exit_code ?? 'N/A' }}</el-descriptions-item>

          <el-descriptions-item label="Submitted At">{{
            formatDateTime(selectedTaskDetail.submitted_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="Stdout Path">{{ selectedTaskDetail.stdout_path || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="Started At">{{ formatDateTime(selectedTaskDetail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="Stderr Path">{{ selectedTaskDetail.stderr_path || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="Completed At">{{
            formatDateTime(selectedTaskDetail.completed_at)
          }}</el-descriptions-item>
        </el-descriptions>

        <el-divider />
        <el-row :gutter="20">
          <!-- Stdout Column -->
          <el-col :span="12">
            <div class="log-column-content">
              <h4>
                Standard Output
                <el-button
                  @click="fetchStdout"
                  :loading="isLoadingStdout"
                  text
                  size="small"
                  :icon="RefreshRight"
                  style="margin-left: 10px"
                />
              </h4>
              <el-alert
                v-if="stdoutError"
                :title="stdoutError"
                type="error"
                show-icon
                :closable="false"
                style="margin-bottom: 5px"
              />
              <el-scrollbar v-loading="isLoadingStdout" class="log-scrollbar" height="250px">
                <pre class="code-block log-content">{{ stdoutContent || 'No output fetched or available.' }}</pre>
              </el-scrollbar>
            </div>
          </el-col>
          <!-- Stderr Column -->
          <el-col :span="12">
            <div class="log-column-content">
              <h4>
                Standard Error
                <el-button
                  @click="fetchStderr"
                  :loading="isLoadingStderr"
                  text
                  size="small"
                  :icon="RefreshRight"
                  style="margin-left: 10px"
                />
              </h4>
              <el-alert
                v-if="stderrError"
                :title="stderrError"
                type="error"
                show-icon
                :closable="false"
                style="margin-bottom: 5px"
              />
              <!-- REMOVE height prop from el-scrollbar -->
              <el-scrollbar v-loading="isLoadingStderr" class="log-scrollbar" height="250px">
                <pre class="code-block log-content">{{ stderrContent || 'No error output fetched or available.' }}</pre>
              </el-scrollbar>
            </div>
          </el-col>
        </el-row>
      </div>
      <div v-else>
        <p>Loading task details...</p>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="detailDialogVisible = false">Close</el-button>
          <el-button
            type="danger"
            @click="handleKill(selectedTaskDetail?.task_id)"
            :disabled="!selectedTaskDetail || !isKillable(selectedTaskDetail.status)"
            :loading="killingState[selectedTaskDetail?.task_id]"
          >
            Kill Task
          </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue';
import api from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import { RefreshRight } from '@element-plus/icons-vue'; // Import icon

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
// MODIFIED: Update taskForm
const taskForm = reactive({
  command: '',
  arguments_text: '',
  env_vars_text: '',
  required_cores: 0,
  memory_limit_str: '', // Input as string (e.g., "512M")
  use_private_network: false,
  use_private_pid: false,
  selectedTargets: [], // Holds the array of selected target strings, e.g., ["host1:0", "host2"]
});

const availableNodes = ref([]); // Raw node data from API
const isLoadingNodes = ref(false);
const nodesError = ref(null);

const targetOptions = computed(() => {
  const options = [];
  if (!availableNodes.value) return options;

  availableNodes.value.forEach((node) => {
    // Only include online nodes as targets
    if (node.status === 'online') {
      // Option for the node as a whole
      options.push({
        label: `${node.hostname} (Node Wide)`,
        value: node.hostname,
      });

      // Add options for each NUMA node if topology exists
      if (node.numa_topology && typeof node.numa_topology === 'object') {
        Object.keys(node.numa_topology)
          .sort((a, b) => parseInt(a) - parseInt(b))
          .forEach((numaId) => {
            const numaInfo = node.numa_topology[numaId];
            const coreCount = numaInfo?.cores?.length ?? '?';
            const memGb = numaInfo?.memory_bytes ? (numaInfo.memory_bytes / 1024 ** 3).toFixed(1) : '?';
            options.push({
              // e.g., host1 / NUMA 0 (8 Cores, 64.0 GB)
              label: `  ${node.hostname} / NUMA ${numaId} (${coreCount} Cores, ${memGb} GB)`,
              value: `${node.hostname}:${numaId}`, // Format: "hostname:numa_id"
            });
          });
      }
    }
  });
  return options;
});

// MODIFIED: Add custom validator for memory string
const validateMemoryString = (rule, value, callback) => {
  if (!value) {
    callback(); // Optional field
    return;
  }
  // Basic regex for format like 123, 123K, 123M, 123G (case-insensitive)
  const memRegex = /^\d+([kmg]?)$/i;
  if (!memRegex.test(value.trim())) {
    callback(new Error('Invalid format. Use numbers with optional K, M, G suffix (e.g., 512M, 4G)'));
  } else {
    callback();
  }
};

const taskFormRules = reactive({
  command: [{ required: true, message: 'Command is required', trigger: 'blur' }],
  required_cores: [{ required: false, trigger: 'blur' }],
  // MODIFIED: Add rule for memory string format
  memory_limit_str: [{ validator: validateMemoryString, trigger: 'blur' }],
  selectedTargets: [{ type: 'array', min: 0, trigger: 'change' }],
});

const killingState = reactive({}); // Track loading state for individual kill buttons

// --- State (Task Detail Modal) ---
const detailDialogVisible = ref(false);
const selectedTaskDetail = ref(null); // Holds the full task object for the modal
const stdoutContent = ref('');
const stderrContent = ref('');
const isLoadingStdout = ref(false);
const isLoadingStderr = ref(false);
const stdoutError = ref(null);
const stderrError = ref(null);

// --- Helper Functions ---
// MODIFIED: Helper to parse memory string from form to bytes
const parseMemoryToBytes = (memStr) => {
  if (!memStr) return null;
  const str = memStr.trim().toUpperCase();
  const match = str.match(/^(\d+)([KMG]?)$/);
  if (!match) return null; // Invalid format already handled by validator, but double check

  const val = parseInt(match[1], 10);
  const unit = match[2];

  if (unit === 'G') return val * 1024 * 1024 * 1024;
  if (unit === 'M') return val * 1024 * 1024;
  if (unit === 'K') return val * 1024;
  return val; // Bytes
};

// MODIFIED: Helper to format bytes nicely for table/details
const formatBytesForTable = (bytes) => {
  if (bytes === null || bytes === undefined) return 'N/A';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

// --- API Functions ---

const fetchTasks = async () => {
  if (!backendHasGetTasks.value) {
    taskError.value = "Backend API '/tasks' endpoint not implemented.";
    isLoadingTasks.value = false;
    tasks.value = [];
    if (taskPollingInterval) clearInterval(taskPollingInterval);
    return;
  }
  if (isLoadingTasks.value) return; // Prevent overlap

  isLoadingTasks.value = true;
  taskError.value = null;
  try {
    const response = await api.getTasks();
    tasks.value = response.data.map((task) => ({
      ...task,
      // Explicitly ensure default values if backend might omit them
      required_memory_bytes: task.required_memory_bytes ?? null,
      use_private_network: task.use_private_network ?? false,
      use_private_pid: task.use_private_pid ?? false,
      systemd_unit_name: task.systemd_unit_name ?? null,
      target_numa_node_id: task.target_numa_node_id ?? null,
      batch_id: task.batch_id ?? null,
    }));
  } catch (err) {
    console.error('Error fetching tasks:', err);
    taskError.value = 'Failed to fetch task list.';
    tasks.value = [];
  } finally {
    isLoadingTasks.value = false;
  }
};

const fetchAvailableNodes = async () => {
  isLoadingNodes.value = true;
  nodesError.value = null;
  availableNodes.value = []; // Clear previous list
  try {
    // Use getNodes which should now return numa_topology
    const response = await api.getNodes();
    availableNodes.value = response.data;
  } catch (error) {
    console.error('Error fetching nodes for target selection:', error);
    nodesError.value = error.response?.data?.detail || error.message || 'Failed to load available nodes.';
  } finally {
    isLoadingNodes.value = false;
  }
};

const submitTaskApi = async (formData) => {
  isSubmitting.value = true;
  try {
    const argsList = formData.arguments_text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l !== '');
    const envDict = formData.env_vars_text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l !== '' && l.includes('='))
      .reduce((acc, line) => {
        const [key, ...valueParts] = line.split('=');
        acc[key.trim()] = valueParts.join('=').trim();
        return acc;
      }, {});
    const memoryBytes = parseMemoryToBytes(formData.memory_limit_str);

    const payload = {
      command: formData.command,
      arguments: argsList,
      env_vars: envDict,
      required_cores: formData.required_cores,
      required_memory_bytes: memoryBytes,
      use_private_network: formData.use_private_network,
      use_private_pid: formData.use_private_pid,
      targets: formData.selectedTargets, // Use the selected targets array
    };

    const responseData = await api.submitTask(payload); // api.js now returns response.data

    let message = `Batch submitted. Tasks created: ${responseData.task_ids?.join(', ') || 'None'}`;
    let messageType = 'success';

    if (responseData.failed_targets && responseData.failed_targets.length > 0) {
      message += `. ${responseData.failed_targets.length} target(s) failed: `;
      message += responseData.failed_targets.map((f) => `${f.target} (${f.reason})`).join('; ');
      messageType = 'warning'; // Partial success is a warning
      console.warn('Partial submission failure:', responseData.failed_targets);
    } else if (!responseData.task_ids || responseData.task_ids.length === 0) {
      message = 'Submission failed. No tasks were created by the host.';
      messageType = 'error';
    }

    ElMessage({
      message: message,
      type: messageType,
      duration: messageType === 'warning' || messageType === 'error' ? 7000 : 4000,
    });

    if (responseData.task_ids && responseData.task_ids.length > 0) {
      submitDialogVisible.value = false;
      fetchTasks(); // Refresh list
    }
  } catch (error) {
    console.error('Error submitting task:', error);
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({ message: `Failed to submit task: ${errorDetail}`, type: 'error', duration: 7000 });
  } finally {
    isSubmitting.value = false;
  }
};

const killTaskApi = async (taskId) => {
  if (!taskId) return;
  killingState[taskId] = true;
  try {
    await api.killTask(taskId);
    ElMessage({ message: `Kill request sent for task ${taskId}.`, type: 'info' });

    // Optimistic UI update
    const taskInList = tasks.value.find((t) => t.task_id === taskId);
    if (taskInList) taskInList.status = 'killed';

    // Update detail view if this task is selected
    if (selectedTaskDetail.value && selectedTaskDetail.value.task_id === taskId) {
      selectedTaskDetail.value.status = 'killed';
      // Optionally disable log fetching or show killed status prominently
    }
    // Optionally close detail modal?
    // detailDialogVisible.value = false;
  } catch (error) {
    console.error(`Error killing task ${taskId}:`, error);
    const errorDetail = error.response?.data?.detail || error.response?.data || error.message || 'Unknown error';
    ElMessage({ message: `Failed to kill task ${taskId}: ${errorDetail}`, type: 'error' });
  } finally {
    killingState[taskId] = false;
  }
};

// --- Log Fetching API Functions ---
const fetchStdout = async () => {
  if (!selectedTaskDetail.value?.task_id) return;
  isLoadingStdout.value = true;
  stdoutError.value = null;
  stdoutContent.value = ''; // Clear previous
  try {
    const response = await api.getTaskStdout(selectedTaskDetail.value.task_id);
    stdoutContent.value = response.data || '(Empty)'; // Axios text response puts data in .data
  } catch (error) {
    console.error('Error fetching stdout:', error);
    // Use response.data for error message if available (FastAPI error detail)
    stdoutError.value = error.response?.data || error.message || 'Failed to fetch stdout.';
    stdoutContent.value = `Error loading log: ${stdoutError.value}`;
  } finally {
    isLoadingStdout.value = false;
  }
};

const fetchStderr = async () => {
  if (!selectedTaskDetail.value?.task_id) return;
  isLoadingStderr.value = true;
  stderrError.value = null;
  stderrContent.value = ''; // Clear previous
  try {
    const response = await api.getTaskStderr(selectedTaskDetail.value.task_id);
    stderrContent.value = response.data || '(Empty)';
  } catch (error) {
    console.error('Error fetching stderr:', error);
    stderrError.value = error.response?.data || error.message || 'Failed to fetch stderr.';
    stderrContent.value = `Error loading log: ${stderrError.value}`;
  } finally {
    isLoadingStderr.value = false;
  }
};

// --- Dialog and Form Handling ---
const openSubmitDialog = () => {
  fetchAvailableNodes();
  submitDialogVisible.value = true;
};

const resetForm = () => {
  if (taskFormRef.value) {
    taskFormRef.value.resetFields();
  }
  taskForm.arguments_text = '';
  taskForm.env_vars_text = '';
  taskForm.memory_limit_str = '';
  taskForm.use_private_network = false;
  taskForm.use_private_pid = false;
  taskForm.selectedTargets = [];
};

const handleTaskSubmit = async () => {
  if (!taskFormRef.value) return;
  await taskFormRef.value.validate((valid, fields) => {
    if (valid) {
      submitTaskApi(taskForm);
    } else {
      console.log('Form validation failed:', fields);
      ElMessage({ message: 'Please fill in all required fields correctly.', type: 'warning' });
    }
  });
};

// --- Detail Dialog Handling ---
const handleRowClick = (row) => {
  // Assuming the /tasks endpoint now provides enough detail
  // Alternatively, fetch fresh details: api.getTaskStatus(row.task_id).then(...)
  selectedTaskDetail.value = { ...row }; // Make a copy
  resetDetailView(); // Clear logs from previous view
  detailDialogVisible.value = true;
  fetchStdout(); // Fetch logs when opening
  fetchStderr();
};

const resetDetailView = () => {
  // Called when modal is closed or before opening a new one
  stdoutContent.value = '';
  stderrContent.value = '';
  isLoadingStdout.value = false;
  isLoadingStderr.value = false;
  stdoutError.value = null;
  stderrError.value = null;
};

// --- Kill Handling ---
const handleKill = (taskId) => {
  if (!taskId) return;
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
      ElMessage({ type: 'info', message: 'Kill action cancelled.' });
    });
};

// --- Lifecycle Hooks ---
onMounted(() => {
  fetchTasks(); // Initial fetch
  if (backendHasGetTasks.value) {
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
    // Directly use the datetime object if backend returns it, else parse ISO string
    const date = isoString instanceof Date ? isoString : new Date(isoString);
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }
    return date.toLocaleString();
  } catch (e) {
    return 'Invalid Date Format';
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
  const joined = args.join(' ');
  return joined.substring(0, 50) + (joined.length > 50 ? '...' : '');
};

const formatArgsTooltip = (args) => {
  if (!args || args.length === 0) return null;
  return args.join(' ');
};

const formatEnvVars = (envVars) => {
  if (!envVars || Object.keys(envVars).length === 0) return 'None';
  return Object.entries(envVars)
    .map(([key, value]) => `${key}=${value}`)
    .join('\n');
};

// Placeholder for max cores hint
const maxCoresHint = ref(32); // Default value
</script>

<style scoped>
.el-dialog {
  /* Might need adjustment depending on global styles */
  max-width: 90vw; /* Prevent excessive width on small screens */
}
.el-select--multiple .el-select__tags {
  /* Improve multi-select appearance */
  max-width: calc(100% - 30px); /* Prevent overflow */
}
.el-table {
  margin-top: 20px;
}
/* Make table rows clickable */
.task-table :deep(.el-table__row) {
  cursor: pointer;
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

/* Styles for Detail Modal */
.el-descriptions {
  margin-top: 10px;
}
/* Consistent code block styling */
.code-block {
  background-color: var(--el-fill-color-lighter);
  padding: 8px 12px;
  border-radius: 4px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 0.9em;
  color: var(--el-text-color-regular);
}
/* Specific styling for args/env block */
.el-descriptions .code-block {
  max-height: 150px; /* Limit height */
  overflow-y: auto;
}

.log-scrollbar {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  margin-top: 5px;
}
/* Specific styling for log content block */
.log-content {
  min-height: 250px;
  margin: 0;
  padding: 10px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.85em;
  color: var(--el-text-color-primary); /* Ensure readability */
  background-color: var(--el-bg-color-overlay); /* Match dialog bg */
  /* Remove max-height here, scrollbar handles it */
}
</style>
