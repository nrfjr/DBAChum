<script setup lang="ts">
import DatabaseHistoryPanel from '@/components/databases/DatabaseHistoryPanel.vue'
import DatabasePerformancePanel from '@/components/databases/DatabasePerformancePanel.vue'
import type { DatabaseEngine } from '@/stores/connections'

defineProps<{
  connectionId: string
  engine: DatabaseEngine
}>()
</script>

<template>
  <DatabaseHistoryPanel :connection-id="connectionId" />

  <!-- Oracle Top SQL is already part of the collector-backed Metrics feed. -->
  <DatabasePerformancePanel
    v-if="engine !== 'oracle'"
    :connection-id="connectionId"
    :engine="engine"
  />
</template>
