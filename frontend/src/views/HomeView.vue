<template>
  <div>
    <h1 class="page-title">Cluster Overview</h1>

    <el-row :gutter="20">
      <!-- ===== LEFT COLUMN ===== -->
      <el-col :xs="24" :lg="12">
        <!-- Nodes Summary Card -->
        <el-card shadow="hover" class="info-card">
          <template #header>
            <div class="card-header">
              <span>Nodes</span>
              <el-button @click="triggerFetchHealth" :loading="isLoadingHealth" text size="small" :icon="RefreshRight" />
            </div>
          </template>
          <div v-loading="isLoadingHealth">
            <el-alert v-if="healthError" :title="healthError" type="error" show-icon :closable="false" class="info-alert" />
            <el-row :gutter="10" v-else-if="aggregatedHealthStats" class="stats-row">
              <el-col :span="12">
                <el-statistic title="Total Nodes" :value="aggregatedHealthStats.totalNodes" />
              </el-col>
              <el-col :span="12">
                <el-statistic title="Online Nodes" :value="aggregatedHealthStats.onlineNodes">
                  <template #suffix>
                    <el-tooltip
                      v-if="aggregatedHealthStats.totalNodes - aggregatedHealthStats.onlineNodes > 0"
                      effect="dark"
                      :content="`${aggregatedHealthStats.totalNodes - aggregatedHealthStats.onlineNodes} Offline`"
                      placement="top"
                    >
                      <el-icon style="margin-left: 4px; color: #e6a23c" :size="14"><Warning /></el-icon>
                    </el-tooltip>
                  </template>
                </el-statistic>
              </el-col>
            </el-row>
            <div v-else class="placeholder">Loading...</div>
          </div>
        </el-card>

        <!-- Resources Card -->
        <el-card shadow="hover" class="info-card">
          <template #header>
            <div class="card-header">
              <span>Resources (Online Nodes)</span>
              <el-button
                @click="triggerCombinedFetch"
                :loading="isLoadingHealth || isLoadingTasks"
                text
                size="small"
                :icon="RefreshRight"
              />
            </div>
          </template>
          <div v-loading="isLoadingHealth || isLoadingTasks">
            <el-alert
              v-if="healthError || taskError"
              :title="healthError || taskError || 'Failed to load resource data'"
              type="error"
              show-icon
              :closable="false"
              class="info-alert"
            />
            <div v-else-if="aggregatedHealthStats">
              <!-- CPU Resources Section -->
              <div class="resource-section">
                <h4 class="resource-title">CPU Resources</h4>
                <el-row :gutter="10" align="middle" class="resource-row">
                  <el-col :span="8" class="resource-col">
                    <el-statistic title="Total Cores" :value="aggregatedHealthStats.totalCores" />
                  </el-col>
                  <el-col :span="8" class="resource-col">
                    <el-statistic title="Allocated Cores" :value="allocatedCores" />
                  </el-col>
                  <el-col :span="8" class="resource-col">
                    <div class="mini-chart-container">
                      <Chart
                        :size="{ width: 70, height: 70 }"
                        :data="clusterCpuGaugeData"
                        :margin="{ top: 2, bottom: 2, left: 2, right: 2 }"
                        :axis="{ primary: { hide: true }, secondary: { hide: true } }"
                        direction="circular"
                        :config="{ controlHover: false }"
                        class="gauge-chart"
                      >
                        <template #layers>
                          <Pie :dataKeys="['name', 'value']" :pie-style="miniGaugeStyle" :sort="'none'" />
                          <text x="50%" y="50%" dy="0.35em" text-anchor="middle" class="gauge-center-text mini-text">
                            {{ aggregatedHealthStats.avgCpuPercent.toFixed(0) }}%
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
                <el-row :gutter="10" align="middle" class="resource-row">
                  <el-col :span="8" class="resource-col">
                    <el-statistic
                      title="Total Memory"
                      :value="formatBytesToGB(aggregatedHealthStats.totalMemBytes)"
                      suffix=" GB"
                    />
                  </el-col>
                  <el-col :span="8" class="resource-col">
                    <el-statistic title="Allocated Memory" :value="formatBytesToGB(allocatedMemoryBytes)" suffix=" GB" />
                  </el-col>
                  <el-col :span="8" class="resource-col">
                    <div class="mini-chart-container">
                      <Chart
                        :size="{ width: 70, height: 70 }"
                        :data="clusterMemoryGaugeData"
                        :margin="{ top: 2, bottom: 2, left: 2, right: 2 }"
                        :axis="{ primary: { hide: true }, secondary: { hide: true } }"
                        direction="circular"
                        :config="{ controlHover: false }"
                        class="gauge-chart"
                      >
                        <template #layers>
                          <Pie :dataKeys="['name', 'value']" :pie-style="miniGaugeStyle" :sort="'none'" />
                          <text x="50%" y="50%" dy="0.35em" text-anchor="middle" class="gauge-center-text mini-text">
                            {{ aggregatedHealthStats.avgMemPercent.toFixed(0) }}%
                          </text>
                        </template>
                      </Chart>
                      <div class="mini-chart-label">Current Usage</div>
                    </div>
                  </el-col>
                </el-row>
              </div>
            </div>
            <div v-else class="placeholder">Loading...</div>
          </div>
        </el-card>

        <!-- Tasks Summary Card -->
        <el-card shadow="hover" class="info-card">
          <template #header>
            <div class="card-header">
              <span>Tasks Overview</span>
              <el-button @click="fetchTasks" :loading="isLoadingTasks" text size="small" :icon="RefreshRight" />
            </div>
          </template>
          <div v-loading="isLoadingTasks">
            <el-alert v-if="taskError" :title="taskError" type="error" show-icon :closable="false" class="info-alert" />
            <div v-else>
              <!-- Existing Task Stats Rows -->
              <el-row :gutter="10" class="stats-row">
                <el-col :span="12"><el-statistic title="Running Tasks" :value="runningTasksCount" /></el-col>
                <el-col :span="12"><el-statistic title="Pending/Assigning" :value="pendingTasksCount" /></el-col>
              </el-row>
              <el-row :gutter="10" style="margin-top: 15px" class="stats-row">
                <el-col :span="12"><el-statistic title="Completed Tasks" :value="completedTasksCount" /></el-col>
                <el-col :span="12">
                  <el-statistic title="Failed/Lost/Killed" :value="failedTasksCount">
                    <template #suffix v-if="failedTasksCount > 0">
                      <el-tooltip effect="dark" :content="`${failedTasksCount} Failed/Lost/Killed`" placement="top">
                        <el-icon style="margin-left: 4px; color: #f56c6c" :size="14"><CircleClose /></el-icon>
                      </el-tooltip>
                    </template>
                  </el-statistic>
                </el-col>
              </el-row>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- ===== RIGHT COLUMN ===== -->
      <el-col :xs="24" :lg="12">
        <!-- CPU Temp Chart -->
        <el-card shadow="hover" class="info-card">
          <template #header>Cluster CPU Temperature (℃)</template>
          <!-- Add ref="cpuChartContainerRef" here -->
          <div ref="cpuChartContainerRef" v-loading="isLoadingHealth" class="history-chart-container">
            <Chart
              v-if="!isLoadingHealth && !healthError && cpuHistory.length > 1"
              :size="{ width: cpuChartContainerWidth || 300, height: 315 }"
              :data="cpuTempHistoryData"
              :margin="{ top: 5, bottom: 5, left: 0, right: 10 }"
              :axis="temperatureAxis"
              direction="horizontal"
            >
              <template #layers>
                <Grid strokeDasharray="2,2" />
                <Line :dataKeys="['index', 'avg']" :lineStyle="{ stroke: 'var(--el-color-primary)' }" />
                <Line :dataKeys="['index', 'max']" :lineStyle="{ stroke: 'purple' }" />
              </template>
              <template #widgets>
                <Tooltip hideLine :config="{ index: { hide: true } }" />
              </template>
            </Chart>
            <el-alert v-else-if="healthError" :title="healthError" type="error" show-icon :closable="false" />
          </div>
        </el-card>

        <!-- CPU History Chart -->
        <el-card shadow="hover" class="info-card">
          <template #header>Cluster Resource Usage History (%)</template>
          <!-- Add ref="cpuChartContainerRef" here -->
          <div ref="cpuChartContainerRef" v-loading="isLoadingHealth" class="history-chart-container">
            <Chart
              v-if="!isLoadingHealth && !healthError && cpuHistory.length > 1"
              :size="{ width: cpuChartContainerWidth || 300, height: 315 }"
              :data="cpuHistoryData"
              :margin="{ top: 5, bottom: 5, left: 0, right: 10 }"
              :axis="historyAxis"
              direction="horizontal"
            >
              <template #layers>
                <Grid strokeDasharray="2,2" />
                <Line :dataKeys="['index', 'cpu']" :lineStyle="{ stroke: 'var(--el-color-primary)' }" />
                <Line :dataKeys="['index', 'mem']" :lineStyle="{ stroke: 'var(--el-color-success)' }" />
              </template>
              <template #widgets>
                <Tooltip hideLine :config="{ index: { hide: true } }" />
              </template>
            </Chart>
            <el-alert v-else-if="healthError" :title="healthError" type="error" show-icon :closable="false" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 35px">
      <el-col>
        <!-- About Card -->
        <el-card shadow="hover" class="info-card about-card">
          <template #header>
            <div class="card-header"><span>About HakuRiver</span></div>
          </template>
          <div>
            <p class="card-description">
              HakuRiver is a lightweight, self-hosted CPU cluster manager designed for distributing and managing command-line
              tasks across multiple compute nodes.
            </p>
            <p class="card-description">
              It focuses on simple CPU core allocation and basic job lifecycle management, suitable for small clusters or
              development environments.
            </p>
            <el-divider />
            <el-link type="primary" href="https://github.com/KohakuBlueleaf/HakuRiver" target="_blank" :icon="LinkIcon">
              GitHub Repository
            </el-link>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { Chart, Pie, Line, Grid, Tooltip } from 'vue3-charts';
import { useElementSize } from '@vueuse/core'; // Import useElementSize
import api from '@/services/api';
import { calculateAggregatedStats, formatBytesToGB } from '@/utils/health';
import { Warning, CircleClose, RefreshRight, Link as LinkIcon } from '@element-plus/icons-vue';

// --- Config ---
const MAX_HISTORY_POINTS = 32;
const HEALTH_POLLING_RATE_MS = 1000;
const TASK_POLLING_RATE_MS = 5000;

// --- Template Refs for Chart Containers ---
const cpuChartContainerRef = ref(null); // Ref for CPU chart container
const memoryChartContainerRef = ref(null); // Ref for Memory chart container

// --- Responsive Chart Width using VueUse ---
// Get the reactive width of the CPU chart container. Default to 300 if ref isn't attached yet.
const { width: cpuChartContainerWidth } = useElementSize(cpuChartContainerRef, { width: 300 }, { box: 'content-box' });
// Get the reactive width of the Memory chart container. Default to 300.
const { width: memoryChartContainerWidth } = useElementSize(memoryChartContainerRef, { width: 300 }, { box: 'content-box' });

// --- Health State & Polling ---
const aggregatedHealthStats = ref(null);
const isLoadingHealth = ref(false);
const healthError = ref(null);
let healthPollingInterval = null;
const tempHistory = ref({});
const cpuHistory = ref([]);
const memoryHistory = ref([]);
const historyIndex = ref(0);

const triggerFetchHealth = async (showLoading = false) => {
  if (isLoadingHealth.value && showLoading) return;
  isLoadingHealth.value = showLoading;
  healthError.value = null;
  try {
    const rawHealthData = await api.getHealth();
    const monitoringData = rawHealthData.data.aggregate;
    const newStats = rawHealthData.data.nodes;
    aggregatedHealthStats.value = calculateAggregatedStats(newStats[newStats.length - 1]);
    tempHistory.value = monitoringData.map((item, i) => ({ index: i, avg: item.maxAvgCpuTemp, max: item.maxMaxCpuTemp }));
    cpuHistory.value = monitoringData.map((item, i) => ({ index: i, cpu: item.avgCpuPercent, mem: item.avgMemPercent }));
  } catch (err) {
    console.error('Error fetching/processing cluster health:', err);
    healthError.value = err.response?.data?.detail || err.message || 'Failed to load health data.';
  } finally {
    isLoadingHealth.value = false;
  }
};

// --- Task State & Polling ---
const tasks = ref([]);
const isLoadingTasks = ref(false);
const taskError = ref(null);
let taskPollingInterval = null;
const backendHasGetTasks = ref(typeof api.getTasks === 'function'); // Check only once

const fetchTasks = async (showLoading = false) => {
  if (!backendHasGetTasks.value) {
    taskError.value = "Backend API '/tasks' endpoint not available.";
    isLoadingTasks.value = false;
    tasks.value = [];
    if (taskPollingInterval) {
      clearInterval(taskPollingInterval);
      taskPollingInterval = null; // Ensure it stops trying
    }
    return;
  }
  if (isLoadingTasks.value && showLoading) return;
  isLoadingTasks.value = showLoading;
  taskError.value = null;
  try {
    const response = await api.getTasks();
    tasks.value = response.data;
  } catch (err) {
    console.error('Error fetching tasks:', err);
    taskError.value = err.response?.data?.detail || err.message || 'Failed to load task data.';
    tasks.value = []; // Clear tasks on error
  } finally {
    isLoadingTasks.value = false;
  }
};

// --- Combined Fetch Trigger ---
const triggerCombinedFetch = (showLoading = false) => {
  triggerFetchHealth(showLoading); // Fetch health data
  // Only fetch tasks if the function exists and polling isn't disabled
  if (backendHasGetTasks.value && taskPollingInterval !== null) {
    fetchTasks(showLoading); // Fetch tasks
  } else if (!backendHasGetTasks.value) {
    // If API doesn't exist, ensure loading state is false and set error message
    isLoadingTasks.value = false;
    taskError.value = "Backend API '/tasks' endpoint not available.";
  }
};

// --- Computed Properties for Cards ---
const allocatedCores = computed(() => {
  return tasks.value
    .filter((t) => ['running', 'assigning'].includes(t.status))
    .reduce((sum, task) => sum + (task.required_cores || 0), 0);
});

const allocatedMemoryBytes = computed(() => {
  return tasks.value
    .filter((t) => ['running', 'assigning'].includes(t.status))
    .reduce((sum, task) => sum + (task.required_memory_bytes || 0), 0);
});

// --- Computed Properties for Charts ---
const clusterCpuGaugeData = computed(() => {
  const cpu = aggregatedHealthStats.value?.avgCpuPercent ?? 0;
  return [
    { name: 'Used', value: cpu },
    { name: 'Free', value: Math.max(0, 100 - cpu) },
  ];
});
const clusterMemoryGaugeData = computed(() => {
  const mem = aggregatedHealthStats.value?.avgMemPercent ?? 0;
  return [
    { name: 'Used', value: mem },
    { name: 'Free', value: Math.max(0, 100 - mem) },
  ];
});

const cpuTempHistoryData = computed(() => tempHistory.value);
const cpuHistoryData = computed(() => cpuHistory.value);
const memoryHistoryData = computed(() => memoryHistory.value);

// --- Chart Styles & Options ---
const miniGaugeStyle = ref({
  innerRadius: 25,
  padAngle: 0.0,
  colors: ['var(--el-color-primary)', 'var(--el-fill-color-light)'],
});

const historyAxis = ref({
  primary: { type: 'linear', hide: true },
  secondary: { type: 'linear', domain: [0, 100], ticks: 10, format: (val) => `${val}%` },
});
const temperatureAxis = ref({
  primary: { type: 'linear', hide: true },
  secondary: { type: 'linear', domain: [30, 80], ticks: 5, format: (val) => `${val}℃` },
});

// --- Lifecycle Hooks ---
onMounted(() => {
  triggerCombinedFetch(true); // Initial fetch

  healthPollingInterval = setInterval(() => triggerCombinedFetch(false), HEALTH_POLLING_RATE_MS);

  // Set up task polling only if the API exists
  if (backendHasGetTasks.value) {
    taskPollingInterval = setInterval(fetchTasks, TASK_POLLING_RATE_MS);
  } else {
    isLoadingTasks.value = false; // Ensure loading is false
    taskError.value = "Backend API '/tasks' endpoint not available."; // Set error message on mount
    tasks.value = []; // Ensure tasks are empty
  }
});

onUnmounted(() => {
  if (healthPollingInterval) clearInterval(healthPollingInterval);
  if (taskPollingInterval) clearInterval(taskPollingInterval);
  // VueUse handles ResizeObserver cleanup automatically
});

// --- Computed Properties for Task Counts ---
const runningTasksCount = computed(() => tasks.value.filter((t) => t.status === 'running').length);
const pendingTasksCount = computed(() => tasks.value.filter((t) => ['pending', 'assigning'].includes(t.status)).length);
const completedTasksCount = computed(() => tasks.value.filter((t) => t.status === 'completed').length);
const failedTasksCount = computed(
  () => tasks.value.filter((t) => ['failed', 'lost', 'killed', 'killed_oom'].includes(t.status)).length
);
</script>

<style scoped>
.page-title {
  margin-bottom: 25px;
  color: var(--el-text-color-primary);
  font-weight: 500;
}
.info-card {
  margin-bottom: 20px;
}
.info-card:last-child {
  margin-bottom: 0;
} /* Prevent extra margin on last card in col */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
.card-header .el-button {
  padding: 0;
  min-height: unset;
  margin-left: 10px;
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
}
.el-statistic .el-statistic__head {
  color: var(--el-text-color-secondary);
  font-size: 0.9em;
  margin-bottom: 2px;
}
.el-statistic .el-statistic__content {
  font-size: 1.6em;
  font-weight: 600;
  line-height: 1.1;
}
.info-alert {
  margin-bottom: 10px;
}
.placeholder {
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 20px 0;
}
.about-card p {
  margin-top: 0;
  margin-bottom: 1em;
  line-height: 1.6;
  font-size: 0.95em;
  color: var(--el-text-color-regular);
}
.about-card .el-divider {
  margin: 16px 0;
}
.el-statistic .el-statistic__suffix .el-icon {
  vertical-align: -2px;
}
.card-description {
  font-size: 0.8rem !important;
  color: var(--el-text-color-regular);
}

/* Resources Card Specific Styles */
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
.el-divider {
  margin: 10px 0 15px 0;
}
.mini-chart-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 90px; /* Ensure space */
}
.mini-chart-label {
  font-size: 0.8em;
  color: var(--el-text-color-disabled);
  margin-top: -5px; /* Adjust spacing */
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
} /* Smaller text for mini gauges */

/* History Chart Styles */
.history-chart-container {
  min-height: 210px; /* Height for chart area + padding */
  display: flex;
  justify-content: center;
  align-items: center;
}
/* Adjust chart default size if needed */
.history-chart-container :deep(.chart) {
  width: 100%; /* Make chart fill container */
}
</style>
