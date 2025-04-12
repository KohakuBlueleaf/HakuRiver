<template>
  <div>
    <h1 class="page-title">Cluster Overview</h1>

    <el-row :gutter="20">
      <!-- Column 1: Stacked Summary Cards -->
      <el-col :xs="24" :sm="24" :md="12">
        <!-- Nodes Summary Card -->
        <el-card shadow="hover" class="info-card" style="margin-bottom: 20px">
          <template #header>
            <div class="card-header">
              <span>Nodes</span>
              <el-button @click="fetchNodes" :loading="isLoadingNodes" text size="small" :icon="RefreshRight" />
            </div>
          </template>
          <div v-loading="isLoadingNodes">
            <el-alert v-if="nodeError" :title="nodeError" type="error" show-icon :closable="false" class="info-alert" />
            <el-row :gutter="10" v-else class="stats-row">
              <el-col :span="12">
                <el-statistic title="Total Nodes" :value="totalNodesCount" />
              </el-col>
              <el-col :span="12">
                <el-statistic title="Online Nodes" :value="onlineNodesCount">
                  <template #suffix>
                    <el-tooltip
                      v-if="offlineNodesCount > 0"
                      effect="dark"
                      :content="`${offlineNodesCount} Offline`"
                      placement="top"
                    >
                      <el-icon style="margin-left: 4px; color: #e6a23c" :size="14">
                        <Warning />
                      </el-icon>
                    </el-tooltip>
                  </template>
                </el-statistic>
              </el-col>
            </el-row>
          </div>
        </el-card>

        <!-- Cores Summary Card -->
        <el-card shadow="hover" class="info-card" style="margin-bottom: 20px">
          <template #header>
            <div class="card-header">
              <span>CPU Cores (Online Nodes)</span>
              <el-button @click="fetchNodes" :loading="isLoadingNodes" text size="small" :icon="RefreshRight" />
            </div>
          </template>
          <div v-loading="isLoadingNodes">
            <el-alert
              v-if="nodeError"
              title="Node data unavailable"
              type="error"
              show-icon
              :closable="false"
              class="info-alert"
            />
            <el-row :gutter="10" v-else class="stats-row">
              <el-col :span="12">
                <el-statistic title="Total Cores" :value="totalOnlineCores" />
              </el-col>
              <el-col :span="12">
                <el-statistic title="Available Cores" :value="totalAvailableCores" />
              </el-col>
            </el-row>
          </div>
        </el-card>

        <!-- Tasks Summary Card -->
        <el-card shadow="hover" class="info-card" style="margin-bottom: 20px">
          <template #header>
            <div class="card-header">
              <span>Tasks Overview</span>
              <el-button @click="fetchTasks" :loading="isLoadingTasks" text size="small" :icon="RefreshRight" />
            </div>
          </template>
          <div v-loading="isLoadingTasks">
            <el-alert v-if="taskError" :title="taskError" type="error" show-icon :closable="false" class="info-alert" />
            <div v-else>
              <el-row :gutter="10" class="stats-row">
                <el-col :span="12">
                  <el-statistic title="Running Tasks" :value="runningTasksCount" />
                </el-col>
                <el-col :span="12">
                  <el-statistic title="Pending/Assigning" :value="pendingTasksCount" />
                </el-col>
              </el-row>
              <el-row :gutter="10" style="margin-top: 15px" class="stats-row">
                <el-col :span="12">
                  <el-statistic title="Completed Tasks" :value="completedTasksCount" />
                </el-col>
                <el-col :span="12">
                  <el-statistic title="Failed/Lost/Killed" :value="failedTasksCount">
                    <template #suffix v-if="failedTasksCount > 0">
                      <el-tooltip effect="dark" :content="`${failedTasksCount} Failed/Lost/Killed`" placement="top">
                        <el-icon style="margin-left: 4px; color: #f56c6c" :size="14">
                          <CircleClose />
                        </el-icon>
                      </el-tooltip>
                    </template>
                  </el-statistic>
                </el-col>
              </el-row>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- Column 2: About Card -->
      <el-col :xs="24" :sm="24" :md="12">
        <el-card shadow="hover" class="info-card about-card">
          <template #header>
            <div class="card-header">
              <span>About HakuRiver</span>
            </div>
          </template>
          <div>
            <p>
              HakuRiver is a lightweight, self-hosted CPU cluster manager designed for distributing and managing command-line
              tasks across multiple compute nodes.
            </p>
            <p>
              It focuses on simple CPU core allocation and basic job lifecycle management, suitable for small clusters or
              development environments.
            </p>
            <el-divider />
            <el-link type="primary" href="https://github.com/KohakuBlueleaf/HakuRiver" target="_blank" :icon="LinkIcon">
              <!-- Using el-link for better styling -->
              GitHub Repository
            </el-link>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Welcome Message Card REMOVED -->
    <!--
    <el-card shadow="never" style="margin-top: 20px">
      <p>Welcome to the HakuRiver dashboard. Use the sidebar navigation to manage compute nodes and tasks.</p>
    </el-card>
    -->
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import api from '@/services/api';
// Ensure necessary icons are imported
import { Warning, CircleClose, RefreshRight, Link as LinkIcon } from '@element-plus/icons-vue'; // Added RefreshRight and Link

// --- State for Nodes ---
const nodes = ref([]);
const isLoadingNodes = ref(false);
const nodeError = ref(null);
let nodePollingInterval = null;
const NODE_POLLING_RATE_MS = 8000;

// --- State for Tasks ---
const tasks = ref([]);
const isLoadingTasks = ref(false);
const taskError = ref(null);
let taskPollingInterval = null;
const TASK_POLLING_RATE_MS = 5000;
const backendHasGetTasks = ref(typeof api.getTasks === 'function');

// --- Fetch Nodes Function ---
const fetchNodes = async () => {
  isLoadingNodes.value = true;
  nodeError.value = null;
  try {
    const response = await api.getNodes();
    nodes.value = response.data;
  } catch (err) {
    console.error('Error fetching nodes:', err);
    nodeError.value = 'Failed to load node data.';
    nodes.value = [];
  } finally {
    isLoadingNodes.value = false;
  }
};

// --- Fetch Tasks Function ---
const fetchTasks = async () => {
  if (!backendHasGetTasks.value) {
    taskError.value = "Backend API '/tasks' endpoint not available for summary.";
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
    tasks.value = response.data;
  } catch (err) {
    console.error('Error fetching tasks:', err);
    taskError.value = 'Failed to load task data.';
    tasks.value = [];
  } finally {
    isLoadingTasks.value = false;
  }
};

// --- Computed Properties for Nodes ---
const totalNodesCount = computed(() => nodes.value.length);
const onlineNodes = computed(() => nodes.value.filter((n) => n.status === 'online'));
const onlineNodesCount = computed(() => onlineNodes.value.length);
const offlineNodesCount = computed(() => totalNodesCount.value - onlineNodesCount.value);
const totalOnlineCores = computed(() => {
  return onlineNodes.value.reduce((sum, node) => sum + (node.total_cores || 0), 0);
});
const totalAvailableCores = computed(() => {
  return onlineNodes.value.reduce((sum, node) => sum + (node.available_cores || 0), 0);
});

// --- Computed Properties for Tasks ---
const runningTasksCount = computed(() => {
  return tasks.value.filter((t) => t.status === 'running').length;
});
const pendingTasksCount = computed(() => {
  return tasks.value.filter((t) => ['pending', 'assigning'].includes(t.status)).length;
});
const completedTasksCount = computed(() => {
  return tasks.value.filter((t) => t.status === 'completed').length;
});
const failedTasksCount = computed(() => {
  return tasks.value.filter((t) => ['failed', 'lost', 'killed'].includes(t.status)).length;
});

// --- Lifecycle Hooks ---
onMounted(() => {
  fetchNodes();
  fetchTasks();
  nodePollingInterval = setInterval(fetchNodes, NODE_POLLING_RATE_MS);
  if (backendHasGetTasks.value) {
    taskPollingInterval = setInterval(fetchTasks, TASK_POLLING_RATE_MS);
  }
});

onUnmounted(() => {
  if (nodePollingInterval) clearInterval(nodePollingInterval);
  if (taskPollingInterval) clearInterval(taskPollingInterval);
});
</script>

<style scoped>
.page-title {
  margin-bottom: 25px;
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.info-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
/* Ensure refresh icon button doesn't take too much space */
.info-card .card-header .el-button {
  padding: 0; /* Remove padding for icon-only button */
  min-height: unset; /* Override default min height */
  margin-left: 10px; /* Add some space */
}

.info-card .el-statistic .el-statistic__head {
  color: var(--el-text-color-secondary);
  font-size: 0.9em;
}
.info-card .el-statistic .el-statistic__content {
  font-size: 1.8em;
  font-weight: 600;
}

.info-alert {
  margin-bottom: 10px;
}

.stats-row {
  text-align: center;
}

/* Ensure spacing for stacked cards on smaller screens */
.info-card {
  margin-bottom: 20px;
}
/* Override margin for last card in a column on small screens if needed */
@media (max-width: 991px) {
  /* Adjust breakpoint for md if necessary */
  .info-card:last-child {
    margin-bottom: 0;
  }
}

/* Style the About card */
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

/* Adjust suffix icon alignment */
.el-statistic .el-statistic__suffix .el-icon {
  vertical-align: -2px;
}
</style>
