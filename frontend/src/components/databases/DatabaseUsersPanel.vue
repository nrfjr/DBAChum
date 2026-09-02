<script setup lang="ts">
import OracleUsersPanel from '@/components/databases/oracle/OracleUsersPanel.vue'
import SqlServerUsersPanel from '@/components/databases/sqlserver/SqlServerUsersPanel.vue'

import type { DatabaseEngine } from '@/stores/connections'

defineProps<{
  connectionId: string
  engine: DatabaseEngine
  active?: boolean
}>()
</script>

<template>
  <OracleUsersPanel
    v-if="engine === 'oracle'"
    :connection-id="connectionId"
    :active="active"
  />
  <SqlServerUsersPanel
    v-else-if="engine === 'sqlserver'"
    :connection-id="connectionId"
  />
</template>
