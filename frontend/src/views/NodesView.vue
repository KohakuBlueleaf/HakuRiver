<template>
  <div>
    <h1>Compute Nodes</h1>

    <el-button @click="fetchNodes" :loading="isLoading" type="primary"> Refresh Nodes </el-button>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <!-- Use local state refs directly in the template -->
    <el-table :data="nodes" style="width: 100%" v-loading="isLoading" empty-text="No nodes found or registered">
      <el-table-column prop="hostname" label="Hostname" sortable />
      <el-table-column prop="status" label="Status" sortable>
        <template #default="scope">
          <el-tag :type="getStatusType(scope.row.status)">
            {{ scope.row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total_cores" label="Total Cores" sortable />
      <el-table-column prop="cores_in_use" label="Cores In Use" sortable />
      <el-table-column prop="available_cores" label="Available Cores" sortable />
      <el-table-column prop="url" label="Runner URL" />
      <el-table-column prop="last_heartbeat" label="Last Heartbeat" sortable>
        <template #default="scope">
          {{ formatDateTime(scope.row.last_heartbeat) }}
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import api from '@/services/api'; // Import the API service

// --- Local State ---
const nodes = ref([]); // Use ref for reactive array
const isLoading = ref(false);
const error = ref(null); // Store error messages
let pollingInterval = null; // To store the interval ID
const POLLING_RATE_MS = 5000; // Refresh every 5 seconds

// --- API Call Function ---
const fetchNodes = async () => {
  isLoading.value = true;
  error.value = null; // Clear previous errors
  try {
    const response = await api.getNodes();
    nodes.value = response.data; // Update local state
  } catch (err) {
    console.error('Error fetching nodes:', err);
    error.value = 'Failed to fetch node status. Check connection or backend.'; // Set error message
    nodes.value = []; // Clear data on error
  } finally {
    isLoading.value = false;
  }
};

// --- Lifecycle Hooks for Polling ---
onMounted(() => {
  fetchNodes(); // Fetch data initially when component mounts
  // Start polling
  pollingInterval = setInterval(() => {
    // Optional: Only poll if not already loading to prevent overlap
    if (!isLoading.value) {
      fetchNodes();
    }
  }, POLLING_RATE_MS);
});

onUnmounted(() => {
  // IMPORTANT: Clear the interval when the component is destroyed
  // to prevent memory leaks and unwanted background polling.
  if (pollingInterval) {
    clearInterval(pollingInterval);
  }
});

// --- Helper Functions (remain the same) ---
const getStatusType = (status) => {
  switch (status?.toLowerCase()) {
    case 'online':
      return 'success';
    case 'offline':
      return 'info';
    case 'lost':
      return 'danger';
    default:
      return 'warning';
  }
};

const formatDateTime = (isoString) => {
  if (!isoString) return 'N/A';
  try {
    return new Date(isoString).toLocaleString();
  } catch (e) {
    return 'Invalid Date';
  }
};
</script>

<style scoped>
.el-table {
  margin-top: 20px;
}
.el-alert {
  margin-top: 15px;
}
</style>
