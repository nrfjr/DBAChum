<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()

const sectionTitle = computed(() => {
  switch (route.name) {
    case 'settings-connections':
      return 'Connections'
    default:
      return 'Settings'
  }
})
</script>

<template>
  <section class="page-header">
    <div>
      <h1>Settings</h1>
      <p>Configure DBAChum without cluttering the DBA workspace.</p>
    </div>
  </section>

  <div class="settings-layout">
    <aside class="settings-nav">
      <RouterLink
        to="/settings/connections"
        class="settings-nav-item"
      >
        Connections
      </RouterLink>

      <div class="settings-nav-item disabled">
        General
        <span>Later</span>
      </div>

      <div class="settings-nav-item disabled">
        Import / Export
        <span>Later</span>
      </div>
    </aside>

    <section class="settings-content">
      <header class="settings-section-header">
        <h2>{{ sectionTitle }}</h2>
      </header>

      <RouterView />
    </section>
  </div>
</template>