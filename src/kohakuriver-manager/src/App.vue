<script setup>
import { useUIStore } from '@/stores/ui'
import TheSidebar from '@/components/layout/TheSidebar.vue'
import GlobalLoading from '@/components/common/GlobalLoading.vue'

const uiStore = useUIStore()

// Initialize UI store on mount
onMounted(() => {
  uiStore.init()
})
</script>

<template>
  <div class="app-root h-screen overflow-hidden bg-app-page">
    <!-- Sidebar -->
    <TheSidebar />

    <!-- Main Content Area -->
    <div
      class="main-container h-screen transition-all duration-300"
      :class="[uiStore.isMobile ? 'ml-0' : uiStore.sidebarCollapsed ? 'ml-16' : 'ml-64']"
    >
      <!-- Page Content -->
      <main class="main-content h-full overflow-auto p-4 md:p-6">
        <router-view v-slot="{ Component, route }">
          <component :is="Component" :key="route.path" />
        </router-view>
      </main>
    </div>

    <!-- Global Loading Indicator -->
    <GlobalLoading />
  </div>
</template>

