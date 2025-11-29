<script setup>
import { useClusterStore } from '@/stores/cluster'
import { formatBytes, formatPercent } from '@/utils/format'
import { usePolling } from '@/composables/usePolling'
import Plotly from 'plotly.js-dist-min'

const clusterStore = useClusterStore()

// Chart refs
const cpuChartRef = ref(null)
const memoryChartRef = ref(null)
const nodeCompareChartRef = ref(null)

// Health history data
const healthHistory = ref([])
const maxHistoryPoints = 60

// Selected node for detailed view
const selectedNode = ref(null)

// Polling
const { start: startPolling } = usePolling(async () => {
  await clusterStore.fetchNodes()
  await clusterStore.fetchHealth()

  // Add to history
  const timestamp = new Date()
  healthHistory.value.push({
    timestamp,
    avgCpu: clusterStore.avgCpuPercent,
    avgMemory: clusterStore.avgMemoryPercent,
    nodes: clusterStore.nodes.map((n) => ({
      hostname: n.hostname,
      cpu: n.cpu_percent || 0,
      memory: n.memory_percent || 0,
    })),
  })

  // Trim history
  if (healthHistory.value.length > maxHistoryPoints) {
    healthHistory.value = healthHistory.value.slice(-maxHistoryPoints)
  }

  updateCharts()
}, 2000)

onMounted(() => {
  startPolling()
})

const isDark = computed(() => document.documentElement.classList.contains('dark'))

const chartLayout = computed(() => ({
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { color: isDark.value ? '#e5e7eb' : '#374151' },
  margin: { t: 40, r: 20, b: 40, l: 50 },
  xaxis: {
    type: 'date',
    gridcolor: isDark.value ? '#374151' : '#e5e7eb',
  },
  yaxis: {
    gridcolor: isDark.value ? '#374151' : '#e5e7eb',
    range: [0, 100],
  },
  legend: {
    orientation: 'h',
    y: -0.2,
  },
}))

function updateCharts() {
  if (healthHistory.value.length < 2) return

  const timestamps = healthHistory.value.map((h) => h.timestamp)
  const cpuValues = healthHistory.value.map((h) => h.avgCpu)
  const memoryValues = healthHistory.value.map((h) => h.avgMemory)

  // CPU Chart
  if (cpuChartRef.value) {
    const cpuData = [
      {
        x: timestamps,
        y: cpuValues,
        type: 'scattergl',
        mode: 'lines',
        name: 'Cluster CPU',
        line: { color: '#3b82f6', width: 2 },
        fill: 'tozeroy',
        fillcolor: 'rgba(59, 130, 246, 0.1)',
      },
    ]

    Plotly.react(
      cpuChartRef.value,
      cpuData,
      {
        ...chartLayout.value,
        title: { text: 'CPU Usage Over Time', font: { size: 14 } },
        yaxis: { ...chartLayout.value.yaxis, title: 'CPU %' },
      },
      { responsive: true }
    )
  }

  // Memory Chart
  if (memoryChartRef.value) {
    const memoryData = [
      {
        x: timestamps,
        y: memoryValues,
        type: 'scattergl',
        mode: 'lines',
        name: 'Cluster Memory',
        line: { color: '#10b981', width: 2 },
        fill: 'tozeroy',
        fillcolor: 'rgba(16, 185, 129, 0.1)',
      },
    ]

    Plotly.react(
      memoryChartRef.value,
      memoryData,
      {
        ...chartLayout.value,
        title: { text: 'Memory Usage Over Time', font: { size: 14 } },
        yaxis: { ...chartLayout.value.yaxis, title: 'Memory %' },
      },
      { responsive: true }
    )
  }

  // Node Comparison Chart
  if (nodeCompareChartRef.value && healthHistory.value.length > 0) {
    const latestData = healthHistory.value[healthHistory.value.length - 1]
    const nodeNames = latestData.nodes.map((n) => n.hostname)
    const nodeCpuValues = latestData.nodes.map((n) => n.cpu)
    const nodeMemoryValues = latestData.nodes.map((n) => n.memory)

    const compareData = [
      {
        x: nodeNames,
        y: nodeCpuValues,
        type: 'bar',
        name: 'CPU %',
        marker: { color: '#3b82f6' },
      },
      {
        x: nodeNames,
        y: nodeMemoryValues,
        type: 'bar',
        name: 'Memory %',
        marker: { color: '#10b981' },
      },
    ]

    Plotly.react(
      nodeCompareChartRef.value,
      compareData,
      {
        ...chartLayout.value,
        title: { text: 'Node Resource Comparison', font: { size: 14 } },
        barmode: 'group',
        yaxis: { ...chartLayout.value.yaxis, title: 'Usage %' },
      },
      { responsive: true }
    )
  }
}

// Watch for theme changes
watch(isDark, () => {
  nextTick(() => updateCharts())
})

const gpuStats = computed(() => {
  const gpus = []
  for (const node of clusterStore.nodes) {
    if (node.gpu_info) {
      for (const gpu of node.gpu_info) {
        gpus.push({
          ...gpu,
          node: node.hostname,
        })
      }
    }
  }
  return gpus
})
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="page-title mb-0">Statistics</h2>
        <p class="text-muted">Real-time cluster monitoring</p>
      </div>
      <div class="text-sm text-muted">
        <span class="i-carbon-time mr-1"></span>
        Updated every 2 seconds
      </div>
    </div>

    <!-- Quick Stats -->
    <div class="grid-stats">
      <div class="stat-card">
        <span class="i-carbon-chip text-3xl text-blue-500 mb-2 block"></span>
        <div
          class="stat-value"
          :class="clusterStore.avgCpuPercent > 80 ? 'text-red-500' : ''">
          {{ formatPercent(clusterStore.avgCpuPercent) }}
        </div>
        <div class="stat-label">Avg CPU Usage</div>
      </div>

      <div class="stat-card">
        <span class="i-carbon-data-base text-3xl text-green-500 mb-2 block"></span>
        <div
          class="stat-value"
          :class="clusterStore.avgMemoryPercent > 80 ? 'text-red-500' : ''">
          {{ formatPercent(clusterStore.avgMemoryPercent) }}
        </div>
        <div class="stat-label">Avg Memory Usage</div>
      </div>

      <div class="stat-card">
        <span class="i-carbon-bare-metal-server text-3xl text-purple-500 mb-2 block"></span>
        <div class="stat-value">{{ clusterStore.onlineNodes.length }} / {{ clusterStore.nodes.length }}</div>
        <div class="stat-label">Online Nodes</div>
      </div>

      <div class="stat-card">
        <span class="i-carbon-cube text-3xl text-yellow-500 mb-2 block"></span>
        <div class="stat-value">{{ clusterStore.totalGpus }}</div>
        <div class="stat-label">Total GPUs</div>
      </div>
    </div>

    <!-- Charts -->
    <div class="grid-2">
      <!-- CPU Chart -->
      <div class="card">
        <div
          ref="cpuChartRef"
          class="h-64"></div>
      </div>

      <!-- Memory Chart -->
      <div class="card">
        <div
          ref="memoryChartRef"
          class="h-64"></div>
      </div>
    </div>

    <!-- Node Comparison -->
    <div class="card">
      <div
        ref="nodeCompareChartRef"
        class="h-72"></div>
    </div>

    <!-- GPU Stats -->
    <div
      v-if="gpuStats.length > 0"
      class="card">
      <h3 class="card-title mb-4">GPU Overview</h3>
      <div class="grid-cards">
        <div
          v-for="(gpu, idx) in gpuStats"
          :key="idx"
          class="p-4 bg-app-surface rounded-lg">
          <div class="flex items-center gap-3 mb-3">
            <span class="i-carbon-cube text-xl text-yellow-500"></span>
            <div>
              <div class="font-medium text-sm">{{ gpu.name || `GPU ${idx}` }}</div>
              <div class="text-xs text-muted">{{ gpu.node }}</div>
            </div>
          </div>
          <div
            v-if="gpu.memory_total"
            class="space-y-2">
            <ResourceBar
              :value="gpu.memory_used || 0"
              :max="gpu.memory_total"
              label="Memory"
              color="yellow" />
            <div class="text-xs text-muted">
              {{ formatBytes(gpu.memory_used || 0) }} / {{ formatBytes(gpu.memory_total) }}
            </div>
          </div>
          <div
            v-if="gpu.utilization !== undefined"
            class="mt-2">
            <ResourceBar
              :value="gpu.utilization"
              :max="100"
              label="Utilization"
              color="blue" />
          </div>
          <div
            v-if="gpu.temperature"
            class="text-xs text-muted mt-2">
            Temperature: {{ gpu.temperature }}°C
          </div>
        </div>
      </div>
    </div>

    <!-- Memory Details -->
    <div class="card">
      <h3 class="card-title mb-4">Memory Details</h3>
      <div class="overflow-x-auto">
        <table class="table">
          <thead class="table-header">
            <tr>
              <th class="table-cell">Node</th>
              <th class="table-cell">Total</th>
              <th class="table-cell">Used</th>
              <th class="table-cell">Available</th>
              <th class="table-cell">Usage</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="node in clusterStore.nodes"
              :key="node.hostname"
              class="table-row">
              <td class="table-cell font-medium">{{ node.hostname }}</td>
              <td class="table-cell">{{ formatBytes(node.memory_total_bytes || 0) }}</td>
              <td class="table-cell">{{ formatBytes(node.memory_used_bytes || 0) }}</td>
              <td class="table-cell">
                {{ formatBytes((node.memory_total_bytes || 0) - (node.memory_used_bytes || 0)) }}
              </td>
              <td class="table-cell">
                <div class="flex items-center gap-2">
                  <div class="w-24">
                    <ResourceBar
                      :value="node.memory_used_bytes || 0"
                      :max="node.memory_total_bytes || 1"
                      color="auto"
                      size="sm"
                      :show-percent="false" />
                  </div>
                  <span>{{ formatPercent(node.memory_percent || 0) }}</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
