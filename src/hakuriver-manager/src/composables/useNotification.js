import { ElMessage, ElNotification } from 'element-plus'

export function useNotification() {
  function success(message, title = 'Success') {
    ElMessage({
      message,
      type: 'success',
      duration: 3000,
    })
  }

  function error(message, title = 'Error') {
    ElMessage({
      message,
      type: 'error',
      duration: 5000,
    })
  }

  function warning(message, title = 'Warning') {
    ElMessage({
      message,
      type: 'warning',
      duration: 4000,
    })
  }

  function info(message, title = 'Info') {
    ElMessage({
      message,
      type: 'info',
      duration: 3000,
    })
  }

  function notify(options) {
    ElNotification({
      title: options.title || 'Notification',
      message: options.message,
      type: options.type || 'info',
      duration: options.duration || 4500,
      position: options.position || 'top-right',
    })
  }

  return {
    success,
    error,
    warning,
    info,
    notify,
  }
}
