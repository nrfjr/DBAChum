<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { useConnectionsStore } from '@/stores/connections'
import { useServersStore } from '@/stores/servers'

const query = ref('')
const connectionsStore = useConnectionsStore()
const serversStore = useServersStore()

const connectionCount = computed(() => connectionsStore.connections.length)
const serverCount = computed(() => serversStore.servers.length)

onMounted(() => {
  if (!connectionsStore.connections.length) void connectionsStore.load()
  if (!serversStore.servers.length) void serversStore.load()
})
</script>

<template>
  <section class="page-header records-page-header">
    <div>
      <h1>Records</h1>
      <p>
        Human-readable DBA operational knowledge lives here. Records are separate from the live endpoints DBAChum uses under Settings → Connections.
      </p>
    </div>
  </section>

  <section class="records-hero panel">
    <div class="records-search-shell">
      <input
        v-model="query"
        type="search"
        placeholder="Search hostname, IP, environment, version, username, application or notes..."
        aria-label="Search Records"
      />
      <span>Records persistence and custom fields arrive in the next Records implementation step.</span>
    </div>

    <div class="records-foundation-grid">
      <article>
        <strong>{{ serverCount }}</strong>
        <span>configured servers available to link</span>
      </article>
      <article>
        <strong>{{ connectionCount }}</strong>
        <span>database connections available to link</span>
      </article>
      <article>
        <strong>Flexible</strong>
        <span>credentials, versions, URLs, notes and custom DBA fields</span>
      </article>
    </div>
  </section>

  <section class="records-definition-grid">
    <article class="panel">
      <h2>Records</h2>
      <p>Fast human lookup. A record may link to a live connection, but it does not require one.</p>
      <ul>
        <li>Hostname / IP / environment</li>
        <li>Database or OS version</li>
        <li>Application ownership and operational notes</li>
        <li>Optional username/password fields with mask, reveal and copy UX</li>
      </ul>
    </article>

    <article class="panel">
      <h2>Connections</h2>
      <p>Machine-readable endpoints DBAChum actively uses for monitoring, provisioning, LDAP and SSH operations.</p>
      <RouterLink to="/settings/connections" class="secondary-button">Open Connections</RouterLink>
    </article>
  </section>
</template>
