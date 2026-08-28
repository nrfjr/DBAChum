<script setup lang="ts">
const emit = defineEmits<{
  scroll: [event: Event]
}>()

withDefaults(
  defineProps<{
    loading?: boolean
    empty?: boolean
    emptyMessage?: string
    maxHeight?: string
  }>(),
  {
    loading: false,
    empty: false,
    emptyMessage: 'No rows to display.',
    maxHeight: '34rem',
  },
)
</script>

<template>
  <div v-if="loading" class="reusable-table-state">
    Loading...
  </div>
  <div v-else-if="empty" class="reusable-table-state">
    {{ emptyMessage }}
  </div>
  <div
    v-else
    class="reusable-table-shell"
    :style="{ maxHeight }"
    @scroll="emit('scroll', $event)"
  >
    <table class="reusable-data-table">
      <thead>
        <slot name="header" />
      </thead>
      <tbody>
        <slot />
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.reusable-table-shell {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: .75rem;
}

.reusable-data-table {
  width: 100%;
  border-collapse: collapse;
}

.reusable-data-table :deep(th),
.reusable-data-table :deep(td) {
  padding: .65rem .75rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.reusable-data-table :deep(thead th) {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface);
}

.reusable-data-table :deep(tbody tr:last-child td) {
  border-bottom: 0;
}

.reusable-table-state {
  padding: 1rem;
  border: 1px dashed var(--border);
  border-radius: .75rem;
  color: var(--text-muted);
}
</style>
