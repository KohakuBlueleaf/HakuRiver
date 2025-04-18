<template>
  <div>
    <h1>Compute Nodes</h1>

    <el-button @click="triggerCombinedFetch" :loading="isLoadingHealth || isLoadingTasks" type="primary" :icon="RefreshRight">
      Refresh Nodes & Tasks
    </el-button>

    <!-- Display errors prominently -->
    <el-alert v-if="healthError" :title="healthError" type="error" show-icon :closable="false" style="margin-top: 15px" />
    <el-alert
      v-if="taskError && !healthError"
      :title="taskError"
      type="warning"
      show-icon
      :closable="false"
      style="margin-top: 15px"
      description="Node health may be displayed, but task allocation data might be missing or inaccurate."
    />

    <el-row :gutter="20" style="margin-top: 20px">
      <!-- Left Column: Node List -->
      <el-col :xs="24" :md="16">
        <el-card shadow="never">
          <template #header>Node List</template>
          <el-table
            :data="nodesHealthList"
            style="width: 100%"
            v-loading="isLoadingHealth"
            empty-text="No nodes found or registered"
            @row-click="handleNodeSelect"
            highlight-current-row
            ref="nodeTableRef"
            :row-key="(row) => row.hostname"
          >
            <el-table-column prop="hostname" label="Hostname" sortable />
            <el-table-column prop="status" label="Status" sortable>
              <template #default="scope">
                <el-tag :type="getStatusType(scope.row.status)" size="small">
                  {{ scope.row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="NUMA Nodes" sortable :sort-method="sortByNumaNodes" width="125">
              <template #default="scope">
                {{ formatNumaSummary(scope.row.numa_topology) }}
              </template>
            </el-table-column>
            <el-table-column prop="total_cores" label="Cores" sortable />
            <el-table-column prop="cpu_percent" label="CPU %" sortable>
              <template #default="scope">
                {{ scope.row.cpu_percent?.toFixed(1) ?? 'N/A' }}
              </template>
            </el-table-column>
            <el-table-column prop="memory_percent" label="Mem %" sortable>
              <template #default="scope">
                {{ scope.row.memory_percent?.toFixed(1) ?? 'N/A' }}
              </template>
            </el-table-column>
            <el-table-column label="Allocated">
              <template #default="scope">
                <div class="allocated-col">
                  <span>C: {{ getNodeAllocatedCores(scope.row.hostname) }}</span>
                  <span>M: {{ formatBytesToGB(getNodeAllocatedMemory(scope.row.hostname)) }}G</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="last_heartbeat" label="Last Heartbeat" sortable>
              <template #default="scope">
                {{ formatDateTime(scope.row.last_heartbeat) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- Right Column: Selected Node Details & Resources -->
      <el-col :xs="24" :md="8">
        <el-card shadow="never" v-if="selectedNodeData" class="details-card">
          <template #header>Details: {{ selectedNodeData.hostname }}</template>

          <!-- Loading overlay for the details section -->
          <div v-loading="isLoadingTasks || isLoadingHealth">
            <!-- Static Node Info -->
            <el-descriptions :column="1" border size="small" class="node-static-info">
              <el-descriptions-item label="Status">
                <el-tag :type="getStatusType(selectedNodeData.status)" size="small">{{ selectedNodeData.status }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="URL">{{ selectedNodeData.url }}</el-descriptions-item>
              <el-descriptions-item label="Last Heartbeat">{{
                formatDateTime(selectedNodeData.last_heartbeat)
              }}</el-descriptions-item>
            </el-descriptions>

            <!-- Display task error specifically for this card if relevant -->
            <el-alert
              v-if="taskError && selectedNodeData"
              title="Task Allocation Data Unavailable"
              type="warning"
              show-icon
              :closable="false"
              class="info-alert"
              style="margin-top: 15px"
            />

            <!-- Dynamic Resources Section (Mimics HomeView) -->
            <div v-else class="node-resources">
              <!-- CPU Resources Section -->
              <div class="resource-section">
                <h4 class="resource-title">CPU Resources</h4>
                <el-row :gutter="5" align="middle" class="resource-row">
                  <el-col :span="8" class="resource-col">
                    <el-statistic title="Total Cores" :value="selectedNodeData.total_cores" />
                  </el-col>
                  <el-col :span="8" class="resource-col">
                    <el-statistic title="Allocated" :value="selectedNodeAllocatedCores" />
                  </el-col>
                  <el-col :span="8" class="resource-col">
                    <div class="mini-chart-container">
                      <Chart
                        :size="{ width: 70, height: 70 }"
                        :data="selectedNodeCpuGaugeData"
                        :margin="{ top: 2, bottom: 2, left: 2, right: 2 }"
                        :axis="{ primary: { hide: true }, secondary: { hide: true } }"
                        direction="circular"
                        :config="{ controlHover: false }"
                        class="gauge-chart"
                      >
                        <template #layers>
                          <Pie :dataKeys="['name', 'value']" :pie-style="miniGaugeStyle" :sort="'none'" />
                          <text x="50%" y="50%" dy="0.35em" text-anchor="middle" class="gauge-center-text mini-text">
                            {{ (selectedNodeData.cpu_percent ?? 0).toFixed(0) }}%
                          </text>
                        </template>
                      </Chart>
                      <div class="mini-chart-label">Current Usage</div>
                    </div>
                  </el-col>
                </el-row>
              </div>
              <el-divider />
              <!-- Memory Resources Section -->
              <div class="resource-section">
                <h4 class="resource-title">Memory Resources</h4>
                <el-row :gutter="5" align="middle" class="resource-row">
                  <el-col :span="8" class="resource-col">
                    <el-statistic title="Total" :value="formatBytesToGB(selectedNodeData.memory_total_bytes)" suffix=" GB" />
                  </el-col>
                  <el-col :span="8" class="resource-col">
                    <el-statistic title="Allocated" :value="formatBytesToGB(selectedNodeAllocatedMemoryBytes)" suffix=" GB" />
                  </el-col>
                  <el-col :span="8" class="resource-col">
                    <div class="mini-chart-container">
                      <Chart
                        :size="{ width: 70, height: 70 }"
                        :data="selectedNodeMemoryGaugeData"
                        :margin="{ top: 2, bottom: 2, left: 2, right: 2 }"
                        :axis="{ primary: { hide: true }, secondary: { hide: true } }"
                        direction="circular"
                        :config="{ controlHover: false }"
                        class="gauge-chart"
                      >
                        <template #layers>
                          <Pie :dataKeys="['name', 'value']" :pie-style="miniGaugeStyle" :sort="'none'" />
                          <text x="50%" y="50%" dy="0.35em" text-anchor="middle" class="gauge-center-text mini-text">
                            {{ (selectedNodeData.memory_percent ?? 0).toFixed(0) }}%
                          </text>
                        </template>
                      </Chart>
                      <div class="mini-chart-label">Current Usage</div>
                    </div>
                  </el-col>
                </el-row>
              </div>
            </div>

            <el-divider />
            <div class="numa-section">
              <h4 class="resource-title">NUMA Topology</h4>
              <div v-if="selectedNodeData.numa_topology && Object.keys(selectedNodeData.numa_topology).length > 0">
                <el-descriptions
                  :column="1"
                  border
                  size="small"
                  v-for="(numaInfo, numaId) in sortedNumaTopology"
                  :key="numaId"
                  style="margin-bottom: 8px"
                >
                  <template #title>NUMA Node {{ numaId }}</template>
                  <el-descriptions-item label="CPU Cores">
                    <span class="code-like">{{ numaInfo.cores?.join(', ') || 'N/A' }}</span>
                  </el-descriptions-item>
                  <el-descriptions-item label="Memory">
                    {{ formatBytesForNuma(numaInfo.memory_bytes) }}
                  </el-descriptions-item>
                  <!-- Optional: Add allocated resources per NUMA node later -->
                  <!-- <el-descriptions-item label="Allocated Cores">{{ getAllocatedCoresForNuma(numaId) }}</el-descriptions-item> -->
                </el-descriptions>
              </div>
              <el-empty v-else description="No NUMA topology reported by this node." :image-size="60" />
            </div>
          </div>
        </el-card>
        <el-card shadow="never" v-else class="details-card placeholder-card">
          <div class="placeholder-text">Select a node from the list to view details and resource allocation.</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { Chart, Pie } from 'vue3-charts'; // Use Pie for gauge
import { RefreshRight } from '@element-plus/icons-vue'; // Import icon
import api from '@/services/api'; // Import api service
import { fetchHealthData, getNodeHealth, formatBytesToGB, formatDateTime, getStatusType } from '@/utils/health';

// --- Component State ---
const nodesHealthList = ref([]);
const tasks = ref([]); // Add state for tasks
const isLoadingHealth = ref(false);
const isLoadingTasks = ref(false); // Add loading state for tasks
const healthError = ref(null);
const taskError = ref(null); // Add error state for tasks
const selectedHostname = ref(null);
const nodeTableRef = ref(null); // Ref for the table
let healthPollingInterval = null;
let taskPollingInterval = null; // Add interval for tasks
const HEALTH_POLLING_RATE_MS = 5000; // Keep health polling separate maybe
const TASK_POLLING_RATE_MS = 8000; // Task polling rate

// Check if tasks API endpoint exists
const backendHasGetTasks = ref(typeof api.getTasks === 'function');

// --- Fetch Logic ---
const triggerFetchHealth = async (showLoading = true) => {
  if (isLoadingHealth.value && showLoading) return; // Prevent overlap if manually triggered
  if (showLoading) isLoadingHealth.value = true;
  healthError.value = null; // Clear previous health error
  try {
    const newHealthData = await fetchHealthData();
    nodesHealthList.value = newHealthData;
    // If selected node disappeared, deselect it
    if (selectedHostname.value && !getNodeHealth(newHealthData, selectedHostname.value)) {
      selectedHostname.value = null;
    }
  } catch (err) {
    console.error('Error fetching nodes health list:', err);
    healthError.value = err.response?.data?.detail || err.message || 'Failed to load node health data.';
    nodesHealthList.value = []; // Clear list on error
    selectedHostname.value = null; // Deselect on error
  } finally {
    if (showLoading) isLoadingHealth.value = false;
  }
};

const fetchTasks = async (showLoading = true) => {
  if (!backendHasGetTasks.value) {
    taskError.value = "Backend API '/tasks' endpoint not available.";
    isLoadingTasks.value = false;
    tasks.value = [];
    if (taskPollingInterval) {
      clearInterval(taskPollingInterval);
      taskPollingInterval = null;
    }
    return;
  }
  if (isLoadingTasks.value && showLoading) return;
  if (showLoading) isLoadingTasks.value = true;
  taskError.value = null; // Clear previous task error
  try {
    const response = await api.getTasks();
    tasks.value = response.data;
  } catch (err) {
    console.error('Error fetching tasks:', err);
    taskError.value = err.response?.data?.detail || err.message || 'Failed to load task data.';
    tasks.value = []; // Clear tasks on error
  } finally {
    if (showLoading) isLoadingTasks.value = false;
  }
};

// Combined fetch trigger
const triggerCombinedFetch = () => {
  // Use showLoading=true for manual refresh button
  triggerFetchHealth(true);
  if (backendHasGetTasks.value) {
    fetchTasks(true);
  }
};

// --- Computed Properties ---

// Currently selected node's raw health data
const selectedNodeData = computed(() => {
  return getNodeHealth(nodesHealthList.value, selectedHostname.value);
});

// Calculate allocated cores for the *selected* node
const selectedNodeAllocatedCores = computed(() => {
  if (!selectedNodeData.value || !tasks.value || tasks.value.length === 0) {
    return 0;
  }
  return tasks.value
    .filter(
      (t) =>
        (t.status === 'running' || t.status === 'assigning') && t.assigned_node_hostname === selectedNodeData.value.hostname
    )
    .reduce((sum, task) => sum + (task.required_cores || 0), 0);
});

// Calculate allocated memory for the *selected* node
const selectedNodeAllocatedMemoryBytes = computed(() => {
  if (!selectedNodeData.value || !tasks.value || tasks.value.length === 0) {
    return 0;
  }
  return tasks.value
    .filter(
      (t) =>
        (t.status === 'running' || t.status === 'assigning') && t.assigned_node_hostname === selectedNodeData.value.hostname
    )
    .reduce((sum, task) => sum + (task.required_memory_bytes || 0), 0);
});

// Function to get allocated cores for *any* node (used in table)
const getNodeAllocatedCores = (hostname) => {
  if (!hostname || !tasks.value || tasks.value.length === 0) return 0;
  return tasks.value
    .filter((t) => (t.status === 'running' || t.status === 'assigning') && t.assigned_node_hostname === hostname)
    .reduce((sum, task) => sum + (task.required_cores || 0), 0);
};

// Function to get allocated memory for *any* node (used in table)
const getNodeAllocatedMemory = (hostname) => {
  if (!hostname || !tasks.value || tasks.value.length === 0) return 0;
  return tasks.value
    .filter((t) => (t.status === 'running' || t.status === 'assigning') && t.assigned_node_hostname === hostname)
    .reduce((sum, task) => sum + (task.required_memory_bytes || 0), 0);
};

// Gauge data for selected node CPU %
const selectedNodeCpuGaugeData = computed(() => {
  const cpu = selectedNodeData.value?.cpu_percent ?? 0;
  return [
    { name: 'Used', value: cpu },
    { name: 'Free', value: Math.max(0, 100 - cpu) },
  ];
});

// Gauge data for selected node Memory %
const selectedNodeMemoryGaugeData = computed(() => {
  const mem = selectedNodeData.value?.memory_percent ?? 0;
  return [
    { name: 'Used', value: mem },
    { name: 'Free', value: Math.max(0, 100 - mem) },
  ];
});

const sortedNumaTopology = computed(() => {
  if (!selectedNodeData.value?.numa_topology) return {};
  // Sort by NUMA ID (key) numerically
  const sortedKeys = Object.keys(selectedNodeData.value.numa_topology).sort((a, b) => parseInt(a) - parseInt(b));
  const sorted = {};
  for (const key of sortedKeys) {
    sorted[key] = selectedNodeData.value.numa_topology[key];
  }
  return sorted;
});

// --- Chart Style ---
const miniGaugeStyle = ref({
  innerRadius: 25, // Use smaller radius like in HomeView
  padAngle: 0.0,
  colors: ['var(--el-color-primary)', 'var(--el-fill-color-light)'], // Used / Free
});

// --- Event Handlers ---
const handleNodeSelect = (row) => {
  if (row && row.hostname) {
    selectedHostname.value = row.hostname;
  }
};

// --- Watchers ---
// Watch for changes in the selected hostname to potentially update table selection styling
watch(selectedHostname, (newHostname) => {
  if (nodeTableRef.value) {
    const row = nodesHealthList.value.find((node) => node.hostname === newHostname);
    nodeTableRef.value.setCurrentRow(row);
  }
});

const formatNumaSummary = (topology) => {
  if (topology && typeof topology === 'object' && Object.keys(topology).length > 0) {
    const count = Object.keys(topology).length;
    return `${count} Node${count > 1 ? 's' : ''}`;
  }
  return 'N/A';
};
const sortByNumaNodes = (rowA, rowB) => {
  const countA = Object.keys(rowA.numa_topology || {}).length;
  const countB = Object.keys(rowB.numa_topology || {}).length;
  return countA - countB;
};
const formatBytesForNuma = (bytes) => {
  if (bytes === null || bytes === undefined) return 'N/A';
  if (bytes < 1024) return `${bytes} B`; // Show bytes if less than 1 KiB
  // Use the imported GiB formatter for consistency
  return `${formatBytesToGB(bytes)} GiB`;
};

// --- Lifecycle Hooks ---
onMounted(() => {
  // Initial fetch without showing loading indicators for polling fetches later
  triggerFetchHealth(true);
  if (backendHasGetTasks.value) {
    fetchTasks(true);
  } else {
    isLoadingTasks.value = false;
    taskError.value = "Backend API '/tasks' endpoint not available.";
    tasks.value = [];
  }

  // Set up polling, fetch without showing loading indicators
  healthPollingInterval = setInterval(() => triggerFetchHealth(false), HEALTH_POLLING_RATE_MS);
  if (backendHasGetTasks.value) {
    taskPollingInterval = setInterval(() => fetchTasks(false), TASK_POLLING_RATE_MS);
  }
});

onUnmounted(() => {
  if (healthPollingInterval) clearInterval(healthPollingInterval);
  if (taskPollingInterval) clearInterval(taskPollingInterval);
});
</script>

<style scoped>
/* Reusing styles from HomeView where applicable */
.info-card {
  margin-bottom: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
.stats-row,
.resource-row {
  text-align: center;
}
.resource-col {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  padding: 0 2px !important; /* Reduce padding for tighter fit */
}
.el-statistic .el-statistic__head {
  color: var(--el-text-color-secondary);
  font-size: 0.8em;
  margin-bottom: 2px;
  white-space: nowrap;
} /* smaller font */
.el-statistic .el-statistic__content {
  font-size: 1.3em;
  font-weight: 600;
  line-height: 1.1;
} /* smaller font */
.info-alert {
  margin-bottom: 10px;
}
.el-divider {
  margin: 10px 0 15px 0;
}
.mini-chart-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 90px;
}
.mini-chart-label {
  font-size: 0.8em;
  color: var(--el-text-color-disabled);
  margin-top: -5px;
}
.gauge-chart {
  position: relative;
}
.gauge-center-text {
  font-weight: bold;
  fill: var(--el-text-color-primary);
}
.mini-text {
  font-size: 0.7rem;
}

/* --- Styles specific to NodesView --- */
.el-table {
  margin-top: 0;
} /* Removed default top margin */
.el-alert {
  margin-top: 15px;
}
.details-card {
  min-height: 400px; /* Adjust as needed */
}
.placeholder-card {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-secondary);
  text-align: center;
}
.placeholder-text {
  padding: 20px;
}
.node-static-info {
  margin-bottom: 15px;
} /* Space between static info and resources */
.resource-section {
  margin-bottom: 10px;
}
.resource-title {
  font-size: 1em;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
  text-align: center;
}

.el-table :deep(.el-table__row) {
  cursor: pointer;
}
.el-table :deep(.el-table__cell) {
  padding: 6px 0;
} /* Reduce cell padding */

/* Style for the allocated column in the table */
.allocated-col {
  display: flex;
  flex-direction: column;
  font-size: 0.8em;
  line-height: 1.3;
  color: var(--el-text-color-secondary);
}
.allocated-col span {
  white-space: nowrap;
}

.numa-section { margin-top: 15px; }
.numa-section .resource-title { margin-bottom: 10px; } /* Reuse resource title style */
.numa-section .el-descriptions { background-color: var(--el-fill-color-lighter); } /* Slightly different background for distinction */
.numa-section .el-descriptions__title { font-size: 0.9em; font-weight: 600; } /* Smaller title for NUMA node */
.numa-section .code-like { /* Style for core list */
    font-family: monospace;
    background-color: var(--el-color-info-light-9);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 0.9em;
}
/* Ensure empty state is centered */
.numa-section .el-empty { padding: 10px 0; }
</style>
