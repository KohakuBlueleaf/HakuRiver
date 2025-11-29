<script setup>
import { useUIStore } from '@/stores/ui'

const uiStore = useUIStore()

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
  <header class="h-12 bg-app-sidebar flex items-center justify-between px-4 md:px-6">
    <!-- Left Side - Menu button -->
    <div class="flex items-center gap-3">
      <!-- Mobile Menu Button -->
      <button
        v-if="uiStore.isMobile"
        class="header-btn md:hidden"
        @click="uiStore.toggleMobileMenu">
        <span class="i-carbon-menu text-xl"></span>
      </button>
    </div>

    <!-- Right Side Actions -->
    <div class="flex items-center gap-2 md:gap-4">
      <!-- Theme Selector -->
      <el-dropdown
        trigger="click"
        @command="uiStore.setTheme">
        <button class="header-btn">
          <span
            :class="currentThemeIcon"
            class="text-xl"></span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="option in themeOptions"
              :key="option.value"
              :command="option.value"
              :class="{ 'is-active': uiStore.theme === option.value }">
              <span
                :class="option.icon"
                class="mr-2"></span>
              {{ option.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- Refresh Button -->
      <button
        class="header-btn hidden sm:flex"
        @click="$router.go(0)"
        title="Refresh">
        <span class="i-carbon-renew text-xl"></span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.header-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: #9ca3af;
  transition: all 0.15s;
}

.header-btn:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.1);
}
</style>
