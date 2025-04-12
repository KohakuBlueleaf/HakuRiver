<template>
  <div class="common-layout">
    <el-container class="main-container">
      <!-- Sidebar Navigation -->
      <el-aside width="220px">
        <div class="logo-container">
          <!-- You can add a logo here if you have one -->
          <h2>HakuRiver</h2>
        </div>
        <el-scrollbar>
          <el-menu
            :default-active="$route.path"
            class="el-menu-vertical-hakuriver"
            :router="true"
            text-color="#bfcbd9"
            active-text-color="#409EFF"
            background-color="#1f2d3d"
          >
            <el-menu-item index="/">
              <el-icon><House /></el-icon>
              <span>Dashboard</span>
            </el-menu-item>
            <el-menu-item index="/nodes">
              <el-icon><Cpu /></el-icon>
              <span>Nodes</span>
            </el-menu-item>
            <el-menu-item index="/tasks">
              <el-icon><Tickets /></el-icon>
              <span>Tasks</span>
            </el-menu-item>
            <!-- Add more navigation items with icons -->
            <!-- Example:
             <el-sub-menu index="settings">
               <template #title>
                  <el-icon><Setting /></el-icon>
                  <span>Settings</span>
               </template>
               <el-menu-item index="/settings/general">General</el-menu-item>
             </el-sub-menu>
             -->
          </el-menu>
        </el-scrollbar>
      </el-aside>

      <!-- Main Content Area -->
      <el-container class="content-container">
        <!-- Optional Header within content area if needed -->
        <!--
         <el-header class="content-header">
            Header Content (e.g., user profile, breadcrumbs)
         </el-header>
         -->
        <el-main class="content-main">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
// Import icons used in the menu
import { House, Cpu, Tickets, Setting } from '@element-plus/icons-vue';

// No specific script logic needed for layout itself
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

  /* Optional: Add Consolas if you prefer monospace, but sans-serif is usually better for UI */
  /* font-family: Consolas, Monaco, 'Andale Mono', 'Ubuntu Mono', monospace; */
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

/* Specific layout styles */
.main-container {
  display: flex;
}

/* --- UPDATED SIDEBAR STYLES --- */
.el-aside {
  /* Slightly less saturated dark background */
  background-color: #1f2228; /* Changed from #1f2d3d */
  color: var(--el-color-white);
  display: flex;
  flex-direction: column;
  height: 100vh;
  border-right: 1px solid var(--el-border-color-darker);
}

.logo-container {
  padding: 15px 20px;
  text-align: center;
  /* Slightly lighter background for logo area */
  background-color: #262a33; /* Changed from #2c3e50 */
  border-bottom: 1px solid var(--el-border-color-darker);
}
.logo-container h2 {
  margin: 0;
  color: var(--el-color-primary-light-3);
}

/* Styling the menu */
.el-menu-vertical-hakuriver {
  border-right: none;
  flex-grow: 1;
  /* Explicitly set menu background to match aside */
  background-color: #1f2228 !important; /* Added !important */
}
.el-menu-vertical-hakuriver .el-menu-item,
.el-menu-vertical-hakuriver .el-sub-menu__title {
  /* Slightly brighter text color for better readability */
  color: #c0c4cc; /* Changed from #bfcbd9 */
  background-color: transparent !important; /* Ensure no default bg */
}

/* Hover state */
.el-menu-vertical-hakuriver .el-menu-item:hover,
.el-menu-vertical-hakuriver .el-sub-menu__title:hover {
  /* Lighter background on hover */
  background-color: #2c303a !important; /* Changed from #2c3e50 */
}

/* Active state */
.el-menu-vertical-hakuriver .el-menu-item.is-active {
  color: var(--el-color-primary); /* Keep active text bright blue */
  /* Use a subtle background highlight instead of the default dark blue */
  background-color: rgba(64, 158, 255, 0.1) !important; /* Light blue transparent bg */
}
/* --- END UPDATED SIDEBAR STYLES --- */

.content-container {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
}

.content-header {
  /* Optional header styles */
  background-color: var(--el-bg-color-page);
  padding: 10px 20px;
  border-bottom: 1px solid var(--el-border-color);
  height: auto;
}

.content-main {
  padding: 20px;
  overflow-y: auto;
  flex-grow: 1;
}

/* Improve scrollbar appearance (Keep as is) */
.el-scrollbar__bar .el-scrollbar__thumb {
  background-color: rgba(144, 147, 153, 0.5);
}
.el-scrollbar__bar .el-scrollbar__thumb:hover {
  background-color: rgba(144, 147, 153, 0.7);
}
</style>
