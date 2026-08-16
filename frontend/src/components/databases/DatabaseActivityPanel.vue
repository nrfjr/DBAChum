<script setup lang="ts">
import OracleActivityPanel from '@/components/databases/oracle/OracleActivityPanel.vue'
// import SqlServerActivityPanel from '@/components/databases/sqlserver/SqlServerActivityPanel.vue'
// import MySqlActivityPanel from '@/components/databases/mysql/MySqlActivityPanel.vue'

import type { DatabaseEngine } from '@/stores/connections'

defineProps<{
  connectionId: string
  engine: DatabaseEngine
}>()
</script>

<template>
  <OracleActivityPanel
    v-if="engine === 'oracle'"
    :connection-id="connectionId"
  />

  <SqlServerActivityPanel
    v-else-if="engine === 'sqlserver'"
    :connection-id="connectionId"
  />

  <MySqlActivityPanel
    v-else-if="engine === 'mysql'"
    :connection-id="connectionId"
  />
</template>