import { defineStore } from 'pinia'

import type {
  AccentPreference,
  DensityPreference,
  ThemePreference,
  UserPreferences,
} from '@/stores/auth'


type ResolvedTheme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'dbachum-theme'
const ACCENT_STORAGE_KEY = 'dbachum-accent'
const DENSITY_STORAGE_KEY = 'dbachum-density'

const VALID_ACCENTS: AccentPreference[] = [
  'purple',
  'blue',
  'cyan',
  'green',
  'orange',
  'pink',
]

const VALID_DENSITIES: DensityPreference[] = [
  'comfortable',
  'compact',
]

function storedThemePreference(): ThemePreference {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)

  if (
    stored === 'system'
    || stored === 'light'
    || stored === 'dark'
  ) {
    return stored
  }

  return 'system'
}

function storedAccent(): AccentPreference {
  const stored = localStorage.getItem(
    ACCENT_STORAGE_KEY,
  ) as AccentPreference | null

  return stored && VALID_ACCENTS.includes(stored)
    ? stored
    : 'purple'
}

function storedDensity(): DensityPreference {
  const stored = localStorage.getItem(
    DENSITY_STORAGE_KEY,
  ) as DensityPreference | null

  return stored && VALID_DENSITIES.includes(stored)
    ? stored
    : 'comfortable'
}

function resolveTheme(
  preference: ThemePreference,
): ResolvedTheme {
  if (preference === 'light' || preference === 'dark') {
    return preference
  }

  return window.matchMedia(
    '(prefers-color-scheme: dark)',
  ).matches
    ? 'dark'
    : 'light'
}

export const useUiStore = defineStore('ui', {
  state: () => ({
    themePreference: 'system' as ThemePreference,
    resolvedTheme: 'light' as ResolvedTheme,
    accent: 'purple' as AccentPreference,
    density: 'comfortable' as DensityPreference,
    sidebarOpen: false,
    isOnline: navigator.onLine,
  }),

  getters: {
    isDark: (state) => state.resolvedTheme === 'dark',
  },

  actions: {
    initialize() {
      this.themePreference = storedThemePreference()
      this.accent = storedAccent()
      this.density = storedDensity()
      this.applyAppearance()

      this.isOnline = navigator.onLine

      window.addEventListener('online', () => {
        this.setOnline(true)
      })

      window.addEventListener('offline', () => {
        this.setOnline(false)
      })

      const media = window.matchMedia(
        '(prefers-color-scheme: dark)',
      )

      media.addEventListener('change', () => {
        if (this.themePreference === 'system') {
          this.applyAppearance()
        }
      })
    },

    setOnline(value: boolean) {
      this.isOnline = value
    },

    applyAppearance() {
      this.resolvedTheme = resolveTheme(
        this.themePreference,
      )

      document.documentElement.dataset.theme =
        this.resolvedTheme
      document.documentElement.dataset.accent =
        this.accent
      document.documentElement.dataset.density =
        this.density

      localStorage.setItem(
        THEME_STORAGE_KEY,
        this.themePreference,
      )
      localStorage.setItem(
        ACCENT_STORAGE_KEY,
        this.accent,
      )
      localStorage.setItem(
        DENSITY_STORAGE_KEY,
        this.density,
      )
    },

    applyUserPreferences(
      preferences?: UserPreferences | null,
    ) {
      if (!preferences) return

      this.themePreference = preferences.theme
      this.accent = preferences.accent
      this.density = preferences.density
      this.applyAppearance()
    },

    setThemePreference(value: ThemePreference) {
      this.themePreference = value
      this.applyAppearance()
    },

    setAccent(value: AccentPreference) {
      this.accent = value
      this.applyAppearance()
    },

    setDensity(value: DensityPreference) {
      this.density = value
      this.applyAppearance()
    },

    toggleTheme() {
      this.themePreference = this.isDark
        ? 'light'
        : 'dark'
      this.applyAppearance()
    },

    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen
    },

    closeSidebar() {
      this.sidebarOpen = false
    },
  },
})
