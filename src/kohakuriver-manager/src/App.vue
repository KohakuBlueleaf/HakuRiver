<script setup>
import { useUIStore } from '@/stores/ui'
import TheSidebar from '@/components/layout/TheSidebar.vue'
import TheHeader from '@/components/layout/TheHeader.vue'
import GlobalLoading from '@/components/common/GlobalLoading.vue'

const uiStore = useUIStore()

// Initialize UI store on mount
onMounted(() => {
  uiStore.init()
})
</script>

<template>
  <div class="min-h-screen bg-gray-100 dark:bg-gray-900">
    <!-- Sidebar -->
    <TheSidebar />

    <!-- Main Content Area -->
    <div
      class="transition-all duration-300"
      :class="[uiStore.isMobile ? 'ml-0' : uiStore.sidebarCollapsed ? 'ml-16' : 'ml-64']"
    >
      <!-- Header -->
      <TheHeader />

      <!-- Page Content -->
      <main class="p-4 md:p-6">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>

    <!-- Global Loading Indicator -->
    <GlobalLoading />
  </div>
</template>

<style>
/* Page transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
