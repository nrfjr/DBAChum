<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status?: string | null
  warnings?: string[] | null
  error?: string | null
}>()

const uniqueWarnings = computed(() => {
  const seen = new Set<string>()
  const result: string[] = []

  for (const warning of props.warnings ?? []) {
    const normalized = String(warning).trim()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    result.push(normalized)
  }

  return result
})
</script>

<template>
  <div v-if="error" class="login-error database-monitoring-notice">
    <strong>Monitoring unavailable.</strong>
    <div>{{ error }}</div>
  </div>

  <div
    v-else-if="status === 'limited' && uniqueWarnings.length"
    class="utility-warning database-monitoring-notice"
  >
    <strong>Partial monitoring</strong>
    <div>
      DBAChum is showing the metrics this server and login exposed. Unavailable
      values remain — instead of being reported as zero.
    </div>
    <ul>
      <li v-for="warning in uniqueWarnings" :key="warning">
        {{ warning }}
      </li>
    </ul>
  </div>
</template>
