
<script setup lang="ts">
import OracleStoragePanel from '@/components/databases/oracle/OracleStoragePanel.vue'
import SqlServerStoragePanel from '@/components/databases/sqlserver/SqlServerStoragePanel.vue'

import MySqlStoragePanel from '@/components/databases/mysql/MySqlStoragePanel.vue'

import type { DatabaseEngine } from '@/stores/connections'

defineProps<{
  connectionId: string
  engine: DatabaseEngine
}>()
</script>

<template>
  <OracleStoragePanel
    v-if="engine === 'oracle'"
    :connection-id="connectionId"
  />

  <SqlServerStoragePanel
    v-else-if="engine === 'sqlserver'"
    :connection-id="connectionId"
  />

  <MySqlStoragePanel
    v-else-if="engine === 'mysql'"
    :connection-id="connectionId"
  />

</template>