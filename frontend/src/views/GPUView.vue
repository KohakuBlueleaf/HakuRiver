<!-- frontend/src/views/GPUView.vue -->
<template>
  <div>
    <h1>GPU Overview</h1>

    <el-button @click="fetchGpuData(true)" :loading="isLoading" type="primary" :icon="RefreshRight"> Refresh Data </el-button>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" style="margin-top: 15px" />

    <div v-loading="isLoading" style="margin-top: 20px; min-height: 200px">
      <div v-if="nodesWithGpus.length > 0">
        <el-card v-for="node in nodesWithGpus" :key="node.hostname" shadow="hover" class="node-gpu-card">
          <template #header>
            <div class="card-header">
              <span>GPU Details on Node: {{ node.hostname }}</span>
              <!-- Optional: Node status tag -->
              <el-tag size="small" :type="getStatusType(node.status)">{{ node.status }}</el-tag>
            </div>
          </template>

          <el-table
            :data="node.gpu_info"
            style="width: 100%"
            :show-header="true"
            empty-text="No GPU data available for this node."
            size="small"
          >
            <el-table-column prop="gpu_id" label="ID" width="40" />
            <el-table-column prop="name" label="Name" show-overflow-tooltip width="200" />
            <el-table-column prop="driver_version" label="Driver" show-overflow-tooltip width="100" />

            <!-- Utilization Columns with Progress -->
            <el-table-column label="GPU Util (%)">
              <template #default="scope">
                <el-progress
                  :percentage="scope.row.gpu_utilization ?? 0"
                  :stroke-width="20"
                  :text-inside="true"
                  :format="(p) => (scope.row.gpu_utilization ?? 'N/A') + '%'"
                  :status="getProgressStatus(scope.row.gpu_utilization)"
                />
              </template>
            </el-table-column>
            <el-table-column label="Mem Util (%)">
              <template #default="scope">
                <el-progress
                  :percentage="scope.row.mem_utilization ?? 0"
                  :stroke-width="20"
                  :text-inside="true"
                  :format="(p) => (scope.row.mem_utilization ?? 'N/A') + '%'"
                  :status="getProgressStatus(scope.row.mem_utilization)"
                />
              </template>
            </el-table-column>

            <!-- Memory Usage -->
            <el-table-column label="Memory (MiB)" width="140">
              <template #default="scope">
                {{ formatMemoryMiB(scope.row.memory_used_mib) }} / {{ formatMemoryMiB(scope.row.memory_total_mib) }}
              </template>
            </el-table-column>

            <!-- Temperature -->
            <el-table-column label="Temp (°C)" width="80">
              <template #default="scope">
                {{ scope.row.temperature ?? 'N/A' }}
              </template>
            </el-table-column>

            <!-- Power -->
            <el-table-column label="Power (W)" width="100">
              <template #default="scope">
                {{ formatPowerW(scope.row.power_usage_mw) }} / {{ formatPowerW(scope.row.power_limit_mw) }}
              </template>
            </el-table-column>

            <!-- Clocks (Optional, can add if needed) -->
            <el-table-column label="Clocks (MHz)" width="100">
              <template #default="scope">
                GPU: {{ scope.row.graphics_clock_mhz ?? 'N/A' }}<br />
                Mem: {{ scope.row.mem_clock_mhz ?? 'N/A' }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
      <el-empty v-else-if="!isLoading && !error" description="No nodes reporting GPU information found." :image-size="100" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import api from '@/services/api';
import { RefreshRight } from '@element-plus/icons-vue';
import { getStatusType } from '@/utils/health'; // Reuse node status tag helper

// --- State ---
const nodesWithGpus = ref([]); // Array of node objects, each with a gpu_info array
const isLoading = ref(false);
const error = ref(null);
let pollingInterval = null;
const POLLING_RATE_MS = 1000; // Poll every 5 seconds

// --- API Call ---
const fetchGpuData = async (showLoading = false) => {
  if (isLoading.value && showLoading) return; // Prevent manual refresh spam
  if (showLoading) isLoading.value = true;
  error.value = null; // Clear previous error

  try {
    // Fetch the full health data history
    const response = await api.getHealth();
    const allNodeSnapshots = response.data.nodes;

    // Get the latest snapshot (the last element in the outer array)
    if (!allNodeSnapshots || allNodeSnapshots.length === 0) {
      nodesWithGpus.value = [];
      error.value = 'No health data received from the host.';
      return;
    }
    const latestSnapshot = allNodeSnapshots.slice(-1)[0]; // This is an array of node objects

    // Filter nodes to find those reporting gpu_info in this latest snapshot
    const nodesWithGpusInfo = latestSnapshot.filter(
      (node) => node.status === 'online' && node.gpu_info && node.gpu_info.length > 0
    );

    // Structure the data for the template
    nodesWithGpus.value = nodesWithGpusInfo.map((node) => ({
      hostname: node.hostname,
      status: node.status, // Include status for the tag in card header
      gpu_info: node.gpu_info.map((gpu) => ({
        // Map raw gpu_info objects to a consistent structure
        gpu_id: gpu.gpu_id,
        name: gpu.name,
        driver_version: gpu.driver_version,
        pci_bus_id: gpu.pci_bus_id,
        gpu_utilization: gpu.gpu_utilization,
        graphics_clock_mhz: gpu.graphics_clock_mhz,
        mem_utilization: gpu.mem_utilization,
        mem_clock_mhz: gpu.mem_clock_mhz,
        memory_total_mib: gpu.memory_total_mib,
        memory_used_mib: gpu.memory_used_mib,
        memory_free_mib: gpu.memory_free_mib,
        temperature: gpu.temperature,
        fan_speed: gpu.fan_speed,
        power_usage_mw: gpu.power_usage_mw,
        power_limit_mw: gpu.power_limit_mw,
      })),
    }));
  } catch (err) {
    console.error('Error fetching GPU data:', err);
    nodesWithGpus.value = []; // Clear list on error
    error.value = err.response?.data?.detail || err.message || 'Failed to load GPU data.';
  } finally {
    if (showLoading) isLoading.value = false;
  }
};

// --- Helper Functions ---
const formatMemoryMiB = (mib) => {
  if (mib === null || mib === undefined) return 'N/A';
  return mib.toFixed(1); // Format to 1 decimal place for MiB
};

const formatPowerW = (mw) => {
  if (mw === null || mw === undefined) return 'N/A';
  return (mw / 1000).toFixed(1); // Convert mW to W and format
};

const getProgressStatus = (percent) => {
  if (percent === null || percent === undefined) return undefined; // Default style
  if (percent < 50) return 'success';
  if (percent < 80) return 'warning';
  return 'exception'; // Red for high usage
};

// --- Lifecycle Hooks ---
onMounted(() => {
  fetchGpuData(true); // Initial fetch with loading indicator
  pollingInterval = setInterval(() => fetchGpuData(false), POLLING_RATE_MS); // Poll periodically
});

onUnmounted(() => {
  if (pollingInterval) {
    clearInterval(pollingInterval);
  }
});
</script>

<style scoped>
.node-gpu-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

/* Optional: Style for the table within the card */
.el-table {
  margin-top: 10px; /* Space below card header */
}

/* Adjust progress bar style for better fit in table */
.el-table :deep(.el-progress) {
  width: 100%; /* Make progress bar fill the column */
  margin-top: 5px; /* Small space */
}

.el-table :deep(.el-table__empty-block) {
  min-height: 60px; /* Ensure some height for empty state */
}
</style>
