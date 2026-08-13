import { fileURLToPath, URL } from 'node:url'
import { VitePWA } from 'vite-plugin-pwa'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
  vue(),

  vueDevTools(),

  VitePWA({
    registerType: 'prompt',

    includeAssets: [
      'favicon.ico',
      'dbachum.svg',
      'apple-touch-icon-180x180.png',
    ],

    manifest: {
      name: 'DBAChum',
      short_name: 'DBAChum',

      description:
        'Self-hosted database administration and monitoring workspace.',

      theme_color: '#7557c7',
      background_color: '#111115',

      display: 'standalone',

      start_url: '/',
      scope: '/',

      icons: [
        {
          src: 'pwa-64x64.png',
          sizes: '64x64',
          type: 'image/png',
        },
        {
          src: 'pwa-192x192.png',
          sizes: '192x192',
          type: 'image/png',
        },
        {
          src: 'pwa-512x512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'any',
        },
        {
          src: 'maskable-icon-512x512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'maskable',
        },
      ],
    },

    workbox: {
      cleanupOutdatedCaches: true,
      navigateFallback: 'index.html',
    },
  }),
],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
