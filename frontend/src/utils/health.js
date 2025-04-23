// src/utils/health.js
import api from '@/services/api';

/**
 * Fetches health data for all nodes or a specific node.
 * @param {string | null} hostname - Optional hostname to filter by.
 * @returns {Promise<Array<object>>} - Promise resolving to an array of node health objects.
 */
export async function fetchHealthData(hostname = null) {
  // No error handling here, let the caller handle it.
  const response = await api.getHealth(hostname);
  if (!hostname) {
    const newStats = response.data.nodes;
    return newStats[newStats.length - 1];
  }
  return response.data || []; // Ensure we return an array
}

/**
 * Calculates aggregated cluster statistics from raw node health data.
 * @param {Array<object>} nodesHealth - Array of node health objects from fetchHealthData.
 * @returns {object} - Object containing aggregated statistics.
 */
export function calculateAggregatedStats(nodesHealth) {
  const onlineNodes = nodesHealth.filter((n) => n.status === 'online');
  const initial = {
    totalNodes: nodesHealth.length,
    onlineNodes: onlineNodes.length,
    totalCores: 0,
    totalMemBytes: 0,
    usedMemBytes: 0,
    avgCpuPercent: 0,
    avgMemPercent: 0, // This will be calculated based on aggregated bytes
    lastUpdated: new Date(), // Add timestamp of calculation
  };

  if (!onlineNodes.length) return initial;

  const stats = onlineNodes.reduce(
    (acc, node) => {
      acc.totalCores += node.total_cores || 0;
      if (node.memory_total_bytes) {
        acc.totalMemBytes += node.memory_total_bytes;
        acc.usedMemBytes += node.memory_used_bytes || 0;
      }
      acc.avgCpuPercent += node.cpu_percent || 0; // Sum for averaging later
      // We don't average memory percent directly anymore
      return acc;
    },
    { ...initial }
  );

  // Calculate averages/percentages
  stats.avgCpuPercent = stats.avgCpuPercent / onlineNodes.length;
  stats.avgMemPercent = stats.totalMemBytes > 0 ? (stats.usedMemBytes / stats.totalMemBytes) * 100 : 0;

  return stats;
}

/**
 * Finds the health data for a specific node from the list.
 * @param {Array<object>} nodesHealth - Array of node health objects.
 * @param {string} hostname - The hostname to find.
 * @returns {object | null} - The health object for the node or null if not found.
 */
export function getNodeHealth(nodesHealth, hostname) {
  if (!hostname || !nodesHealth) return null;
  return nodesHealth.find((n) => n.hostname === hostname) || null;
}

/**
 * Formats bytes into Gigabytes (GB) with one decimal place.
 * @param {number | null | undefined} bytes - The number of bytes.
 * @returns {string} - Formatted string (e.g., "4.0 GB").
 */
export function formatBytesToGB(bytes) {
  if (bytes === null || bytes === undefined || bytes === 0) return '0.0';
  const gb = bytes / (1024 * 1024 * 1024);
  return gb.toFixed(1);
}

/**
 * Formats an ISO date string or Date object into a locale string.
 * @param {string | Date | null | undefined} isoStringOrDate - The date input.
 * @returns {string} - Formatted date string or '-'.
 */
export function formatDateTime(isoStringOrDate) {
  if (!isoStringOrDate) return '-';
  try {
    const date = isoStringOrDate instanceof Date ? isoStringOrDate : new Date(isoStringOrDate);
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }
    return date.toLocaleString();
  } catch (e) {
    return 'Invalid Date Format';
  }
}

/**
 * Determines the Element Plus tag type based on node status.
 * @param {string | null | undefined} status - The node status string.
 * @returns {string} - 'success', 'info', 'danger', or 'warning'.
 */
export const getStatusType = (status) => {
  switch (status?.toLowerCase()) {
    case 'online':
      return 'success';
    case 'offline':
      return 'info';
    case 'lost':
      return 'danger'; // Assuming 'lost' might appear
    default:
      return 'warning'; // For unknown or null status
  }
};
