<script setup lang="ts">
import { useRegisterSW } from 'virtual:pwa-register/vue'

const {
  offlineReady,
  needRefresh,
  updateServiceWorker,
} = useRegisterSW()

function close() {
  offlineReady.value = false
  needRefresh.value = false
}

async function update() {
  await updateServiceWorker(true)
}
</script>

<template>
  <div
    v-if="offlineReady || needRefresh"
    class="pwa-prompt"
    role="status"
  >
    <div class="pwa-prompt__content">
      <strong v-if="needRefresh">
        DBAChum update available
      </strong>

      <strong v-else>
        DBAChum is ready offline
      </strong>

      <p v-if="needRefresh">
        A newer version of the application is ready.
      </p>

      <p v-else>
        The application shell can now open without a network connection.
      </p>
    </div>

    <div class="pwa-prompt__actions">
      <button
        v-if="needRefresh"
        type="button"
        class="primary-button"
        @click="update"
      >
        Update
      </button>

      <button
        type="button"
        class="secondary-button"
        @click="close"
      >
        Dismiss
      </button>
    </div>
  </div>
</template>