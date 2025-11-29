// Task status definitions
export const TASK_STATUS = {
  PENDING: 'pending',
  ASSIGNING: 'assigning',
  RUNNING: 'running',
  PAUSED: 'paused',
  COMPLETED: 'completed',
  FAILED: 'failed',
  KILLED: 'killed',
  KILLED_OOM: 'killed_oom',
  LOST: 'lost',
  STOPPED: 'stopped',
}

// Node status definitions
export const NODE_STATUS = {
  ONLINE: 'online',
  OFFLINE: 'offline',
}

// Status color mappings
export const STATUS_COLORS = {
  // Task statuses
  pending: 'warning',
  assigning: 'info',
  running: 'success',
  paused: 'warning',
  completed: 'success',
  failed: 'danger',
  killed: 'danger',
  killed_oom: 'danger',
  lost: 'danger',
  stopped: 'gray',

  // Node statuses
  online: 'success',
  offline: 'danger',
}

// Status badge class mappings
export const STATUS_BADGE_CLASS = {
  pending: 'badge-warning',
  assigning: 'badge-info',
  running: 'badge-success',
  paused: 'badge-warning',
  completed: 'badge-success',
  failed: 'badge-danger',
  killed: 'badge-danger',
  killed_oom: 'badge-danger',
  lost: 'badge-danger',
  stopped: 'badge-gray',
  online: 'badge-success',
  offline: 'badge-danger',
}

// SSH key modes
export const SSH_KEY_MODES = {
  DISABLED: 'disabled', // No SSH, TTY-only mode (default)
  NONE: 'none', // SSH with passwordless root login
  UPLOAD: 'upload', // SSH with uploaded public key
  GENERATE: 'generate', // SSH with generated key pair
}

// Active statuses (for filtering)
export const ACTIVE_STATUSES = ['pending', 'assigning', 'running', 'paused']

// Terminal statuses (tasks that can have terminal access)
export const TERMINAL_STATUSES = ['running']
