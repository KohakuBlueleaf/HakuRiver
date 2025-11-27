import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { routes } from 'vue-router/auto-routes'
import App from './App.vue'

// UnoCSS
import 'virtual:uno.css'

// Element Plus styles
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

// Custom styles
import './styles/main.css'

// Create router with auto-generated routes
const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Create Pinia store
const pinia = createPinia()

// Create app
const app = createApp(App)

// Use plugins
app.use(pinia)
app.use(router)

// Initialize UI store for theme
import { useUIStore } from './stores/ui'
router.isReady().then(() => {
  const uiStore = useUIStore()
  uiStore.init()
})

// Mount app
app.mount('#app')
