<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const title = computed(() =>
  String(route.meta.title ?? 'Module'),
)

const subtitle = computed(() =>
  String(route.meta.subtitle ?? ''),
)
</script>

<template>
  <section class="panel placeholder-page">
    <div class="placeholder-page__badge">
      DBAChum v2
    </div>

    <h2>{{ title }}</h2>

    <p>
      {{ subtitle }}
    </p>

    <div class="placeholder-page__message">
      This module will be implemented in a later milestone.
    </div>
  </section>
</template>