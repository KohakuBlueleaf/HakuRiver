<script setup>
import { useUIStore } from '@/stores/ui'

const route = useRoute()
const uiStore = useUIStore()

const pageTitle = computed(() => {
  const titles = {
    '/': 'Dashboard',
    '/nodes': 'Compute Nodes',
    '/gpu': 'GPU Overview',
    '/tasks': 'Tasks',
    '/vps': 'VPS Instances',
    '/docker': 'Docker Management',
    '/stats': 'Statistics',
  }
  // Check for exact match first, then prefix match
  return titles[route.path] || titles[Object.keys(titles).find((k) => route.path.startsWith(k))] || 'KohakuRiver'
})

const themeOptions = [
  { value: 'light', label: 'Light', icon: 'i-carbon-sun' },
  { value: 'dark', label: 'Dark', icon: 'i-carbon-moon' },
  { value: 'system', label: 'System', icon: 'i-carbon-laptop' },
]

const currentThemeIcon = computed(() => {
  const option = themeOptions.find((o) => o.value === uiStore.theme)
  return option?.icon || 'i-carbon-laptop'
})
</script>

<template>
  <header
    class="h-16 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between px-4 md:px-6"
  >
    <!-- Left Side - Menu button + Title -->
    <div class="flex items-center gap-3">
      <!-- Mobile Menu Button -->
      <button v-if="uiStore.isMobile" class="btn-icon md:hidden" @click="uiStore.toggleMobileMenu">
        <span class="i-carbon-menu text-xl"></span>
      </button>

      <h1 class="text-lg md:text-xl font-semibold text-gray-800 dark:text-white truncate">{{ pageTitle }}</h1>
    </div>

    <!-- Right Side Actions -->
    <div class="flex items-center gap-2 md:gap-4">
      <!-- Theme Selector -->
      <el-dropdown trigger="click" @command="uiStore.setTheme">
        <button class="btn-icon">
          <span :class="currentThemeIcon" class="text-xl"></span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="option in themeOptions"
              :key="option.value"
              :command="option.value"
              :class="{ 'is-active': uiStore.theme === option.value }"
            >
              <span :class="option.icon" class="mr-2"></span>
              {{ option.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- Refresh Button -->
      <button class="btn-icon hidden sm:flex" @click="$router.go(0)" title="Refresh">
        <span class="i-carbon-renew text-xl"></span>
      </button>
    </div>
  </header>
</template>
