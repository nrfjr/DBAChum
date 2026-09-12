<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import FloatingActionMenu from '@/components/common/FloatingActionMenu.vue'
import { hasPermission } from '@/core/permissions'
import { useAuthStore } from '@/stores/auth'
import { useDatabaseJobsStore, type DatabaseJobItem, type JobOperation } from '@/stores/databaseJobs'
import type { DatabaseEngine } from '@/stores/connections'
import { confirmDialog, showToast } from '@/ui/feedback'

const props = defineProps<{
  connectionId: string
  engine: DatabaseEngine
}>()

const authStore = useAuthStore()
const jobsStore = useDatabaseJobsStore()

const result = computed(() => jobsStore.results[props.connectionId])
const loading = computed(() => Boolean(jobsStore.loading[props.connectionId]))
const error = computed(() => jobsStore.errors[props.connectionId])
const canOperate = computed(() => hasPermission(authStore.user, 'database:operate'))

function hasJobActions(job: DatabaseJobItem) {
  return job.can_run || job.can_enable_disable
}


function formatWhen(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

async function operate(job: DatabaseJobItem, action: JobOperation) {
  if (!canOperate.value) return
  const verb = action === 'run' ? 'run now' : action
  const confirmed = await confirmDialog({
    title: `${verb.charAt(0).toUpperCase()}${verb.slice(1)} job`,
    message: job.name,
    confirmLabel: action === 'run' ? 'Run now' : action === 'enable' ? 'Enable job' : 'Disable job',
    tone: action === 'disable' ? 'warning' : 'default',
  })
  if (!confirmed) return
  try {
    await jobsStore.operate(props.connectionId, job.id, action)
    showToast({ title: `Job ${action === 'run' ? 'started' : action === 'enable' ? 'enabled' : 'disabled'}`, message: job.name, tone: 'success' })
  } catch (cause) {
    showToast({ title: 'Job action failed', message: cause instanceof Error ? cause.message : error.value ?? undefined, tone: 'danger' })
  }
}

onMounted(() => {
  void jobsStore.load(props.connectionId)
})

</script>

<template>
  <section class="utility-section">
    <div class="utility-toolbar">
      <div title="{{ (engine === 'oracle' ? 'Oracle Scheduler and legacy DBMS_JOB.' : engine === 'sqlserver' ? 'SQL Server Agent jobs.' : 'MySQL/MariaDB Event Scheduler.') }}">
        <h2>Jobs</h2>
      </div>
      <button type="button" class="secondary-button refresh-button" :disabled="loading" @click="jobsStore.load(connectionId)">
        {{ loading ? 'Refreshing' : 'Refresh' }}
        <p v-if="loading" class="loading"></p>
      </button>
    </div>

    <p v-if="error" class="login-error">{{ error }}</p>
    <div v-for="warning in result?.warnings ?? []" :key="warning" class="utility-warning">{{ warning }}</div>

    <ScrollableDataTable
      v-if="result"
      :empty="result.items.length === 0"
      :empty-message="result.available ? 'No jobs found.' : 'Jobs are unavailable for this database or login.'"
      max-height="42rem"
    >
      <template #header>
        <tr>
          <th>Job</th>
          <th>Status</th>
          <th>Schedule</th>
          <th>Last run</th>
          <th>Next run</th>
          <th>Owner / Type</th>
          <th v-if="canOperate" class="user-actions-column">Actions</th>
        </tr>
      </template>
      <tr v-for="job in result.items" :key="job.id">
        <td>
          <strong>{{ job.name }}</strong>
          <div v-if="job.detail" class="utility-table-secondary">{{ job.detail }}</div>
        </td>
        <td>
          <span class="workspace-status-pill" :class="job.enabled === false ? 'workspace-status-pill--muted' : ''">
            {{ job.status ?? (job.enabled ? 'Enabled' : 'Disabled') }}
          </span>
        </td>
        <td>{{ job.schedule ?? '—' }}</td>
        <td>{{ formatWhen(job.last_run) }}</td>
        <td>{{ formatWhen(job.next_run) }}</td>
        <td>{{ job.owner ?? '—' }}<template v-if="job.job_type"> · {{ job.job_type }}</template></td>
        <td v-if="canOperate" class="user-actions-cell">
          <FloatingActionMenu v-if="hasJobActions(job)" :label="`Actions for ${job.name}`" :disabled="jobsStore.busy">
            <button v-if="job.can_run" type="button" role="menuitem" @click="operate(job, 'run')">
              <FontAwesomeIcon icon="play" />
              Run now
            </button>
            <button v-if="job.can_enable_disable && job.enabled !== false" type="button" role="menuitem" @click="operate(job, 'disable')">
              <FontAwesomeIcon icon="ban" />
              Disable
            </button>
            <button v-if="job.can_enable_disable && job.enabled === false" type="button" role="menuitem" @click="operate(job, 'enable')">
              <FontAwesomeIcon icon="circle-check" />
              Enable
            </button>
          </FloatingActionMenu>
          <span v-else>—</span>
        </td>
      </tr>
    </ScrollableDataTable>
  </section>
</template>
