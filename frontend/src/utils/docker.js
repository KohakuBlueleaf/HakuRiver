// src/utils/docker.js
import { formatDateTime } from './health'; // Reuse date formatting

/**
 * Formats container status for display.
 * @param {string | null | undefined} status - The Docker container status string.
 * @returns {string} - Formatted status string.
 */
export function formatContainerStatus(status) {
  if (!status) return 'Unknown';
  // Docker status can be complex (e.g., "Exited (0)", "Up 5 minutes").
  // Simplify for display.
  if (status.toLowerCase().includes('up')) return 'Running';
  if (status.toLowerCase().includes('exited') || status.toLowerCase().includes('stopped')) return 'Stopped';
  if (status.toLowerCase().includes('created')) return 'Created';
  return status; // Return as is for other states
}

/**
 * Determines the Element Plus tag type based on container status.
 * @param {string | null | undefined} status - The Docker container status string.
 * @returns {string} - 'success', 'info', 'danger', 'warning'.
 */
export function getContainerStatusType(status) {
  const formatted = formatContainerStatus(status).toLowerCase();
  if (formatted === 'running') return 'success';
  if (formatted === 'stopped') return 'info'; // Or 'danger' depending on desired emphasis
  if (formatted === 'created') return 'warning';
  return 'info'; // Default
}

/**
 * Formats a Unix timestamp to a readable date/time string.
 * @param {number | null | undefined} timestamp - Unix timestamp in seconds.
 * @returns {string} - Formatted date string or '-'.
 */
export function formatUnixTimestamp(timestamp) {
  if (timestamp === null || timestamp === undefined) return '-';
  // Convert seconds to milliseconds for Date object
  const date = new Date(timestamp * 1000);
  return formatDateTime(date); // Reuse the existing function
}

/**
 * Parses timestamp from a tarball filename (e.g., "myenv-1678886400.tar").
 * @param {string} filename - The tarball filename.
 * @returns {number | null} - Unix timestamp or null if parsing fails.
 */
export function parseTimestampFromTarballFilename(filename) {
  if (!filename) return null;
  const match = RegExp(/-(\d+)\.tar$/).exec(filename);
  if (match?.[1]) {
    try {
      return parseInt(match[1], 10);
    } catch (e) {
      console.error('Failed to parse timestamp from filename:', filename, e);
      return null;
    }
  }
  return null;
}
