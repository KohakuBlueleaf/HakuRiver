<!-- src/views/DockerView.vue -->
<template>
  <div>
    <h1>Docker Management</h1>

    <el-tabs v-model="activeTab" class="docker-tabs">
      <!-- Host Containers Tab -->
      <el-tab-pane label="Host Containers" name="containers">
        <div class="tab-header">
          <el-button type="primary" @click="openCreateContainerModal"> Create New Container </el-button>
          <el-button @click="fetchContainers" :loading="isLoadingContainers" text size="small" :icon="RefreshRight">
            Refresh List
          </el-button>
        </div>

        <el-alert
          v-if="containerError"
          :title="containerError"
          type="error"
          show-icon
          :closable="false"
          style="margin-bottom: 15px"
        />

        <el-table
          :data="hostContainers"
          v-loading="isLoadingContainers"
          empty-text="No containers found on the Host"
          class="docker-table"
        >
          <el-table-column prop="name" label="Name" sortable width="200" />
          <el-table-column prop="image" label="Image" show-overflow-tooltip width="250" />
          <el-table-column prop="status" label="Status" sortable width="150">
            <template #default="scope">
              <el-tag :type="getContainerStatusType(scope.row.status)">
                {{ formatContainerStatus(scope.row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Actions" fixed="right">
            <template #default="scope">
              <div class="action-buttons">
                <el-button
                  size="small"
                  @click="handleStartContainer(scope.row)"
                  :disabled="formatContainerStatus(scope.row.status) !== 'Stopped'"
                  v-loading="actionLoading[scope.row.name]?.start"
                >
                  Start
                </el-button>
                <el-button
                  size="small"
                  @click="handleStopContainer(scope.row)"
                  :disabled="formatContainerStatus(scope.row.status) !== 'Running'"
                  v-loading="actionLoading[scope.row.name]?.stop"
                >
                  Stop
                </el-button>
                <el-button
                  size="small"
                  @click="handleCreateTarball(scope.row)"
                  :disabled="formatContainerStatus(scope.row.status) === 'Created'"
                  v-loading="actionLoading[scope.row.name]?.createTarball"
                >
                  Create Tar
                </el-button>
                <el-button
                  size="small"
                  @click="handleShell(scope.row)"
                  :disabled="formatContainerStatus(scope.row.status) !== 'Running'"
                  v-loading="actionLoading[scope.row.name]?.shell"
                >
                  Shell
                </el-button>
                <el-button
                  type="danger"
                  size="small"
                  @click="handleDeleteContainer(scope.row)"
                  v-loading="actionLoading[scope.row.name]?.delete"
                >
                  Delete
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Shared Tarballs Tab -->
      <el-tab-pane label="Shared Tarballs" name="tarballs">
        <div class="tab-header">
          <el-button @click="fetchTarballs" :loading="isLoadingTarballs" text size="small" :icon="RefreshRight">
            Refresh List
          </el-button>
        </div>
        <el-alert
          v-if="tarballError"
          :title="tarballError"
          type="error"
          show-icon
          :closable="false"
          style="margin-bottom: 15px"
        />
        <el-table
          :data="formattedTarballs"
          v-loading="isLoadingTarballs"
          empty-text="No HakuRiver tarballs found in shared storage"
          class="docker-table"
        >
          <el-table-column prop="name" label="Container Name" sortable />
          <el-table-column label="Latest Version (Timestamp)">
            <template #default="scope">
              {{ formatUnixTimestamp(scope.row.latest_timestamp) }}
            </template>
          </el-table-column>
          <el-table-column prop="latest_tarball" label="Latest Tarball File" show-overflow-tooltip />
          <!-- Optional: Expandable row for all versions -->
          <el-table-column type="expand">
            <template #default="props">
              <div style="padding: 0 50px">
                <h4>All Versions (Newest First):</h4>
                <ul style="margin: 10px 0; padding: 0">
                  <li
                    v-for="version in props.row.all_versions"
                    :key="version.timestamp"
                    style="margin-bottom: 5px; list-style: none"
                  >
                    {{ formatUnixTimestamp(version.timestamp) }}: {{ version.tarball }}
                    <el-button
                      type="danger"
                      size="small"
                      @click="handleDeleteTarball(props.row.name, version.timestamp)"
                      style="margin-left: 10px"
                      >Delete</el-button
                    >
                  </li>
                </ul>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="Actions" width="100" fixed="right">
            <template #default="scope">
              <!-- Delete Tarball Button (Backend endpoint needed) -->
              <el-tooltip content="Backend API needed to delete specific tarballs" placement="top">
                <el-button type="danger" size="small" disabled> Delete </el-button>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- Create Container Modal -->
    <el-dialog
      v-model="createModalVisible"
      title="Create New Host Container"
      width="400px"
      :close-on-click-modal="false"
      @closed="resetCreateForm"
      draggable
    >
      <el-form ref="createFormRef" :model="createForm" :rules="createFormRules" label-position="top">
        <el-form-item label="Docker Image Name" prop="image_name">
          <el-input v-model="createForm.image_name" placeholder="e.g., ubuntu:latest, python:3.11-slim" />
        </el-form-item>
        <el-form-item label="HakuRiver Container Name" prop="container_name">
          <el-input v-model="createForm.container_name" placeholder="e.g., my-python-env" />
          <el-text size="small" type="info">Used for tarball naming and task targeting.</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createModalVisible = false">Cancel</el-button>
          <el-button type="primary" @click="handleCreateSubmit" :loading="isCreatingContainer"> Create </el-button>
        </span>
      </template>
    </el-dialog>

    <!-- Terminal Modal (Implementation separate) -->
    <terminal-modal
      v-model="terminalModalVisible"
      :container-name="selectedContainerNameForShell"
      @closed="selectedContainerNameForShell = null"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue';
import api from '@/services/api';
import { ElMessage, ElMessageBox } from 'element-plus';
import { RefreshRight, Box } from '@element-plus/icons-vue'; // Import icons
import {
  formatContainerStatus,
  getContainerStatusType,
  formatUnixTimestamp,
  parseTimestampFromTarballFilename, // Unused but good practice to import
} from '@/utils/docker'; // Import new utils

// Import the TerminalModal component (assuming it exists)
import TerminalModal from '@/components/TerminalModal.vue'; // Adjust path as needed

// --- State ---
const activeTab = ref('containers'); // 'containers' or 'tarballs'

// Containers tab state
const hostContainers = ref([]);
const isLoadingContainers = ref(false);
const containerError = ref(null);

// Tarballs tab state
const sharedTarballs = ref({}); // { containerName: { latest_timestamp, latest_tarball, all_versions } }
const isLoadingTarballs = ref(false);
const tarballError = ref(null);

// Create Container Modal state
const createModalVisible = ref(false);
const createFormRef = ref(null);
const isCreatingContainer = ref(false);
const createForm = reactive({
  image_name: '',
  container_name: '',
});
const createFormRules = reactive({
  image_name: [{ required: true, message: 'Docker Image Name is required', trigger: 'blur' }],
  container_name: [{ required: true, message: 'HakuRiver Container Name is required', trigger: 'blur' }],
});

// Action loading state (for per-row buttons)
const actionLoading = reactive({}); // { containerName: { actionType: boolean } }

// Terminal Modal state
const terminalModalVisible = ref(false);
const selectedContainerNameForShell = ref(null);

// --- Computed Properties ---
const formattedTarballs = computed(() => {
  // Convert the object structure from the API into an array for the table
  return Object.entries(sharedTarballs.value)
    .map(([name, data]) => ({
      name,
      ...data,
    }))
    .sort((a, b) => {
      // Sort by container name alphabetically
      if (a.name < b.name) return -1;
      if (a.name > b.name) return 1;
      return 0;
    });
});

// --- API Calls ---
const fetchContainers = async () => {
  isLoadingContainers.value = true;
  containerError.value = null;
  hostContainers.value = [];
  try {
    const response = await api.getContainers();
    hostContainers.value = response.data;
  } catch (err) {
    console.error('Error fetching host containers:', err);
    containerError.value = err.response?.data?.detail || err.message || 'Failed to load host containers.';
  } finally {
    isLoadingContainers.value = false;
  }
};

const fetchTarballs = async () => {
  isLoadingTarballs.value = true;
  tarballError.value = null;
  sharedTarballs.value = {};
  try {
    const response = await api.getTarballs();
    sharedTarballs.value = response.data;
  } catch (err) {
    console.error('Error fetching shared tarballs:', err);
    tarballError.value = err.response?.data?.detail || err.message || 'Failed to load shared tarballs.';
  } finally {
    isLoadingTarballs.value = false;
  }
};

const createContainerApi = async (formData) => {
  isCreatingContainer.value = true;
  try {
    await api.createContainer(formData);
    ElMessage({ message: `Container '${formData.container_name}' created successfully.`, type: 'success' });
    createModalVisible.value = false;
    fetchContainers(); // Refresh list after creating
  } catch (error) {
    console.error('Error creating container:', error);
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({ message: `Failed to create container: ${errorDetail}`, type: 'error', duration: 5000 });
  } finally {
    isCreatingContainer.value = false;
  }
};

const deleteContainerApi = async (containerName) => {
  setActionLoading(containerName, 'delete', true);
  try {
    await api.deleteContainer(containerName);
    ElMessage({ message: `Container '${containerName}' deleted.`, type: 'success' });
    fetchContainers(); // Refresh list
  } catch (error) {
    console.error(`Error deleting container ${containerName}:`, error);
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({ message: `Failed to delete container '${containerName}': ${errorDetail}`, type: 'error', duration: 5000 });
  } finally {
    setActionLoading(containerName, 'delete', false);
  }
};

const stopContainerApi = async (containerName) => {
  setActionLoading(containerName, 'stop', true);
  try {
    await api.stopContainer(containerName);
    ElMessage({ message: `Container '${containerName}' stopped.`, type: 'success' });
    // Optimistic update or just refetch? Refetch is safer given potential status changes
    // Small delay might be needed for Docker status to update
    setTimeout(fetchContainers, 1000);
  } catch (error) {
    console.error(`Error stopping container ${containerName}:`, error);
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({ message: `Failed to stop container '${containerName}': ${errorDetail}`, type: 'error', duration: 5000 });
  } finally {
    setActionLoading(containerName, 'stop', false);
  }
};

const startContainerApi = async (containerName) => {
  setActionLoading(containerName, 'start', true);
  try {
    await api.startContainer(containerName);
    ElMessage({ message: `Container '${containerName}' started.`, type: 'success' });
    setTimeout(fetchContainers, 1000);
  } catch (error) {
    console.error(`Error starting container ${containerName}:`, error);
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({ message: `Failed to start container '${containerName}': ${errorDetail}`, type: 'error', duration: 5000 });
  } finally {
    setActionLoading(containerName, 'start', false);
  }
};

const createTarballApi = async (containerName) => {
  setActionLoading(containerName, 'createTarball', true);
  try {
    await api.createTarball(containerName);
    ElMessage({ message: `Tarball created for '${containerName}'.`, type: 'success' });
    fetchTarballs(); // Refresh tarball list
  } catch (error) {
    console.error(`Error creating tarball for ${containerName}:`, error);
    const errorDetail = error.response?.data?.detail || error.message || 'Unknown error';
    ElMessage({ message: `Failed to create tarball for '${containerName}': ${errorDetail}`, type: 'error', duration: 7000 }); // Longer duration as it's a background process potentially
  } finally {
    setActionLoading(containerName, 'createTarball', false);
  }
};

// --- Event Handlers ---
const openCreateContainerModal = () => {
  createModalVisible.value = true;
};

const resetCreateForm = () => {
  if (createFormRef.value) {
    createFormRef.value.resetFields();
  }
};

const handleCreateSubmit = async () => {
  if (!createFormRef.value) return;
  await createFormRef.value.validate((valid) => {
    if (valid) {
      createContainerApi({
        image_name: createForm.image_name,
        container_name: createForm.container_name,
      });
    } else {
      ElMessage({ message: 'Please fill in required fields.', type: 'warning' });
    }
  });
};

const handleDeleteContainer = (row) => {
  ElMessageBox.confirm(`Are you sure you want to delete container '${row.name}'? This cannot be undone.`, 'Confirm Delete', {
    confirmButtonText: 'Delete',
    cancelButtonText: 'Cancel',
    type: 'warning',
    draggable: true,
  })
    .then(() => {
      deleteContainerApi(row.name);
    })
    .catch(() => {
      ElMessage({ type: 'info', message: 'Delete cancelled.' });
    });
};

const handleStartContainer = (row) => {
  startContainerApi(row.name);
};

const handleStopContainer = (row) => {
  ElMessageBox.confirm(`Are you sure you want to stop container '${row.name}'?`, 'Confirm Stop', {
    confirmButtonText: 'Stop',
    cancelButtonText: 'Cancel',
    type: 'warning',
    draggable: true,
  })
    .then(() => {
      stopContainerApi(row.name);
    })
    .catch(() => {
      ElMessage({ type: 'info', message: 'Stop cancelled.' });
    });
};

const handleCreateTarball = (row) => {
  ElMessageBox.confirm(
    `Are you sure you want to create a new tarball from container '${row.name}'? This will take a snapshot of its current state.`,
    'Confirm Create Tarball',
    {
      confirmButtonText: 'Create',
      cancelButtonText: 'Cancel',
      type: 'info',
      draggable: true,
    }
  )
    .then(() => {
      createTarballApi(row.name);
    })
    .catch(() => {
      ElMessage({ type: 'info', message: 'Tarball creation cancelled.' });
    });
};

const handleShell = (row) => {
  selectedContainerNameForShell.value = row.name;
  terminalModalVisible.value = true;
};

const setActionLoading = (containerName, action, isLoading) => {
  if (!actionLoading[containerName]) {
    actionLoading[containerName] = reactive({});
  }
  actionLoading[containerName][action] = isLoading;
};

// --- Lifecycle Hooks ---
onMounted(() => {
  fetchContainers();
  fetchTarballs();
});
</script>

<style scoped>
.tab-header {
  display: flex;
  justify-content: flex-end; /* Align buttons to the right */
  gap: 10px; /* Space between buttons */
  margin-bottom: 15px;
}

.docker-table {
  width: 100%;
}

.docker-table .el-button {
  padding: 8px 12px; /* Adjust button padding */
}

.action-buttons {
  display: flex; /* Use flexbox for inline buttons */
  gap: 5px; /* Space between buttons */
  flex-wrap: wrap; /* Allow buttons to wrap if needed */
}

/* Improve alignment in table cells */
.el-table :deep(.el-table__cell) {
  vertical-align: top;
}

/* Optional: Style for expandable row content */
/* .docker-table .el-table__expanded-cell {
    background-color: var(--el-fill-color-lighter) !important;
} */
</style>
