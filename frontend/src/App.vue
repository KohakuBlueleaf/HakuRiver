<template>
  <div class="common-layout">
    <el-container class="main-container">
      <!-- Mobile Menu Overlay (visible only on small screens) -->
      <div v-if="isMobileScreen && sidebarVisible" class="mobile-overlay" @click="toggleSidebar"></div>

      <!-- Sidebar Navigation with dynamic width -->
      <el-aside
        :width="sidebarWidth"
        :class="{ 'mobile-sidebar': isMobileScreen && sidebarVisible, 'sidebar-collapsed': !sidebarVisible && !isMobileScreen }"
      >
        <div class="sidebar-header">
          <div class="logo-container">
            <h2 v-if="sidebarVisible">HakuRiver</h2>
            <h2 v-else>H</h2>
          </div>
          <!-- Toggle button on larger screens -->
          <el-button v-if="!isMobileScreen" type="text" class="toggle-sidebar-btn" @click="toggleSidebar">
            <el-icon v-if="sidebarVisible"><ArrowLeft /></el-icon>
            <el-icon v-else><ArrowRight /></el-icon>
          </el-button>
        </div>

        <el-scrollbar>
          <el-menu
            :default-active="$route.path"
            class="el-menu-vertical-hakuriver"
            :router="true"
            text-color="#bfcbd9"
            active-text-color="#409EFF"
            background-color="#1f2d3d"
            :collapse="!sidebarVisible"
          >
            <el-menu-item index="/">
              <el-icon><House /></el-icon>
              <template #title>Dashboard</template>
            </el-menu-item>
            <el-menu-item index="/nodes">
              <el-icon><Cpu /></el-icon>
              <template #title>Nodes</template>
            </el-menu-item>
            <el-menu-item index="/gpus">
              <!-- NEW MENU ITEM -->
              <el-icon><Monitor /></el-icon>
              <!-- Using Monitor icon, you might need to import it -->
              <template #title>GPUs</template>
            </el-menu-item>
            <el-menu-item index="/tasks">
              <el-icon><Tickets /></el-icon>
              <template #title>Tasks</template>
            </el-menu-item>
            <el-menu-item index="/docker">
              <el-icon><Cellphone /></el-icon>
              <template #title>Docker</template>
            </el-menu-item>
          </el-menu>
        </el-scrollbar>
      </el-aside>

      <!-- Main Content Area -->
      <el-container class="content-container">
        <!-- Header with menu toggle button for mobile -->
        <el-header class="content-header">
          <div class="header-content">
            <!-- Mobile menu toggle button -->
            <el-button v-if="isMobileScreen" type="text" class="mobile-menu-btn" @click="toggleSidebar">
              <el-icon><Menu /></el-icon>
            </el-button>

            <!-- Page title or breadcrumbs could go here -->
            <div class="page-title">{{ currentPageTitle }}</div>

            <!-- Right side header content (optional) -->
            <div class="header-actions">
              <!-- Any header actions like profile, notifications, etc. -->
            </div>
          </div>
        </el-header>

        <el-main class="content-main">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRoute } from 'vue-router';
import { House, Cpu, Tickets, Menu, ArrowLeft, ArrowRight } from '@element-plus/icons-vue';

// Responsive sidebar state
const sidebarVisible = ref(true);
const isMobileScreen = ref(false);
const MOBILE_BREAKPOINT = 768; // Adjust this value as needed
const route = useRoute();

// Toggle sidebar visibility
const toggleSidebar = () => {
  sidebarVisible.value = !sidebarVisible.value;
};

// Compute sidebar width based on state
const sidebarWidth = computed(() => {
  if (isMobileScreen.value) {
    return sidebarVisible.value ? '220px' : '0px';
  } else {
    return sidebarVisible.value ? '220px' : '64px';
  }
});

// Get current page title based on route
const currentPageTitle = computed(() => {
  const path = route.path;
  if (path === '/') return 'Dashboard';
  if (path === '/nodes') return 'Nodes';
  if (path === '/tasks') return 'Tasks';
  if (path === '/docker') return 'Docker'; // New page title
  // Add more cases as needed
  return 'HakuRiver';
});

// Check screen size and update state
const checkScreenSize = () => {
  isMobileScreen.value = window.innerWidth < MOBILE_BREAKPOINT;
  // Auto-hide sidebar on mobile
  if (isMobileScreen.value) {
    sidebarVisible.value = false;
  }
};

// Set up responsive behavior
onMounted(() => {
  checkScreenSize();
  window.addEventListener('resize', checkScreenSize);
});

onUnmounted(() => {
  window.removeEventListener('resize', checkScreenSize);
});
</script>

<style>
/* Global Styles */
:root {
  /* Define base font size - adjust as needed */
  font-size: 22px; /* Larger base font size */

  /* Define font family - Consolas is monospace, this is a sans-serif stack */
  /* Prioritize system UI fonts, fallback to common sans-serif */
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen-Sans, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif;
}

html,
body,
#app,
.common-layout,
.main-container {
  height: 100%;
  margin: 0;
  padding: 0;
  background-color: var(--el-bg-color);
  color: var(--el-text-color-primary);
}

/* Main container layout */
.main-container {
  display: flex;
  position: relative; /* For absolute positioning of overlay */
}

/* --- SIDEBAR STYLES --- */
.el-aside {
  background-color: #1f2228;
  color: var(--el-color-white);
  display: flex;
  flex-direction: column;
  height: 100vh;
  border-right: 1px solid var(--el-border-color-darker);
  transition: width 0.3s ease;
  overflow: hidden; /* Prevents content from showing during animation */
}

/* Mobile sidebar styling */
.mobile-sidebar {
  position: fixed;
  z-index: 1000;
  height: 100vh;
  top: 0;
  left: 0;
  box-shadow: 4px 0 10px rgba(0, 0, 0, 0.1);
}

/* Overlay for mobile when sidebar is open */
.mobile-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: 999;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo-container {
  padding: 15px;
  text-align: center;
  background-color: #262a33;
  flex-grow: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.logo-container h2 {
  margin: 0;
  color: var(--el-color-primary-light-3);
  transition: opacity 0.3s;
}

.toggle-sidebar-btn {
  color: #c0c4cc;
  padding: 10px;
  margin-right: 5px;
}

/* Collapsed sidebar styles */
.sidebar-collapsed {
  width: 64px !important;
}

.sidebar-collapsed .logo-container {
  padding: 15px 5px;
}

/* Styling the menu */
.el-menu-vertical-hakuriver {
  border-right: none !important;
  flex-grow: 1;
  background-color: #1f2228 !important;
}

.el-menu-vertical-hakuriver .el-menu-item,
.el-menu-vertical-hakuriver .el-sub-menu__title {
  color: #c0c4cc;
  background-color: transparent !important;
}

/* Hover state */
.el-menu-vertical-hakuriver .el-menu-item:hover,
.el-menu-vertical-hakuriver .el-sub-menu__title:hover {
  background-color: #2c303a !important;
}

/* Active state */
.el-menu-vertical-hakuriver .el-menu-item.is-active {
  color: var(--el-color-primary);
  background-color: rgba(64, 158, 255, 0.1) !important;
}

/* --- CONTENT AREA STYLES --- */
.content-container {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  width: 100%;
}

.content-header {
  background-color: var(--el-bg-color-page);
  padding: 0 20px;
  border-bottom: 1px solid var(--el-border-color);
  height: auto;
  display: flex;
  align-items: center;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  height: 60px;
}

.mobile-menu-btn {
  font-size: 1.2rem;
  padding: 7px;
  margin-right: 10px;
}

.page-title {
  font-size: 1.1rem;
  font-weight: 500;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 15px;
}

.content-main {
  padding: 20px;
  overflow-y: auto;
  flex-grow: 1;
}

/* Improve scrollbar appearance */
.el-scrollbar__bar .el-scrollbar__thumb {
  background-color: rgba(144, 147, 153, 0.5);
}
.el-scrollbar__bar .el-scrollbar__thumb:hover {
  background-color: rgba(144, 147, 153, 0.7);
}

/* Responsive adjustments */
@media (max-width: 768px) {
  :root {
    font-size: 16px; /* Smaller base font size for mobile */
  }

  .content-main {
    padding: 15px;
  }
}
</style>
