<script setup>
import { useUIStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const uiStore = useUIStore()

const menuItems = [
  { path: '/', icon: 'i-carbon-dashboard', label: 'Dashboard' },
  { path: '/nodes', icon: 'i-carbon-bare-metal-server', label: 'Nodes' },
  { path: '/gpu', icon: 'i-carbon-chip', label: 'GPUs' },
  { path: '/tasks', icon: 'i-carbon-task', label: 'Tasks' },
  { path: '/vps', icon: 'i-carbon-virtual-machine', label: 'VPS' },
  { path: '/docker', icon: 'i-carbon-container-software', label: 'Docker' },
  { path: '/stats', icon: 'i-carbon-chart-line', label: 'Statistics' },
]

const isActive = (path) => {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

function navigateTo(path) {
  router.push(path)
  // Close mobile menu on navigation
  if (uiStore.isMobile) {
    uiStore.closeMobileMenu()
  }
}
</script>

<template>
  <!-- Mobile Overlay -->
  <Transition name="fade">
    <div
      v-if="uiStore.isMobile && uiStore.mobileMenuOpen"
      class="fixed inset-0 bg-black/50 z-40 md:hidden"
      @click="uiStore.closeMobileMenu"
    ></div>
  </Transition>

  <!-- Sidebar -->
  <aside
    class="fixed left-0 top-0 h-screen bg-gray-900 text-gray-100 transition-all duration-300 z-50 flex flex-col"
    :class="[
      uiStore.isMobile
        ? uiStore.mobileMenuOpen
          ? 'translate-x-0 w-64'
          : '-translate-x-full w-64'
        : uiStore.sidebarCollapsed
          ? 'w-16'
          : 'w-64',
    ]"
  >
    <!-- Logo -->
    <div class="h-16 flex items-center justify-between px-4 border-b border-gray-800">
      <div class="flex items-center gap-3">
        <img src="/favicon.svg" alt="KohakuRiver" class="w-8 h-8 flex-shrink-0" />
        <span v-if="!uiStore.sidebarCollapsed || uiStore.isMobile" class="font-semibold text-lg">KohakuRiver</span>
      </div>
      <!-- Close button for mobile -->
      <button v-if="uiStore.isMobile" @click="uiStore.closeMobileMenu" class="p-1 rounded hover:bg-gray-800">
        <span class="i-carbon-close text-xl"></span>
      </button>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 py-4 overflow-y-auto">
      <ul class="space-y-1 px-2">
        <li v-for="item in menuItems" :key="item.path">
          <button
            @click="navigateTo(item.path)"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors"
            :class="isActive(item.path) ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'"
          >
            <span :class="item.icon" class="text-xl flex-shrink-0"></span>
            <span v-if="!uiStore.sidebarCollapsed || uiStore.isMobile" class="truncate">{{ item.label }}</span>
          </button>
        </li>
      </ul>
    </nav>

    <!-- Footer - Only show on desktop -->
    <div v-if="!uiStore.isMobile" class="p-3 border-t border-gray-800">
      <button
        @click="uiStore.toggleSidebar"
        class="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
      >
        <span
          :class="uiStore.sidebarCollapsed ? 'i-carbon-chevron-right' : 'i-carbon-chevron-left'"
          class="text-lg"
        ></span>
        <span v-if="!uiStore.sidebarCollapsed">Collapse</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
