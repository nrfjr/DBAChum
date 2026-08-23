<script setup lang="ts">
import OracleUsersPanel from '@/components/databases/oracle/OracleUsersPanel.vue'

import type { DatabaseEngine } from '@/stores/connections'

defineProps<{
  connectionId: string
  engine: DatabaseEngine
}>()
</script>

<template>
  <OracleUsersPanel
    v-if="engine === 'oracle'"
    :connection-id="connectionId"
  />
</template>
