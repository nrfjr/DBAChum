<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '@/layouts/AppShell.vue'
import PwaPrompt from '@/components/pwa/PwaPrompt.vue'


const route = useRoute()

const publicRoute = computed(
  () => route.meta.public === true,
)
</script>


<template>
  <RouterView v-if="publicRoute" />

  <AppShell v-else />

  <PwaPrompt />
</template>