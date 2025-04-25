<!-- frontend/src/views/TasksView.vue -->
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
            <el-form-item label="Memory Limit (Optional)" prop="memory_limit_str">
              <el-input v-model="taskForm.memory_limit_str" placeholder="e.g., 512M, 4G" clearable>
                <template #append>Bytes/K/M/G</template>
              </el-input>
              <el-text size="small" type="info">Examples: 512M, 4G, 2048K. No suffix means bytes (1000-based units).</el-text>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="Container Environment" prop="container_name">
          <el-select
            v-model="taskForm.container_name"
            clearable
            placeholder="Select container or use default"
            style="width: 100%"
            :loading="isLoadingContainerOptions"
            loading-text="Loading available containers..."
            no-data-text="No container tarballs found"
          >
            <el-option label="[Use Host Default]" value="" />
            <!-- Empty string means use host default -->
            <el-option label="[Systemd Fallback - No Docker]" value="NULL" />
            <!-- Special value for systemd -->
            <el-option
              v-for="containerName in availableContainerNames"
              :key="containerName"
              :label="containerName"
              :value="containerName"
            />
          </el-select>
          <el-text size="small" type="info"
            >Select the Docker environment tarball to use. Default is configured on the Host. Select '[Systemd Fallback]' to run
            directly on the host/runner OS.</el-text
          >
        </el-form-item>

        <!-- GPU Feature Toggle -->
        <el-form-item label="Enable GPU Selection">
          <el-switch v-model="gpuFeatureEnabled" />
          <el-text size="small" type="info" style="margin-left: 10px">
            Toggle to select specific GPUs instead of nodes/NUMA cores. Requires Docker container environment.
          </el-text>
        </el-form-item>

        <!-- Conditional Target Selection -->
        <el-form-item v-if="!gpuFeatureEnabled" label="Target Node(s) / NUMA Node(s)" prop="selectedTargets">
          <el-select
            v-model="taskForm.selectedTargets"
            multiple
            filterable
            clearable
            placeholder="Select target(s)"
            style="width: 100%"
            :loading="isLoadingNodes"
            loading-text="Loading available nodes..."
            no-data-text="No online nodes found or failed to load"
          >
            <el-option v-for="item in targetOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-text size="small" type="info">Select one or more nodes. Suffix :N targets NUMA node N.</el-text>
        </el-form-item>

        <!-- GPU Selection UI (Conditional) -->
        <el-form-item v-else label="Select Target GPUs">
          <div v-loading="isLoadingNodes" class="gpu-selection-container">
            <el-alert
              v-if="nodesError"
              :title="nodesError"
              type="error"
              show-icon
              :closable="false"
              style="margin-bottom: 10px"
            />
            <el-collapse v-if="availableNodesWithGpus.length > 0" v-model="expandedGpuNodes">
              <el-collapse-item
                v-for="node in availableNodesWithGpus"
                :key="node.hostname"
                :title="`${node.hostname} (${node.gpu_info.length} GPUs)`"
                :name="node.hostname"
              >
                <el-checkbox-group v-model="selectedGpus[node.hostname]">
                  <el-checkbox v-for="gpu in node.gpu_info" :key="gpu.gpu_id" :label="gpu.gpu_id" border class="gpu-checkbox">
                    <div class="gpu-checkbox-content">
                      GPU {{ gpu.gpu_id }}: {{ gpu.name }}
                      <span class="gpu-stats">
                        GPU Util: {{ gpu.gpu_utilization ?? 'N/A' }}% | Mem Util: {{ gpu.mem_utilization ?? 'N/A' }}% | Temp:
                        {{ gpu.temperature ?? 'N/A' }}°C
                      </span>
                    </div>
                  </el-checkbox>
                </el-checkbox-group>
              </el-collapse-item>
            </el-collapse>
            <el-empty v-else description="No online nodes reporting GPU information." :image-size="60" />
          </div>
          <el-text size="small" type="info"
            >Select specific GPUs on available nodes. Requires selecting a Docker container environment above.</el-text
          >
          <el-alert
            v-if="taskForm.container_name === 'NULL' && gpuFeatureEnabled"
            title="GPU Selection requires a Docker Environment"
            type="warning"
            show-icon
            :closable="false"
            style="margin-top: 10px"
            description="GPU allocation via '--gpus' flag is only supported when running tasks inside a Docker container. Please select a container environment or disable GPU selection."
          />
        </el-form-item>

        <!-- Optional: Additional Mounts -->
        <el-form-item label="Additional Mounts (Optional)">
          <el-input
            v-model="taskForm.additional_mounts_text"
            type="textarea"
            :rows="2"
            placeholder="e.g., /host/path:/container/path"
          />
          <el-text size="small" type="info"
            >Each line is a mount point in 'host_path:container_path' format. Overrides default mounts configured on the
            Host.</el-text
          >
        </el-form-item>

        <!-- Optional: Privileged Mode -->
        <el-form-item label="Run Privileged (Optional)">
          <el-switch v-model="taskForm.privileged_override" />
          <el-text size="small" type="info" style="margin-left: 10px">
            Run the Docker container with the --privileged flag. Use with extreme caution. Overrides default configured on Host.
          </el-text>
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
      <el-table-column prop="task_id" label="Task ID" sortable width="170" />
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
      <el-table-column prop="required_cores" label="Cores" sortable width="90" />
      <!-- Display required_gpus -->
      <el-table-column label="Req GPUs" width="120">
        <template #default="scope">
          {{ formatRequiredGpus(scope.row.required_gpus) }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="Status" sortable width="100">
        <template #default="scope">
          <el-tag :type="getTaskStatusType(scope.row.status)">
            {{ scope.row.status }}
            <span v-if="scope.row.assignment_suspicion_count > 0" style="margin-left: 4px">(?)</span>
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="assigned_node" label="Assigned Node" sortable />
      <el-table-column prop="target_numa_node_id" label="Target NUMA" sortable width="140">
        <template #default="scope">{{ scope.row.target_numa_node_id ?? 'Node Wide' }}</template>
      </el-table-column>
      <el-table-column prop="submitted_at" label="Submitted" sortable width="120">
        <template #default="scope">{{ formatDateTime(scope.row.submitted_at) }}</template>
      </el-table-column>
      <!-- Removed Started/Completed from main table for brevity -->
      <el-table-column label="Actions" fixed="right" width="100">
        <template #default="scope">
          <div class="action-buttons">
            <!-- Stop propagation to prevent row click when clicking buttons -->
            <el-button
              :type="scope.row.status === 'paused' ? 'success' : 'warning'"
              size="small"
              @click.stop="handlePauseResume(scope.row.task_id, scope.row.status)"
              :disabled="!isPauseResumeable(scope.row.status)"
            >
              {{ pauseOrResume(scope.row.status) }}
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click.stop="handleKill(scope.row.task_id)"
              :disabled="!isKillable(scope.row.status)"
              v-loading="killingState[scope.row.task_id]"
            >
              Kill
            </el-button>
            <el-button type="primary" size="small" @click.stop="handleRowClick(scope.row)"> Details </el-button>
          </div>
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
          <el-descriptions-item label="Required GPUs">{{
            formatRequiredGpus(selectedTaskDetail.required_gpus)
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
          <el-descriptions-item label="Container Name">{{
            selectedTaskDetail.container_name || 'Host Default'
          }}</el-descriptions-item>

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
          <el-descriptions-item label="Required Memory">{{
            formatBytesForTable(selectedTaskDetail.required_memory_bytes)
          }}</el-descriptions-item>

          <el-descriptions-item label="Submitted At">{{
            formatDateTime(selectedTaskDetail.submitted_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="Stdout Path">{{ selectedTaskDetail.stdout_path || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="Started At">{{ formatDateTime(selectedTaskDetail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="Stderr Path">{{ selectedTaskDetail.stderr_path || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="Completed At">{{
            formatDateTime(selectedTaskDetail.completed_at)
          }}</el-descriptions-item>
          <el-descriptions-item label="Systemd Unit">{{ selectedTaskDetail.systemd_unit_name || 'N/A' }}</el-descriptions-item>
          <el-descriptions-item label="Error Message" :span="2">
            <pre class="code-block">{{ selectedTaskDetail.error_message || 'None' }}</pre>
          </el-descriptions-item>
        </el-descriptions>

        <el-divider />
        <el-row :gutter="20">
          <!-- Stdout Column - ADDED Click Listener -->
          <el-col :span="12">
            <div class="log-column-content">
              <h4 @click="openLogContentModal('stdout')" class="clickable-log-header">
                Standard Output
                <el-button
                  @click.stop="fetchStdout"
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
          <!-- Stderr Column - ADDED Click Listener -->
          <el-col :span="12">
            <div class="log-column-content">
              <h4 @click="openLogContentModal('stderr')" class="clickable-log-header">
                Standard Error
                <el-button
                  @click.stop="fetchStderr"
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

    <!-- --- NEW Log Content Modal --- -->
    <log-content-modal v-model="logContentModalVisible" :title="logContentModalTitle" :content="logContentModalContent" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed, watch } from 'vue';
import api from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import { RefreshRight } from '@element-plus/icons-vue'; // Import icon

// Import the new Log Content Modal component
import LogContentModal from '@/components/LogContentModal.vue';

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

// State for GPU feature
const gpuFeatureEnabled = ref(false);
const selectedGpus = reactive({}); // { hostname1: [0, 1], hostname2: [0], ... }

const taskForm = reactive({
  command: '',
  arguments_text: '',
  env_vars_text: '',
  required_cores: 0, // Default to 0 core
  memory_limit_str: '', // Input as string (e.g., "512M")
  selectedTargets: [], // Used when gpuFeatureEnabled is false
  container_name: '', // Holds the selected container name
  privileged_override: null, // Switch state for privileged flag (null = use host default)
  additional_mounts_text: '', // Input as string (one per line)
});

const availableNodes = ref([]); // Raw node data from API (including GPU info)
const isLoadingNodes = ref(false);
const nodesError = ref(null);

const availableContainerNames = ref([]); // Just the list of names (strings)
const isLoadingContainerOptions = ref(false);
const containerOptionsError = ref(null);

// --- Computed properties for form options ---

// Options for Node/NUMA selection (used when GPU feature is off)
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
        // Sort NUMA keys numerically
        const sortedNumaIds = Object.keys(node.numa_topology)
          .map(Number)
          .sort((a, b) => a - b);

        sortedNumaIds.forEach((numaId) => {
          const numaInfo = node.numa_topology[numaId];
          const coreCount = numaInfo?.cores?.length ?? '?';
          // Re-using formatBytesForTable for memory string, might need a more specific one
          const memFormatted = numaInfo?.memory_bytes ? formatBytesForTable(numaInfo.memory_bytes) : '?';
          options.push({
            // e.g., host1 / NUMA 0 (8 Cores, 64.0 GB)
            label: `  ${node.hostname} / NUMA ${numaId} (${coreCount} Cores, ${memFormatted})`,
            value: `${node.hostname}:${numaId}`, // Format: "hostname:numa_id"
          });
        });
      }
    }
  });
  return options;
});

// Filtered list of nodes that have GPU info for the GPU selection UI
const availableNodesWithGpus = computed(() => {
  if (!availableNodes.value) return [];
  return availableNodes.value.filter((node) => node.status === 'online' && node.gpu_info && node.gpu_info.length > 0);
});

const expandedGpuNodes = ref([]); // State for expanded collapse panels

// --- Validation Rules ---
const parseMemoryToBytes = (memStr) => {
  if (!memStr) return null;
  const str = memStr.trim().toUpperCase();
  // Adjusted regex to match Runner's 1000-based K, M, G
  const match = str.match(/^(\d+)([KMG]?)$/);
  if (!match) return null; // Invalid format already handled by validator

  const val = parseInt(match[1], 10);
  const unit = match.group(2);

  if (unit === 'G') return val * 1000 * 1000 * 1000;
  if (unit === 'M') return val * 1000 * 1000;
  if (unit === 'K') return val * 1000;
  return val; // Bytes
};

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
    // Check if parsing is successful
    if (parseMemoryToBytes(value) === null) {
      callback(new Error('Failed to parse memory string.'));
    } else {
      callback();
    }
  }
};

// Rules object structure adjusted for conditional validation
const taskFormRules = computed(() => {
  return {
    command: [{ required: true, message: 'Command is required', trigger: 'blur' }],
    required_cores: [{ required: false, trigger: 'blur' }], // Keep optional
    memory_limit_str: [{ validator: validateMemoryString, trigger: 'blur' }],
    // selectedTargets validation is only applied if gpuFeatureEnabled is FALSE
    selectedTargets: [
      {
        validator: (rule, value, callback) => {
          // If GPU feature is OFF, selectedTargets must be non-empty
          if (!gpuFeatureEnabled.value && (!value || value.length === 0)) {
            callback(new Error('Please select at least one target node/NUMA.'));
          } else {
            callback();
          }
        },
        trigger: 'change',
      },
    ],
    // GPU selection validation will be manual in handleTaskSubmit
  };
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

// --- State (Log Content Modal) ---
const logContentModalVisible = ref(false);
const logContentModalTitle = ref('');
const logContentModalContent = ref('');

// --- Helper Functions ---

const formatBytesForTable = (bytes) => {
  if (bytes === null || bytes === undefined) return 'N/A';
  if (bytes === 0) return '0 B';
  // Using 1000-based units for consistency with backend parsing
  const k = 1000;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
};

const formatRequiredGpus = (requiredGpus) => {
  if (!requiredGpus) return '-'; // Handle null/undefined directly
  // required_gpus is now a list of lists in the task object
  if (!Array.isArray(requiredGpus) || requiredGpus.length === 0) return '-';
  try {
    // Flatten the list of lists and join
    const allGpuIds = requiredGpus.flat();
    if (allGpuIds.length === 0) return '-';
    return allGpuIds.join(', ');
  } catch (e) {
    console.error('Error formatting required_gpus:', e);
    return 'Invalid Data';
  }
};

// --- API Functions ---

const fetchTasks = async (showLoading = false) => {
  if (!backendHasGetTasks.value) {
    taskError.value = "Backend API '/tasks' endpoint not implemented.";
    isLoadingTasks.value = false;
    tasks.value = [];
    if (taskPollingInterval) clearInterval(taskPollingInterval);
    return;
  }
  if (isLoadingTasks.value && showLoading) return; // Prevent overlap

  isLoadingTasks.value = showLoading;
  taskError.value = null;
  try {
    const response = await api.getTasks();
    tasks.value = response.data.map((task) => ({
      ...task,
      // Explicitly ensure default values if backend might omit them
      required_memory_bytes: task.required_memory_bytes ?? null,
      systemd_unit_name: task.systemd_unit_name ?? null,
      target_numa_node_id: task.target_numa_node_id ?? null,
      batch_id: task.batch_id ?? null,
      // Ensure required_gpus is included and default to an empty list of lists if null/undefined
      required_gpus: task.required_gpus ?? [],
    }));
  } catch (err) {
    console.error('Error fetching tasks:', err);
    taskError.value = err.response?.data?.detail || err.message || 'Failed to fetch task list.';
    tasks.value = [];
  } finally {
    isLoadingTasks.value = false;
  }
};

// Modified to fetch GPU info and filter for nodes with GPUs
const fetchAvailableNodes = async () => {
  isLoadingNodes.value = true;
  nodesError.value = null;
  availableNodes.value = []; // Clear previous list
  // Also clear GPU selections based on previous nodes
  Object.keys(selectedGpus).forEach((hostname) => delete selectedGpus[hostname]);
  // availableNodesWithGpus computed prop will filter for display

  try {
    const response = await api.getNodes(); // This now returns gpu_info from the backend
    availableNodes.value = response.data;

    // Initialize selectedGpus for nodes that have GPUs
    availableNodes.value.forEach((node) => {
      // Only initialize if node is online and reports GPU info
      if (node.status === 'online' && node.gpu_info && node.gpu_info.length > 0) {
        // Initialize with empty array for each potential GPU node
        // Use Vue's reactive `set` or just direct assignment if it's a new key
        selectedGpus[node.hostname] = selectedGpus[node.hostname] || [];
      }
    });
  } catch (error) {
    console.error('Error fetching nodes for target selection:', error);
    nodesError.value = error.response?.data?.detail || error.message || 'Failed to load available nodes.';
  } finally {
    isLoadingNodes.value = false;
  }
};

const fetchAvailableContainers = async () => {
  isLoadingContainerOptions.value = true;
  containerOptionsError.value = null;
  availableContainerNames.value = [];
  try {
    const response = await api.getTarballs(); // Assuming api.getTarballs exists
    // The response data is an object like { "containerName1": {...}, "containerName2": {...} }
    // Convert to an array of names
    availableContainerNames.value = Object.keys(response.data).sort((a, b) => {
      // Sort based on latest update time
      const timestampA = response.data[a]?.latest_timestamp ?? 0;
      const timestampB = response.data[b]?.latest_timestamp ?? 0;
      return timestampB - timestampA;
    });
  } catch (error) {
    console.error('Error fetching available containers:', error);
    containerOptionsError.value = error.response?.data?.detail || error.message || 'Failed to load available containers.';
  } finally {
    isLoadingContainerOptions.value = false;
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

    const additionalMountsList = formData.additional_mounts_text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l !== '');

    // --- Build Payload based on GPU Feature Flag ---
    const payload = {
      command: formData.command,
      arguments: argsList,
      env_vars: envDict,
      required_cores: formData.required_cores, // Always include core request
      container_name: formData.container_name === '' ? null : formData.container_name, // '' maps to null (Host default)
      // privileged_override is boolean or null; privileged should be boolean or null
      privileged: formData.privileged_override === null ? null : Boolean(formData.privileged_override),
      additional_mounts: additionalMountsList.length > 0 ? additionalMountsList : null,
    };

    if (gpuFeatureEnabled.value) {
      // GPU targeting mode:
      const taskTargets = [];
      const taskGpus = [];
      let totalGpusSelected = 0;

      // Iterate through nodes that *have* GPUs and check if any were selected
      availableNodesWithGpus.value.forEach((node) => {
        const selectedGpusOnNode = selectedGpus[node.hostname] || [];
        if (selectedGpusOnNode.length > 0) {
          taskTargets.push(node.hostname); // Target is just the hostname
          taskGpus.push(selectedGpusOnNode.sort((a, b) => a - b)); // Add array of selected GPU IDs (sorted)
          totalGpusSelected += selectedGpusOnNode.length;
        }
      });

      if (taskTargets.length === 0) {
        ElMessage({ message: 'Please select at least one GPU.', type: 'warning' });
        isSubmitting.value = false;
        return; // Stop submission
      }
      if (payload.container_name === 'NULL') {
        ElMessage({
          message: 'GPU selection requires a Docker environment. Please select a container or disable GPU selection.',
          type: 'warning',
        });
        isSubmitting.value = false;
        return; // Stop submission
      }

      payload.targets = taskTargets; // List of hostnames
      payload.required_gpus = taskGpus; // List of lists of GPU IDs
      // When GPU is enabled, cores/memory might be secondary or enforced via Docker
      // Keep user-specified cores/memory in payload if they provided them, otherwise leave as default/null
      if (formData.memory_limit_str) {
        payload.required_memory_bytes = parseMemoryToBytes(formData.memory_limit_str);
      } else {
        payload.required_memory_bytes = null;
      }
    } else {
      // CPU/NUMA targeting mode:
      if (!formData.selectedTargets || formData.selectedTargets.length === 0) {
        ElMessage({ message: 'Please select at least one target node/NUMA.', type: 'warning' });
        isSubmitting.value = false;
        return; // Stop submission
      }

      payload.targets = formData.selectedTargets; // Array of hostname or hostname:numa_id strings
      payload.required_gpus = null; // Explicitly null when not using GPU targeting
      if (formData.memory_limit_str) {
        payload.required_memory_bytes = parseMemoryToBytes(formData.memory_limit_str);
      } else {
        payload.required_memory_bytes = null;
      }
    }

    // --- Send to API ---
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
      fetchTasks(true); // Refresh list
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
  fetchAvailableNodes(); // Fetch nodes (now includes GPU info)
  fetchAvailableContainers(); // Fetch container tarballs
  submitDialogVisible.value = true;
};

const resetForm = () => {
  if (taskFormRef.value) {
    taskFormRef.value.resetFields();
  }
  // Manually reset fields not covered by resetFields (like textareas and new state)
  taskForm.arguments_text = '';
  taskForm.env_vars_text = '';
  taskForm.memory_limit_str = '';
  taskForm.selectedTargets = [];
  taskForm.container_name = '';
  taskForm.privileged_override = null; // Reset privileged override
  taskForm.additional_mounts_text = ''; // Reset mounts text

  gpuFeatureEnabled.value = false; // Reset GPU feature toggle
  // Reset selectedGpus object - clear all properties
  Object.keys(selectedGpus).forEach((hostname) => delete selectedGpus[hostname]);
  // Re-initialize for nodes currently online with GPUs (in case node list changed)
  availableNodes.value.forEach((node) => {
    if (node.status === 'online' && node.gpu_info && node.gpu_info.length > 0) {
      selectedGpus[node.hostname] = [];
    }
  });

  expandedGpuNodes.value = []; // Collapse all panels
};

const handleTaskSubmit = async () => {
  if (!taskFormRef.value) return;

  // Perform validation. Note: selectedTargets rule is conditional.
  let formValid = false;
  try {
    await taskFormRef.value.validate();
    formValid = true;
  } catch (validationErrors) {
    // Validation failed, errors are shown on fields by Element Plus
    console.log('Form validation failed:', validationErrors);
    ElMessage({ message: 'Please fill in all required fields correctly.', type: 'warning' });
    return;
  }

  // Manual validation for GPU selection if feature is enabled
  if (gpuFeatureEnabled.value) {
    let anyGpuSelected = false;
    for (const hostname in selectedGpus) {
      if (selectedGpus[hostname] && selectedGpus[hostname].length > 0) {
        anyGpuSelected = true;
        break;
      }
    }
    if (!anyGpuSelected) {
      ElMessage({ message: 'Please select at least one GPU.', type: 'warning' });
      isSubmitting.value = false;
      return; // Stop submission
    }
    if (taskForm.container_name === 'NULL' || taskForm.container_name === '') {
      ElMessage({
        message: 'GPU selection requires a Docker environment. Please select a container or disable GPU selection.',
        type: 'warning',
      });
      isSubmitting.value = false;
      return; // Stop submission
    }
  } else {
    // If GPU feature is off, ensure at least one standard target is selected (handled by selectedTargets rule)
    // If validation passed this point, the rule for selectedTargets must have succeeded.
  }

  // If validation passes (automatic and manual)
  submitTaskApi(taskForm); // Call the API function with the form data
};

// --- Detail Dialog Handling ---
const handleRowClick = (row) => {
  // Assuming the /tasks endpoint now provides enough detail
  // Alternatively, fetch fresh details: api.getTaskStatus(row.task_id).then(...)
  selectedTaskDetail.value = { ...row }; // Make a copy
  resetDetailView(); // Clear logs from previous view
  detailDialogVisible.value = true;
  // Logs are fetched automatically when the detail dialog opens
  fetchStdout();
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
  // Ensure log content modal is also closed if it's open
  logContentModalVisible.value = false;
};

// --- Log Content Modal Handling ---
const openLogContentModal = (logType) => {
  if (!selectedTaskDetail.value) return; // Should not happen if called from detail modal

  const taskId = selectedTaskDetail.value.task_id;
  if (logType === 'stdout') {
    logContentModalTitle.value = `Standard Output for Task ${taskId}`;
    logContentModalContent.value = stdoutContent.value; // Use already fetched content
  } else if (logType === 'stderr') {
    logContentModalTitle.value = `Standard Error for Task ${taskId}`;
    logContentModalContent.value = stderrContent.value; // Use already fetched content
  } else {
    return; // Invalid log type
  }
  logContentModalVisible.value = true;
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

const handlePauseResume = (taskId, status) => {
  if (!taskId) return;
  const command = pauseOrResume(status);
  ElMessageBox.confirm(`Are you sure you want to ${command} task ${taskId}?`, 'Confirm Pause/Resume', {
    confirmButtonText: `${command} Task`,
    cancelButtonText: 'Cancel',
    type: 'warning',
    draggable: true,
  })
    .then(() => {
      api
        .submitCommand({
          task_id: taskId,
          command: command,
        })
        .then(() => {
          ElMessage({ message: `Task ${taskId} ${command}ed successfully.`, type: 'success' });
          fetchTasks(true); // Refresh list
        })
        .catch((error) => {
          console.error(`Error ${command}ing task ${taskId}:`, error);
          const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
          ElMessage({ message: `Failed to ${command} task ${taskId}: ${errorDetail}`, type: 'error' });
        });
    })
    .catch(() => {
      ElMessage({ type: 'info', message: `${command} action cancelled.` });
    });
};

const pauseOrResume = (status) => {
  status = status?.toLowerCase();
  if (status === 'running') return 'pause';
  else return 'resume';
};

const isKillable = (status) => {
  status = status?.toLowerCase();
  return ['pending', 'assigning', 'running', 'paused'].includes(status);
};

const isPauseResumeable = (status) => {
  return ['running', 'paused'].includes(status?.toLowerCase());
};

// --- Watchers ---
// Watch for changes in gpuFeatureEnabled to potentially clear selections
watch(gpuFeatureEnabled, (newValue) => {
  if (newValue) {
    // Clearing non-GPU targets when GPU feature is enabled
    taskForm.selectedTargets = [];
  } else {
    // Clearing GPU selections when GPU feature is disabled
    Object.keys(selectedGpus).forEach((hostname) => (selectedGpus[hostname] = []));
    expandedGpuNodes.value = []; // Collapse all panels
  }
});

// --- Lifecycle Hooks ---
onMounted(() => {
  fetchTasks(); // Initial fetch
  if (backendHasGetTasks.value) {
    taskPollingInterval = setInterval(() => fetchTasks(false), TASK_POLLING_RATE_MS);
  }
});

onUnmounted(() => {
  if (taskPollingInterval) {
    clearInterval(taskPollingInterval);
  }
});

// --- General Helper Functions ---
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
  if (status === 'failed' || status === 'lost' || status === 'killed' || status === 'killed_oom') return 'danger';
  if (status === 'paused') return 'info';
  return 'info'; // Default for unknown states
};

const formatArgsPreview = (args) => {
  if (!args || args.length === 0) return '-';
  // Ensure it's an array before joining
  const argsArray = Array.isArray(args) ? args : [];
  const joined = argsArray.join(' ');
  return joined.substring(0, 50) + (joined.length > 50 ? '...' : '');
};

const formatArgsTooltip = (args) => {
  if (!args || args.length === 0) return null;
  // Ensure it's an array before joining
  const argsArray = Array.isArray(args) ? args : [];
  return argsArray.join(' ');
};

const formatEnvVars = (envVars) => {
  if (!envVars || Object.keys(envVars).length === 0) return 'None';
  // Ensure it's an object before iterating
  const envObject = typeof envVars === 'object' && envVars !== null && !Array.isArray(envVars) ? envVars : {};
  return Object.entries(envObject)
    .map(([key, value]) => `${key}=${value}`)
    .join('\n');
};

// Placeholder for max cores hint (not used in this version)
// const maxCoresHint = ref(32);
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
  word-break: break-word; /* Changed from break-all to break-word */
  font-size: 0.9em;
  color: var(--el-text-color-regular);
}
/* Specific styling for args/env block */
.el-descriptions .code-block {
  max-height: 150px; /* Limit height */
  overflow-y: auto;
}
.el-descriptions-item__container .el-descriptions-item__content {
  word-break: break-word; /* Also apply to non-pre blocks */
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

/* Make log headers clickable */
.clickable-log-header {
  cursor: pointer;
  display: flex; /* Align refresh button */
  align-items: center;
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: 5px; /* Space between buttons */
}
.action-buttons .el-button {
  width: 100%; /* Full width for buttons */
  margin: 0;
}

/* GPU Selection Styles */
.gpu-selection-container {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 10px;
  min-height: 100px; /* Ensure some height even when empty */
  max-height: 400px; /* Limit height and enable scroll */
  overflow-y: auto;
  width: 100%;
}
.el-collapse {
  border-top: none; /* Remove default top border */
  border-bottom: none; /* Remove default bottom border */
}
.el-collapse-item {
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.el-collapse-item__header {
  font-size: 0.9em;
  font-weight: 500;
  padding: 0 10px;
}
.el-collapse-item__content {
  padding: 10px;
}
.gpu-checkbox-content {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  font-size: 0.85em;
  line-height: 1.4;
}
.gpu-stats {
  font-size: 0.75em;
  color: var(--el-text-color-secondary);
}
.gpu-checkbox {
  margin-right: 10px !important; /* Add spacing between checkboxes */
  margin-bottom: 5px;
}
.el-checkbox.is-bordered.el-checkbox--small {
  padding: 8px 10px !important; /* Adjust padding for border+small */
}
</style>
