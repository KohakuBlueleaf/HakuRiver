<script setup>
import { useLoadingStore } from '@/stores/loading'

const loadingStore = useLoadingStore()
</script>

<template>
  <Transition name="fade">
    <div
      v-if="loadingStore.isLoading"
      class="global-loading">
      <div class="loading-content">
        <div class="loading-spinner">
          <span class="i-carbon-renew animate-spin text-2xl text-blue-500"></span>
        </div>
        <div class="loading-messages">
          <div
            v-for="(msg, idx) in loadingStore.allMessages"
            :key="idx"
            class="loading-message">
            {{ msg }}
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.global-loading {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  pointer-events: none;
}

.loading-content {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: rgba(30, 41, 59, 0.95);
  border-radius: 12px;
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.3),
    0 0 0 1px rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(8px);
}

.loading-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-messages {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.loading-message {
  font-size: 14px;
  color: #e2e8f0;
  white-space: nowrap;
}

/* Animation */
.fade-enter-active,
.fade-leave-active {
  transition: all 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

/* Light mode */
:root:not(.dark) .loading-content {
  background: rgba(255, 255, 255, 0.95);
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.15),
    0 0 0 1px rgba(0, 0, 0, 0.05);
}

:root:not(.dark) .loading-message {
  color: #334155;
}
</style>
