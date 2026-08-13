import { defineStore } from 'pinia'

type Theme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'dbachum-theme'

function detectTheme(): Theme {
  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY)

  if (storedTheme === 'light' || storedTheme === 'dark') {
    return storedTheme
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: 'light' as Theme,
    sidebarOpen: false,
    isOnline: navigator.onLine,
  }),

  getters: {
    isDark: (state) => state.theme === 'dark',
  },

  actions: {
    initialize() {
      this.theme = detectTheme()
      this.applyTheme()

      this.isOnline = navigator.onLine

      window.addEventListener('online', () => {
           this.setOnline(true)
      })

      window.addEventListener('offline', () => {
           this.setOnline(false)
      })
    },

    setOnline(value: boolean) {
  	this.isOnline = value
    },

    applyTheme() {
      document.documentElement.dataset.theme = this.theme
      localStorage.setItem(THEME_STORAGE_KEY, this.theme)
    },

    toggleTheme() {
      this.theme = this.theme === 'light' ? 'dark' : 'light'
      this.applyTheme()
    },

    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen
    },

    closeSidebar() {
      this.sidebarOpen = false
    },
  },
})