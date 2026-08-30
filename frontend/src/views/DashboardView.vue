<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { useUiStore } from '@/stores/ui'
import { useAlertsStore } from '@/stores/alerts'

interface HealthResponse {
  api: string
  mongodb: string
}

const health = ref<HealthResponse | null>(null)
const healthError = ref(false)
const uiStore = useUiStore()
const alertsStore = useAlertsStore()

async function checkHealth() {

  if (!uiStore.isOnline) {
    health.value = null
    healthError.value = false
    return
  }

  watch(
    () => uiStore.isOnline,
    (isOnline) => {
      if (!isOnline) {
        health.value = null
        healthError.value = false
        return
      }

      checkHealth()
    },
  )

  healthError.value = false

  try {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL

    const response = await fetch(`${apiBaseUrl}/health`)

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    health.value = await response.json()
  } catch {
    health.value = null
    healthError.value = true
  }
}

onMounted(async () => {
  await Promise.all([
    checkHealth(),
    alertsStore.loadSummary(),
    alertsStore.load('active').catch(() => []),
  ])
})
</script>

<template>
  <div class="dashboard">
    <section class="metric-grid">
      <article class="metric-card">
        <span class="metric-card__label">
          Databases
        </span>

        <strong class="metric-card__value">
          —
        </strong>

        <span class="metric-card__hint">
          Monitoring not configured
        </span>
      </article>

      <article class="metric-card">
        <span class="metric-card__label">
          Servers
        </span>

        <strong class="metric-card__value">
          —
        </strong>

        <span class="metric-card__hint">
          Inventory not configured
        </span>
      </article>

      <article class="metric-card">
        <span class="metric-card__label">
          Warnings
        </span>

        <strong class="metric-card__value">
          {{ alertsStore.summary.warning }}
        </strong>

        <span class="metric-card__hint">
          Active warning alerts
        </span>
      </article>

      <article class="metric-card">
        <span class="metric-card__label">
          Critical
        </span>

        <strong class="metric-card__value">
          {{ alertsStore.summary.critical }}
        </strong>

        <span class="metric-card__hint">
          Active critical alerts
        </span>
      </article>
    </section>

    <section class="dashboard-grid">
      <article class="panel">
        <div class="panel__header">
          <div>
            <h2>Database health</h2>

            <p>
              Configured databases will appear here.
            </p>
          </div>
        </div>

        <div class="empty-state">
          <div class="empty-state__icon">
            DB
          </div>

          <strong>No databases configured</strong>

          <p>
            Database connection management arrives in a later milestone.
          </p>
        </div>
      </article>

      <article class="panel">
        <div class="panel__header">
          <div>
            <h2>System status</h2>

            <p>
              Weekend 1 foundation
            </p>
          </div>
        </div>

        <div v-if="!uiStore.isOnline" class="status-message">
          Status unknown — device offline.
        </div>

        <div v-else-if="health" class="status-list">
          <div class="status-row">
            <span>FastAPI</span>

            <span class="status status--healthy">
              ● {{ health.api }}
            </span>
          </div>

          <div class="status-row">
            <span>MongoDB</span>

            <span class="status status--healthy">
              ● {{ health.mongodb }}
            </span>
          </div>
        </div>

        <div v-else-if="healthError" class="status-message status-message--error">
          Backend unavailable.
        </div>

        <div v-else class="status-message">
          Checking services...
        </div>

        <button type="button" class="secondary-button" @click="checkHealth">
          Check again
        </button>
      </article>
    </section>

    <section class="panel">
      <div class="panel__header">
        <div>
          <h2>Recent events</h2>

          <p>
            Monitoring activity will appear here.
          </p>
        </div>
      </div>

      <div v-if="alertsStore.items.length" class="dashboard-alert-list">
        <RouterLink
          v-for="alert in alertsStore.items.slice(0, 5)"
          :key="alert.id"
          to="/alerts"
          class="dashboard-alert-row"
        >
          <span class="alert-severity-badge" :class="alert.severity">{{ alert.severity }}</span>
          <div>
            <strong>{{ alert.title }}</strong>
            <small>{{ alert.source_name }}</small>
          </div>
        </RouterLink>
      </div>

      <div v-else class="empty-state empty-state--small">
        <strong>Nothing to report</strong>

        <p>
          No active alerts right now. Enjoy the suspicious calm.
        </p>
      </div>
    </section>
  </div>
</template>