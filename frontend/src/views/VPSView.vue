<!-- frontend/src/views/VPSView.vue -->
<template>
  <div>
    <h1>Active VPS Tasks</h1>

    <!-- Submit VPS Task Button -->
    <el-button type="primary" @click="openSubmitDialog" :icon="Plus"> Submit New VPS Task </el-button>

    <el-button @click="fetchVpsTasks" :loading="isLoadingTasks" type="primary" :icon="RefreshRight">
      Refresh Active VPS List
    </el-button>

    <!-- Display errors prominently -->
    <el-alert
      v-if="taskError"
      :title="taskError"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 15px; margin-bottom: 15px;"
    />

    <!-- Task Table -->
    <el-table
      :data="tasks"
      style="width: 100%"
      v-loading="isLoadingTasks"
      empty-text="No active VPS tasks found or backend endpoint missing"
      class="vps-task-table"
    >
      <el-table-column prop="task_id" label="Task ID" sortable width="170" />
      <el-table-column prop="status" label="Status" sortable width="120">
        <template #default="scope">
          <el-tag :type="getTaskStatusType(scope.row.status)">
            {{ scope.row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="assigned_node" label="Assigned Node" sortable width="150" />
      <el-table-column prop="target_numa_node_id" label="Target NUMA" sortable width="140">
        <template #default="scope">{{ scope.row.target_numa_node_id ?? 'Node Wide' }}</template>
      </el-table-column>
      <el-table-column label="Required Resources" width="160">
         <template #default="scope">
            C: {{ scope.row.required_cores ?? 'N/A' }}<br/>
            M: {{ formatBytesForDisplay(scope.row.required_memory_bytes) }}<br/>
            GPUs: {{ formatRequiredGpus(scope.row.required_gpus) }}
         </template>
      </el-table-column>
      <el-table-column prop="submitted_at" label="Submitted" sortable width="120">
        <template #default="scope">{{ formatDateTime(scope.row.submitted_at) }}</template>
      </el-table-column>
      <el-table-column prop="started_at" label="Started" sortable width="120">
        <template #default="scope">{{ formatDateTime(scope.row.started_at) }}</template>
      </el-table-column>
       <el-table-column label="SSH Port" width="100">
        <template #default="scope">
           <span v-if="scope.row.status === 'running' && scope.row.ssh_port">{{ scope.row.ssh_port }}</span>
           <span v-else>-</span>
        </template>
       </el-table-column>
      <el-table-column label="Actions" fixed="right" width="180">
        <template #default="scope">
          <div class="action-buttons">
            <!-- Pause/Resume -->
            <el-button
              :type="scope.row.status === 'paused' ? 'success' : 'warning'"
              size="small"
              @click.stop="handlePauseResume(scope.row.task_id, scope.row.status)"
              :disabled="!isPauseResumeable(scope.row.status)"
              :loading="actionLoading[scope.row.task_id]?.[pauseOrResume(scope.row.status)]"
            >
              {{ pauseOrResume(scope.row.status) }}
            </el-button>
            <!-- Kill -->
            <el-button
              type="danger"
              size="small"
              @click.stop="handleKill(scope.row.task_id)"
              :disabled="!isKillable(scope.row.status)"
              :loading="actionLoading[scope.row.task_id]?.kill"
            >
              Kill
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- Submit VPS Task Dialog -->
    <el-dialog
      v-model="submitDialogVisible"
      title="Submit New VPS Task"
      width="600px"
      :close-on-click-modal="false"
      @closed="resetForm"
      top="5vh"
      draggable
    >
      <el-form
        ref="vpsFormRef"
        :model="vpsForm"
        :rules="vpsFormRules"
        label-position="top"
        @submit.prevent="handleVpsSubmit"
      >
        <!-- Public Key Input -->
        <el-form-item label="SSH Public Key (.pub)" prop="public_key_string">
            <el-input
              v-model="vpsForm.public_key_string"
              type="textarea"
              :rows="2"
              placeholder="Paste your public key here, OR upload the .pub file below"
              :disabled="hasUploadedFile"
            />
             <el-upload
                ref="uploadRef"
                :auto-upload="false"
                :on-change="handleFileChange"
                :on-remove="handleFileRemove"
                :limit="1"
                accept=".pub, .txt"
                style="width: 100%;"
             >
                <template #trigger>
                   <el-button type="info" size="small">Select File</el-button>
                </template>
                <template #tip>
                   <el-text size="small" type="info" style="margin-left: 10px;">Upload your public key file (e.g., ~/.ssh/id_rsa.pub)</el-text>
                </template>
             </el-upload>
        </el-form-item>


        <!-- Resource Requirements Row -->
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="Required CPU Cores" prop="required_cores">
              <el-input-number v-model="vpsForm.required_cores" :min="0" controls-position="right" style="width: 100%" />
               <el-text size="small" type="info">0 means auto-select based on available resources.</el-text>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Memory Limit (Optional)" prop="memory_limit_str">
              <el-input v-model="vpsForm.memory_limit_str" placeholder="e.g., 512M, 4G" clearable>
                <template #append>Bytes/K/M/G</template>
              </el-input>
              <el-text size="small" type="info">Examples: 512M, 4G, 2048K. No suffix means bytes (1000-based units).</el-text>
            </el-form-item>
          </el-col>
        </el-row>

        <!-- Container Environment Selection -->
        <el-form-item label="Container Environment" prop="container_name">
          <el-select
            v-model="vpsForm.container_name"
            clearable
            placeholder="Select container tarball or use default"
            style="width: 100%"
            :loading="isLoadingContainerOptions"
            loading-text="Loading available containers..."
            no-data-text="No container tarballs found"
          >
             <el-option label="[Use Host Default]" :value="null" /> <!-- Use null for default -->
             <el-option label="[Systemd Fallback - NOT FOR VPS]" value="NULL" disabled /> <!-- Explicitly disabled -->
            <el-option
              v-for="containerName in availableContainerNames"
              :key="containerName"
              :label="containerName"
              :value="containerName"
            />
          </el-select>
          <el-text size="small" type="info"
            >Select the Docker environment tarball to use. VPS tasks *require* a Docker container environment. Selecting Host Default uses the tarball configured on the Host.</el-text
          >
        </el-form-item>

         <!-- GPU Feature Toggle -->
        <el-form-item label="Enable GPU Selection">
          <el-switch v-model="vpsForm.gpuFeatureEnabled" />
          <el-text size="small" type="info" style="margin-left: 10px">
            Toggle to select specific GPUs instead of a node/NUMA core. Requires Docker container environment.
          </el-text>
        </el-form-item>

        <!-- Conditional Target Selection (Node/NUMA or GPU) -->
        <!-- Node/NUMA Selector (Visible when GPU feature is OFF) -->
        <el-form-item v-if="!vpsForm.gpuFeatureEnabled" label="Target Node / NUMA Node" prop="selectedTarget">
          <el-select
            v-model="vpsForm.selectedTarget"
            filterable
            clearable
            placeholder="Select a single target or leave blank for auto"
            style="width: 100%"
            :loading="isLoadingNodes"
            loading-text="Loading available nodes..."
            no-data-text="No online nodes found or failed to load"
          >
            <el-option label="[Auto Select]" :value="null" /> <!-- Use null for auto -->
            <el-option v-for="item in targetOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <el-text size="small" type="info">Select a single node or node:numa_id, or leave blank for auto-selection based on required cores.</el-text>
        </el-form-item>

        <!-- GPU Selection UI (Visible when GPU feature is ON) -->
        <el-form-item v-else label="Select Target GPUs (on a single node)">
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
                 <!-- Only allow selection on ONE node for VPS -->
                 <el-checkbox-group
                     v-model="vpsForm.selectedGpus[node.hostname]"
                     :disabled="isAnotherGpuNodeSelected(node.hostname)"
                 >
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
            >Select specific GPUs on *one* available node. Requires selecting a Docker container environment above.</el-text
          >
             <el-alert
                 v-if="vpsForm.gpuFeatureEnabled && !Object.values(vpsForm.selectedGpus).some(list => list && list.length > 0)"
                 title="Please select at least one GPU on a node."
                 type="warning"
                 show-icon
                 :closable="false"
                 style="margin-top: 5px;"
             />
        </el-form-item>


        <!-- Optional: Additional Mounts -->
        <el-form-item label="Additional Mounts (Optional)">
          <el-input
            v-model="vpsForm.additional_mounts_text"
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
          <el-switch v-model="vpsForm.privileged_override" />
          <el-text size="small" type="info" style="margin-left: 10px">
            Run the Docker container with the --privileged flag. Use with extreme caution. Overrides default configured on Host.
          </el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="submitDialogVisible = false">Cancel</el-button>
          <el-button type="primary" @click="handleVpsSubmit" :loading="isSubmitting"> Submit </el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed, watch } from 'vue';
import api from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import { RefreshRight, Plus } from '@element-plus/icons-vue'; // Import icons
// Reusing utility functions from TasksView/health utils
import { formatDateTime, formatBytesToGB } from '@/utils/health'; // Reuse date formatter

// --- State (Task List) ---
const tasks = ref([]); // This will hold the list of active VPS tasks
const isLoadingTasks = ref(false);
const taskError = ref(null);
let taskPollingInterval = null;
const TASK_POLLING_RATE_MS = 5000; // Poll tasks every 5 seconds

const actionLoading = reactive({}); // Track loading state for individual buttons { taskId: { action: boolean } }

// --- State (Submit Dialog) ---
const submitDialogVisible = ref(false);
const vpsFormRef = ref(null); // Reference to the ElForm component for validation
const uploadRef = ref(null); // Reference to the ElUpload component
const isSubmitting = ref(false);
const hasUploadedFile = ref(false); // State to track if a file has been uploaded

// State for GPU feature selection UI
const expandedGpuNodes = ref([]); // State for expanded collapse panels

const vpsForm = reactive({
  public_key_string: '', // Holds the key read from file or pasted
  required_cores: 0, // Default to 0 core for VPS (auto)
  memory_limit_str: '', // Input as string (e.g., "512M")
  selectedTarget: null, // Holds a single selected target string (hostname or hostname:numa_id), null for auto
  container_name: null, // Holds the selected container name (string), null for host default
  privileged_override: null, // Switch state for privileged flag (null = use host default)
  additional_mounts_text: '', // Input as string (one per line)

  // GPU Selection State (within form object for reactive coupling)
  gpuFeatureEnabled: false, // Toggle for GPU feature
  selectedGpus: {}, // { hostname: [gpu_id1, gpu_id2], ... } - Only one key should have non-empty array
});

// State for fetching form options (nodes, containers)
const availableNodes = ref([]); // Raw node data from API (including GPU info)
const isLoadingNodes = ref(false);
const nodesError = ref(null);

const availableContainerNames = ref([]); // Just the list of names (strings) from tarballs
const isLoadingContainerOptions = ref(false);
const containerOptionsError = ref(null);

// --- Helper Functions (Copied/Adapted) ---

const getTaskStatusType = (status) => {
  status = status?.toLowerCase();
  if (status === 'running') return ''; // Default blue
  if (status === 'pending' || status === 'assigning') return 'warning';
  if (status === 'failed' || status === 'lost' || status === 'killed' || status === 'killed_oom') return 'danger';
  if (status === 'paused') return 'info';
  if (status === 'completed') return 'success';
  return 'info';
};

const formatBytesForDisplay = (bytes) => {
  if (bytes === null || bytes === undefined) return 'N/A';
  if (bytes === 0) return '0 B';
  const k = 1000;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const formattedValue = parseFloat((bytes / Math.pow(k, i)).toFixed(1));
  return `${formattedValue} ${sizes[i]}`;
};

const formatRequiredGpus = (requiredGpus) => {
  if (!requiredGpus) return '-';
  if (!Array.isArray(requiredGpus) || requiredGpus.length === 0) return '-';
  try {
    const allGpuIds = requiredGpus.flat();
    if (allGpuIds.length === 0) return '-';
    return allGpuIds.join(', ');
  } catch (e) {
    console.error('Error formatting required_gpus:', e);
    return 'Invalid Data';
  }
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

const setActionLoading = (taskId, action, isLoading) => {
  if (!actionLoading[taskId]) {
    actionLoading[taskId] = reactive({});
  }
  actionLoading[taskId][action] = isLoading;
};

// Copied utility functions for memory parsing (from utils/cli.py)
const parseMemoryToBytes = (memStr) => {
    if (!memStr) return null;
    const str = memStr.trim().toUpperCase();
    const match = str.match(/^(\d+)([KMG]?)$/);
    if (!match) {
        throw new Error(
            `Invalid memory format: '${memStr}'. Use suffix K, M, or G (e.g., 512M, 4G).`
        );
    }

    const val = parseInt(match[1], 10);
    const unit = match[2];

    if (unit === "G") return val * 1000_000_000;
    if (unit === "M") return val * 1000_000;
    if (unit === "K") return val * 1000;
    return val; // Bytes
};

// Copied validation function for memory string (from TasksView)
const validateMemoryString = (rule, value, callback) => {
  if (!value) {
    callback(); // Optional field
    return;
  }
  const memRegex = /^\d+([kmg]?)$/i;
  if (!memRegex.test(value.trim())) {
    callback(new Error('Invalid format. Use numbers with optional K, M, G suffix (e.g., 512M, 4G)'));
  } else {
    try {
       const bytes = parseMemoryToBytes(value);
       if (bytes === null || isNaN(bytes) || bytes < 0) {
          callback(new Error('Failed to parse memory string.'));
       } else {
          callback();
       }
    } catch (e) {
       callback(new Error(`Failed to parse memory string: ${e.message}`));
    }
  }
};


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
          const memFormatted = numaInfo?.memory_bytes ? formatBytesForDisplay(numaInfo.memory_bytes) : '?'; // Use bytes formatter
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

// Helper for GPU selection UI: Disable checkboxes on other nodes if one node is already selected
const isAnotherGpuNodeSelected = computed(() => (currentNodeHostname) => {
    // Find the hostname that has selected GPUs
    const selectedNode = Object.keys(vpsForm.selectedGpus).find(
        hostname => vpsForm.selectedGpus[hostname] && vpsForm.selectedGpus[hostname].length > 0
    );
    // If no node is selected, or the current node is the selected one, enable checkboxes
    return selectedNode !== undefined && selectedNode !== currentNodeHostname;
});


// --- Validation Rules ---
const vpsFormRules = computed(() => {
  const rules = {
    public_key_string: [
        { required: true, message: 'SSH Public Key is required', trigger: ['blur', 'change'] },
         {
            pattern: /^ssh-(rsa|dss|ecdsa|ed25519|cert-v01@openssh\.com) .+/,
            message: 'Invalid SSH public key format',
            trigger: ['blur', 'change']
         }
    ],
    required_cores: [{ required: false, type: 'number', min: 0, message: 'Cores must be a non-negative number', trigger: 'blur' }],
    memory_limit_str: [{ validator: validateMemoryString, trigger: 'blur' }],
    // container_name is now only required to be non-NULL (not the empty string)
    container_name: [{
        validator: (rule, value, callback) => {
            if (value === 'NULL') {
                 callback(new Error('Systemd fallback is not supported for VPS tasks.'));
            } else {
                 // null is allowed (host default), empty string is not (unless it maps to null?)
                 // Let's assume null or a non-empty string container name is valid
                 // If the backend requires null for default, the UI should send null.
                 // The select component value="null" for host default is correctly null.
                 callback(); // If not 'NULL', it's valid (either null or a string)
            }
        },
        trigger: 'change'
    }],
    selectedTarget: [], // No required rule here, handled manually
  };

  return rules;
});

// --- API Functions ---

const fetchVpsTasks = async (showLoading = false) => {
  if (isLoadingTasks.value && showLoading) return;

  isLoadingTasks.value = showLoading;
  taskError.value = null;

  try {
    const response = await api.getVpsStatus();
    const data = response.data.map(task => ({
        ...task,
        status: task.status ?? 'unknown',
        required_cores: task.required_cores ?? null,
        required_memory_bytes: task.required_memory_bytes ?? null,
        required_gpus: task.required_gpus ?? [],
        assigned_node: task.assigned_node ?? 'N/A',
        target_numa_node_id: task.target_numa_node_id ?? null,
        ssh_port: task.ssh_port ?? null,
    }));
    tasks.value = data;

  } catch (err) {
    console.error('Error fetching VPS tasks:', err);
    taskError.value = err.response?.data?.detail || err.message || 'Failed to fetch active VPS task list.';
    tasks.value = [];
  } finally {
    isLoadingTasks.value = false;
  }
};

const fetchAvailableNodes = async () => {
  isLoadingNodes.value = true;
  nodesError.value = null;
  availableNodes.value = [];
  // Clear selectedGpus for nodes that might disappear or change status
  Object.keys(vpsForm.selectedGpus).forEach((hostname) => delete vpsForm.selectedGpus[hostname]);

  try {
    const response = await api.getNodes();
    availableNodes.value = response.data;

    // Initialize selectedGpus reactive arrays for *all* fetched nodes with GPUs
    availableNodes.value.forEach((node) => {
      if (node.gpu_info && node.gpu_info.length > 0) {
         if (!vpsForm.selectedGpus[node.hostname]) {
             vpsForm.selectedGpus[node.hostname] = reactive([]); // Use reactive() for direct keys
         }
      }
    });
     // Clear any nodes from selectedGpus that are no longer in availableNodes
     Object.keys(vpsForm.selectedGpus).forEach(hostname => {
         if (!availableNodes.value.find(node => node.hostname === hostname)) {
             delete vpsForm.selectedGpus[hostname];
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
    const response = await api.getTarballs();
    availableContainerNames.value = Object.keys(response.data).sort();
  } catch (error) {
    console.error('Error fetching available containers:', error);
    containerOptionsError.value = error.response?.data?.detail || error.message || 'Failed to load available containers.';
  } finally {
    isLoadingContainerOptions.value = false;
  }
};


const submitVpsTaskApi = async (formData) => {
  isSubmitting.value = true;
  try {
    let memory_bytes = null;
    if (formData.memory_limit_str) {
        try {
           memory_bytes = parseMemoryToBytes(formData.memory_limit_str);
        } catch (e) {
            // This should be caught by form validation, but included for safety
            ElMessage({ message: `Invalid Memory Limit: ${e.message}`, type: 'warning' });
            isSubmitting.value = false;
            return;
        }
    }

    const additionalMountsList = formData.additional_mounts_text
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l !== '');

    // --- Determine Target(s) and GPUs based on GPU Feature Flag ---
    let targets_payload = null; // Use null for auto-select
    let required_gpus_payload = null; // list of lists, or null

    if (formData.gpuFeatureEnabled) {
      // GPU targeting mode:
      let selectedNodeHostname = null;
      const selectedGpuIdsOnNode = [];

       for (const hostname in formData.selectedGpus) {
           if (formData.selectedGpus[hostname] && formData.selectedGpus[hostname].length > 0) {
               selectedNodeHostname = hostname; // Found the node
               selectedGpuIdsOnNode.push(...formData.selectedGpus[hostname]);
               // Don't break here, let the watcher or manual validation handle multi-select error
           }
       }

       // Manual validation already handled in handleVpsSubmit: ensures selectedNodeHostname exists and only one node has selections.
       if (selectedNodeHostname) {
           targets_payload = [selectedNodeHostname]; // Targets is a list with the selected hostname
           required_gpus_payload = [selectedGpuIdsOnNode.sort((a, b) => a - b)]; // required_gpus is a list containing the list of IDs
       } else {
           // If GPU feature is enabled but no GPUs selected on any node,
           // targets and required_gpus should be null (will likely fail validation later, but consistent payload)
           targets_payload = null;
           required_gpus_payload = null;
       }


    } else {
      // CPU/NUMA targeting mode:
      // If selectedTarget is null, targets_payload should be null for auto-select
      //If selectedTarget is a string, targets_payload should be [selectedTarget]
       if (formData.selectedTarget !== null) {
           targets_payload = [formData.selectedTarget];
       } else {
           targets_payload = null; // Auto-select
       }
       required_gpus_payload = null; // Explicitly null
    }

    // --- Construct Payload for API ---
    const payload = {
      task_type: 'vps',
      command: formData.public_key_string, // Public key goes into the command field
      arguments: [], // VPS has no arguments
      env_vars: {}, // VPS has no standard env vars (unless mounted?)
      required_cores: formData.required_cores, // Send 0 as null if auto
      required_memory_bytes: memory_bytes,
      targets: targets_payload, // null for auto, [target_string] for specific
      required_gpus: required_gpus_payload, // null or [[gpu_ids]]
      container_name: formData.container_name, // null for host default, string otherwise
      privileged: formData.privileged_override === null ? null : Boolean(formData.privileged_override),
      additional_mounts: additionalMountsList.length > 0 ? additionalMountsList : null,
    };

    console.log('Submitting VPS payload:', payload); // Debugging payload

    // --- Send to API ---
    // Use the general submit endpoint, it handles task_type 'vps'
    const response = await api.submitTask(payload);
    const responseData = response; // api.submitTask now returns response.data directly

    let message = 'VPS task submitted successfully.';
    let messageType = 'success';

    if (responseData.task_ids && responseData.task_ids.length > 0) {
        const taskId = responseData.task_ids[0];
        message += ` Task ID: ${taskId}`;
         if (responseData.runner_response && responseData.runner_response.ssh_port) {
             message += `, SSH Port: ${responseData.runner_response.ssh_port}`;
         } else {
             // If runner response isn't immediately available (e.g., node assigning),
             // user will need to check status later.
             message += `. Check status (VPS Tasks list) for SSH port.`;
         }

        if (responseData.failed_targets && responseData.failed_targets.length > 0) {
            // Should not happen for VPS with a single target, but defensive
             message += `. Target failed: ${responseData.failed_targets[0].reason}`;
             messageType = 'warning';
        }

        ElMessage({
            message: message,
            type: messageType,
            duration: 7000, // Longer duration to read Task ID/Port
            showClose: true, // Allow closing
        });

        submitDialogVisible.value = false;
        // Small delay to allow host/runner to process before refetching
        setTimeout(() => fetchVpsTasks(false), 1000);

    } else {
        // This case implies the Host accepted the request but didn't create a task (shouldn't happen if validation passed)
        // Or if responseData doesn't have task_ids as expected
         message = responseData.message || 'Submission failed: No task IDs received from Host.';
         messageType = 'error';
         ElMessage({ message: message, type: messageType, duration: 7000, showClose: true });
    }


  } catch (error) {
    console.error('Error submitting VPS task:', error);
    // Check if it's an HTTP error with a response body containing details
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({ message: `Failed to submit VPS task: ${errorDetail}`, type: 'error', duration: 7000, showClose: true });
  } finally {
    isSubmitting.value = false;
  }
};

const killTaskApi = async (taskId) => {
  console.log('Handling kill for task:', taskId); // Debug log
  if (!taskId) {
    console.warn('Kill called with no task ID.');
    return;
  }
  setActionLoading(taskId, 'kill', true);
  try {
    await api.killTask(taskId);
    ElMessage({ message: `Kill request sent for VPS task ${taskId}.`, type: 'info' });
    // Optimistic UI update - remove from list since getVpsStatus only shows active
    tasks.value = tasks.value.filter(t => t.task_id !== taskId);
  } catch (error) {
    console.error(`Error killing VPS task ${taskId}:`, error);
    const errorDetail = error.response?.data?.detail || error.response?.data || error.message || 'Unknown error';
    ElMessage({ message: `Failed to kill VPS task ${taskId}: ${errorDetail}`, type: 'error', duration: 5000 });
  } // finally omitted as task is removed
};

const pauseResumeTaskApi = async (taskId, action) => {
    console.log('Handling', action, 'for task:', taskId); // Debug log
    if (!taskId) {
        console.warn(action, 'called with no task ID.');
        return;
    }
    setActionLoading(taskId, action, true);
    try {
        await api.submitCommand({
            task_id: taskId,
            command: action,
        });
        ElMessage({ message: `VPS task ${taskId} ${action}d successfully.`, type: 'success' });

        const taskInList = tasks.value.find((t) => t.task_id === taskId);
        if (taskInList) taskInList.status = action === 'pause' ? 'paused' : 'running';

    } catch (error) {
        console.error(`Error ${action}ing VPS task ${taskId}:`, error);
        const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
        ElMessage({ message: `Failed to ${action} VPS task ${taskId}: ${errorDetail}`, type: 'error', duration: 5000 });
    } finally {
        setActionLoading(taskId, action, false);
    }
};

const handleKill = (taskId) => {
  if (!taskId) return;
  ElMessageBox.confirm(`Are you sure you want to kill VPS task ${taskId}? This will stop the container and cannot be undone.`, 'Confirm Kill VPS', {
    confirmButtonText: 'Kill VPS',
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
  const action = pauseOrResume(status); // 'pause' or 'resume'
  ElMessageBox.confirm(`Are you sure you want to ${action} VPS task ${taskId}?`, `Confirm ${action.charAt(0).toUpperCase() + action.slice(1)} VPS`, {
    confirmButtonText: `${action.charAt(0).toUpperCase() + action.slice(1)} VPS`,
    cancelButtonText: 'Cancel',
    type: 'warning', // Use warning type for both pause/resume confirmation
    draggable: true,
  })
    .then(() => {
      pauseResumeTaskApi(taskId, action);
    })
    .catch(() => {
      ElMessage({ type: 'info', message: `${action.charAt(0).toUpperCase() + action.slice(1)} action cancelled.` });
    });
};


// --- Dialog and Form Handling ---
const openSubmitDialog = () => {
  fetchAvailableNodes(); // Fetch nodes (includes GPU info)
  fetchAvailableContainers(); // Fetch container tarballs
  resetForm(); // Reset form state before opening
  submitDialogVisible.value = true;
};

const resetForm = () => {
  // ElForm's resetFields() only works reliably for fields with 'prop' attributes
  // and initial values that are explicitly defined in the reactive object when it's created.
  // For nullable/defaulted fields, manual reset is often better or required.

  // Manual reset for all fields
  vpsForm.public_key_string = '';
  vpsForm.required_cores = 0;
  vpsForm.memory_limit_str = '';
  vpsForm.selectedTarget = null;
  vpsForm.container_name = null;
  vpsForm.privileged_override = null;
  vpsForm.additional_mounts_text = '';

  vpsForm.gpuFeatureEnabled = false;
  // Clear selectedGpus object
  Object.keys(vpsForm.selectedGpus).forEach((hostname) => delete vpsForm.selectedGpus[hostname]);
   // Re-initialize empty reactive arrays for nodes that have GPUs (needed for checkbox-group v-model)
   // Do this AFTER fetching nodes if the list can change between dialog opens
   availableNodes.value.forEach((node) => {
     if (node.gpu_info && node.gpu_info.length > 0) {
       vpsForm.selectedGpus[node.hostname] = reactive([]);
     }
   });


  expandedGpuNodes.value = [];
  hasUploadedFile.value = false; // Reset file upload flag

  // Reset ElUpload component
  if (uploadRef.value) {
     uploadRef.value.clearFiles();
  }

  // Reset validation state after resetting fields
   if (vpsFormRef.value) {
      vpsFormRef.value.resetFields(); // This might only clear validation messages, not values for all fields
   }
};

const handleVpsSubmit = async () => {
  if (!vpsFormRef.value) return;

  isSubmitting.value = true; // Start loading

  // Validate main form fields
  let formValid = false;
  try {
     await vpsFormRef.value.validate();
     formValid = true;
  } catch (validationErrors) {
     console.log('Form validation failed:', validationErrors);
     // ElMessage is typically handled by the form validation component itself
     isSubmitting.value = false; // Stop loading on validation error
     return;
  }

  // Manual validation for public key (redundant if rule works, but safety)
  if (!vpsForm.public_key_string) {
      ElMessage({ message: 'SSH Public Key is required.', type: 'warning' });
      isSubmitting.value = false;
      return;
  }

  // Manual validation for target/GPU selection based on toggle state
  if (vpsForm.gpuFeatureEnabled) {
    // GPU targeting mode:
    let selectedNodeHostname = null;
    let totalGpusSelected = 0;
    for (const hostname in vpsForm.selectedGpus) {
      if (vpsForm.selectedGpus[hostname] && vpsForm.selectedGpus[hostname].length > 0) {
        // Check if the node is still in availableNodesWithGpus (status online + has GPUs)
        if (availableNodesWithGpus.value.find(node => node.hostname === hostname)) {
             selectedNodeHostname = hostname; // Valid node
             totalGpusSelected += vpsForm.selectedGpus[hostname].length;
        } else {
            // Should not happen if watch on selectedGpus cleans up, but defensive
            console.warn(`Selected GPUs on node ${hostname} which is no longer valid.`);
        }
      }
    }

    if (!selectedNodeHostname || totalGpusSelected === 0) {
      ElMessage({ message: 'Please select at least one GPU on a single, online node.', type: 'warning' });
      isSubmitting.value = false;
      return; // Stop submission
    }
     // The UI helper `isAnotherGpuNodeSelected` prevents selecting on multiple nodes,
     // but we should still validate just in case.
     const selectedNodeCount = Object.values(vpsForm.selectedGpus).filter(list => list && list.length > 0).length;
     if (selectedNodeCount > 1) {
         ElMessage({ message: 'VPS tasks can only target GPUs on a single node.', type: 'warning' });
         isSubmitting.value = false;
         return; // Stop submission
     }

  } else {
    // CPU/NUMA targeting mode:
    // selectedTarget can be null (auto) or a string (specific)
    // If it's a string, check if the target format is valid (hostname or hostname:numa_id)
    // We don't need to validate if the specific node/NUMA exists or is online here, backend does that.
    if (vpsForm.selectedTarget !== null) {
       const pattern = /^[a-zA-Z0-9.-]+(:\d+)?$/;
       if (!pattern.test(vpsForm.selectedTarget)) {
           ElMessage({ message: 'Invalid target format. Use "hostname" or "hostname:numa_id".', type: 'warning' });
           isSubmitting.value = false;
           return; // Stop submission
       }
    }
  }

  // Check Container Environment (required, but can be null for default)
   if (vpsForm.container_name === 'NULL') {
        ElMessage({
          message: 'Systemd fallback is not supported for VPS tasks. Please select a container environment or Host Default.',
          type: 'warning',
        });
        isSubmitting.value = false;
        return; // Stop submission
   }


  // If validation passes (automatic and manual)
  submitVpsTaskApi(vpsForm); // Call the API function with the form data
};


// --- File Upload Handlers ---
const handleFileChange = (uploadFile, fileList) => {
  // Limit ensures only one file is in the list.
  if (fileList.length > 0) {
      hasUploadedFile.value = true; // Set flag immediately when a file is added
  } else {
       hasUploadedFile.value = false;
       vpsForm.public_key_string = ''; // Clear textarea if no file is left
       // No need to read if fileList is empty
       if (vpsFormRef.value) {
          vpsFormRef.value.validateField('public_key_string');
       }
       return;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    vpsForm.public_key_string = e.target.result.trim();
     // Trigger validation manually after setting value from file
     if (vpsFormRef.value) {
         vpsFormRef.value.validateField('public_key_string');
     }
  };
  reader.onerror = (e) => {
     console.error('Error reading file:', e);
     ElMessage.error('Failed to read public key file.');
     // Clear file list and string on error
     if (uploadRef.value) uploadRef.value.clearFiles();
     vpsForm.public_key_string = '';
     hasUploadedFile.value = false; // Reset flag on error
     if (vpsFormRef.value) {
        vpsFormRef.value.validateField('public_key_string');
     }
  };

  // Read the first (and only) file in the list
  reader.readAsText(fileList[0].raw);
};

const handleFileRemove = (uploadFile, fileList) => {
  // fileList here contains the files *after* the remove operation
  if (fileList.length === 0) {
      hasUploadedFile.value = false;
      vpsForm.public_key_string = ''; // Clear the public key string when the last file is removed
      // Trigger validation manually after clearing value
      if (vpsFormRef.value) {
          vpsFormRef.value.validateField('public_key_string');
      }
  }
  // If fileList is still > 0 after remove (shouldn't happen with limit=1),
  // the handleFileChange for the remaining file(s) would re-populate the string.
};


// --- Lifecycle Hooks ---
onMounted(() => {
  fetchVpsTasks(true); // Initial fetch with loading indicator
  taskPollingInterval = setInterval(() => fetchVpsTasks(false), TASK_POLLING_RATE_MS); // Set up polling
});

onUnmounted(() => {
  if (taskPollingInterval) {
    clearInterval(taskPollingInterval);
  }
});

// Watcher to clear target selection when GPU feature is enabled, and vice-versa for GPU selections
watch(() => vpsForm.gpuFeatureEnabled, (newValue) => {
  if (newValue) {
    vpsForm.selectedTarget = null; // Clear non-GPU target
  } else {
    // Clear GPU selections when GPU feature is disabled
    Object.keys(vpsForm.selectedGpus).forEach((hostname) => {
         if (vpsForm.selectedGpus[hostname] && Array.isArray(vpsForm.selectedGpus[hostname])) {
             vpsForm.selectedGpus[hostname].length = 0; // Clear array in place
         }
     });
     expandedGpuNodes.value = []; // Collapse all panels
  }
});

// Watcher on vpsForm.selectedGpus to enforce single-node selection
watch(() => vpsForm.selectedGpus, (newVal, oldVal) => {
    if (!vpsForm.gpuFeatureEnabled) return; // Only applies when GPU feature is enabled

    const nodesWithSelections = Object.keys(newVal).filter(hostname => newVal[hostname] && newVal[hostname].length > 0);

    if (nodesWithSelections.length > 1) {
        ElMessage({
            message: 'Only one node can be selected for GPU allocation on a VPS task.',
            type: 'warning',
            duration: 3000
        });

        // Find the most recently touched node and clear others
        // This heuristic is tricky with deep watch on reactive objects.
        // A simpler UI approach might use radio buttons per node + checkboxes per GPU.
        // For current structure, let's just clear all but the first node found with selections.
         const firstNodeWithSelection = nodesWithSelections[0];
         nodesWithSelections.forEach(hostname => {
             if (hostname !== firstNodeWithSelection) {
                 if (newVal[hostname] && Array.isArray(newVal[hostname])) {
                    newVal[hostname].length = 0; // Clear array in place
                 }
             }
         });
    }
}, { deep: true }); // Watch deeply into selectedGpus object

</script>

<style scoped>
/* Reusing styles from TasksView where applicable */
.el-table {
  margin-top: 20px;
}

.el-alert {
  margin-bottom: 15px;
}

.action-buttons {
  display: flex;
  flex-direction: row; /* Arrange buttons horizontally */
  gap: 5px; /* Space between buttons */
  flex-wrap: wrap; /* Allow buttons to wrap if needed */
}

.action-buttons .el-button {
  /* width: 100%; /* Not full width for horizontal layout */
  margin: 0; /* Remove default margin */
}

/* Adjust table cell padding for better fit */
.el-table :deep(.el-table__cell) {
  padding: 6px 0 !important; /* Reduce cell padding */
}

/* Adjust Required Resources column layout */
.vps-task-table .el-table__cell div {
    line-height: 1.4; /* Improve readability for stacked lines */
}

/* Specific style for SSH Port to make it stand out slightly */
.el-table .el-table__cell:has(span) > div > span {
    font-weight: 500;
    color: var(--el-color-primary); /* Highlight the port number */
}


/* --- Submit Dialog Styles (Copied/Adapted from TasksView) --- */
.el-dialog {
  /* Might need adjustment depending on global styles */
  max-width: 90vw; /* Prevent excessive width on small screens */
}
.el-select--multiple .el-select__tags {
  /* Improve multi-select appearance */
  max-width: calc(100% - 30px); /* Prevent overflow */
}

.dialog-footer {
  text-align: right;
}

/* GPU Selection Styles */
.gpu-selection-container {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 10px;
  min-height: 100px; /* Ensure some height even when empty */
  max-height: 300px; /* Limit height and enable scroll */
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