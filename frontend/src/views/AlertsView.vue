<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAlertsStore, type AlertSeverity } from '@/stores/alerts'

const alertsStore = useAlertsStore()
const router = useRouter()

const statusFilter = ref<'active' | 'resolved' | 'all'>('active')
const severityFilter = ref<'' | AlertSeverity>('')
const clearingId = ref<string | null>(null)
let refreshTimer: ReturnType<typeof setInterval> | undefined

const hasResolved = computed(() => alertsStore.items.some((item) => item.status === 'resolved'))

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

function formatDate(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date)
}

async function refresh() {
  await Promise.all([
    alertsStore.load(statusFilter.value, severityFilter.value),
    alertsStore.loadSummary(),
  ])
}

async function clearAlert(id: string) {
  clearingId.value = id
  try {
    await alertsStore.clear(id)
  } finally {
    clearingId.value = null
  }
}

async function clearResolved() {
  if (!window.confirm('Clear all resolved alerts from the Alert Center?')) return
  await alertsStore.clearResolved()
  await refresh()
}

function openSource(sourceType: string, sourceId: string, history = false) {
  if (sourceType === 'database') {
    router.push({
      name: 'database-detail',
      params: { id: sourceId },
      query: history ? { tab: 'history' } : undefined,
    })
  } else if (sourceType === 'server') {
    router.push({ name: 'server-detail', params: { id: sourceId } })
  }
}

onMounted(async () => {
  await refresh()
  refreshTimer = setInterval(() => {
    void refresh()
  }, 30_000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <section class="alerts-page">
    <div class="page-header">
      <div>
        <h1>Alerts</h1>
        <p>Collector-backed warnings and incidents. Clearing is real: resolved alerts are removed, while active alerts stay suppressed until the condition recovers.</p>
      </div>

      <button type="button" class="secondary-button" :disabled="alertsStore.loading" @click="refresh">
        {{ alertsStore.loading ? 'Refreshing...' : 'Refresh' }}
      </button>
    </div>

    <section class="alert-summary-grid">
      <article class="alert-summary-card critical">
        <span>Critical</span>
        <strong>{{ alertsStore.summary.critical }}</strong>
        <small>Active now</small>
      </article>
      <article class="alert-summary-card warning">
        <span>Warning</span>
        <strong>{{ alertsStore.summary.warning }}</strong>
        <small>Active now</small>
      </article>
      <article class="alert-summary-card">
        <span>Active</span>
        <strong>{{ alertsStore.summary.active }}</strong>
        <small>Needs attention</small>
      </article>
      <article class="alert-summary-card">
        <span>Resolved</span>
        <strong>{{ alertsStore.summary.resolved }}</strong>
        <small>Can be cleared</small>
      </article>
    </section>

    <div class="alert-toolbar">
      <div class="alert-filter-group" role="group" aria-label="Alert status">
        <button type="button" :class="{ active: statusFilter === 'active' }" @click="statusFilter = 'active'; refresh()">Active</button>
        <button type="button" :class="{ active: statusFilter === 'resolved' }" @click="statusFilter = 'resolved'; refresh()">Resolved</button>
        <button type="button" :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'; refresh()">All</button>
      </div>

      <div class="alert-toolbar-right">
        <select v-model="severityFilter" aria-label="Filter alerts by severity" @change="refresh">
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
        </select>
        <button v-if="hasResolved || alertsStore.summary.resolved" type="button" class="secondary-button" @click="clearResolved">
          Clear resolved
        </button>
      </div>
    </div>

    <p v-if="alertsStore.error" class="login-error">{{ alertsStore.error }}</p>

    <div v-if="alertsStore.loading && alertsStore.items.length === 0" class="database-empty-state">
      <h2>Loading alerts...</h2>
    </div>

    <div v-else-if="alertsStore.items.length === 0" class="database-empty-state">
      <h2>{{ statusFilter === 'active' ? 'No active alerts' : 'Nothing here' }}</h2>
      <p>{{ statusFilter === 'active' ? 'The collector is not reporting any persisted warning or critical conditions.' : 'No alerts match the selected filters.' }}</p>
    </div>

    <div v-else class="alert-list">
      <article
        v-for="alert in alertsStore.items"
        :key="alert.id"
        class="alert-card"
        :class="[`alert-card--${alert.severity}`, `alert-card--${alert.status}`]"
      >
        <div class="alert-card-main">
          <div class="alert-card-heading">
            <span class="alert-severity-badge" :class="alert.severity">{{ alert.severity }}</span>
            <span v-if="alert.status === 'resolved'" class="alert-status-badge">Resolved</span>
            <strong>{{ alert.title }}</strong>
          </div>

          <p>{{ alert.message }}</p>

          <div class="alert-metadata">
            <span><strong>{{ alert.source_name }}</strong> · {{ alert.source_type }}</span>
            <span>First seen {{ formatDate(alert.first_seen_at) }}</span>
            <span>Last seen {{ formatDate(alert.last_seen_at) }}</span>
            <span v-if="alert.resolved_at">Resolved {{ formatDate(alert.resolved_at) }}</span>
          </div>
        </div>

        <div class="alert-card-actions">
          <button
            v-if="alert.source_type === 'database'"
            type="button"
            class="secondary-button"
            @click="openSource(alert.source_type, alert.source_id, true)"
          >
            View history
          </button>
          <button
            v-if="alert.source_type === 'database' || alert.source_type === 'server'"
            type="button"
            class="secondary-button"
            @click="openSource(alert.source_type, alert.source_id)"
          >
            Open {{ alert.source_type }}
          </button>
          <button
            type="button"
            class="secondary-button alert-clear-button"
            :disabled="clearingId === alert.id"
            @click="clearAlert(alert.id)"
          >
            {{ clearingId === alert.id ? 'Clearing...' : 'Clear' }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>
