import { defineStore } from 'pinia'

export const useUIStore = defineStore('ui', () => {
  // State
  const sidebarCollapsed = ref(false)
  const mobileMenuOpen = ref(false)
  const isMobile = ref(false)
  const theme = ref(localStorage.getItem('hakuriver-theme') || 'system')

  // Computed
  const isDark = computed(() => {
    if (theme.value === 'dark') return true
    if (theme.value === 'light') return false
    // System preference
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  // Actions
  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function toggleMobileMenu() {
    mobileMenuOpen.value = !mobileMenuOpen.value
  }

  function closeMobileMenu() {
    mobileMenuOpen.value = false
  }

  function checkMobile() {
    isMobile.value = window.innerWidth < 768
    if (!isMobile.value) {
      mobileMenuOpen.value = false
    }
  }

  function setTheme(newTheme) {
    theme.value = newTheme
    localStorage.setItem('hakuriver-theme', newTheme)
    applyTheme()
  }

  function applyTheme() {
    if (isDark.value) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }

  // Initialize theme on store creation
  function init() {
    applyTheme()
    checkMobile()

    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (theme.value === 'system') {
        applyTheme()
      }
    })

    // Listen for resize to check mobile
    window.addEventListener('resize', checkMobile)
  }

  return {
    // State
    sidebarCollapsed,
    mobileMenuOpen,
    isMobile,
    theme,
    // Getters
    isDark,
    // Actions
    toggleSidebar,
    toggleMobileMenu,
    closeMobileMenu,
    checkMobile,
    setTheme,
    init,
  }
})
