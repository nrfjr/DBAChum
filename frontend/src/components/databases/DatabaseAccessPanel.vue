<script setup lang="ts">
import OracleAccessPrivilegesPanel from '@/components/databases/oracle/OracleAccessPrivilegesPanel.vue'
import SqlServerAccessPanel from '@/components/databases/sqlserver/SqlServerAccessPanel.vue'
import MySqlAccessPanel from '@/components/databases/mysql/MySqlAccessPanel.vue'

import type { DatabaseEngine } from '@/stores/connections'

defineProps<{
  connectionId: string
  engine: DatabaseEngine
}>()
</script>

<template>
  <OracleAccessPrivilegesPanel
    v-if="engine === 'oracle'"
    :connection-id="connectionId"
  />
  <SqlServerAccessPanel
    v-else-if="engine === 'sqlserver'"
    :connection-id="connectionId"
  />
  <MySqlAccessPanel
    v-else-if="engine === 'mysql'"
    :connection-id="connectionId"
  />
</template>
