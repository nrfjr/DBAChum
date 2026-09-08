<script setup lang="ts">
import { dismissToast, toastState } from '@/ui/feedback'
</script>

<template>
  <Teleport to="body">
    <div class="app-toast-stack" aria-live="polite" aria-atomic="false">
      <article v-for="toast in toastState.items" :key="toast.id" class="app-toast" :class="`app-toast--${toast.tone}`">
        <div>
          <strong>{{ toast.title }}</strong>
          <p v-if="toast.message">{{ toast.message }}</p>
        </div>
        <button type="button" aria-label="Dismiss notification" @click="dismissToast(toast.id)">×</button>
      </article>
    </div>
  </Teleport>
</template>
