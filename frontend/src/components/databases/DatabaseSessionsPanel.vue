<script setup lang="ts">
import OracleSessionsPanel from '@/components/databases/oracle/OracleSessionsPanel.vue'
import SqlServerSessionsPanel from '@/components/databases/sqlserver/SqlServerSessionsPanel.vue'
import MySqlSessionsPanel from '@/components/databases/mysql/MySqlSessionsPanel.vue'

import type { DatabaseEngine } from '@/stores/connections'

defineProps<{
  connectionId: string
  engine: DatabaseEngine
}>()
</script>

<template>
  <OracleSessionsPanel
    v-if="engine === 'oracle'"
    :connection-id="connectionId"
  />

  <SqlServerSessionsPanel
    v-else-if="engine === 'sqlserver'"
    :connection-id="connectionId"
  />

  <MySqlSessionsPanel
    v-else-if="engine === 'mysql'"
    :connection-id="connectionId"
  />
</template>