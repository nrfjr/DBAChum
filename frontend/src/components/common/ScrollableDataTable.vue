<script setup lang="ts">
import {
  Comment,
  Fragment,
  computed,
  defineComponent,
  ref,
  type PropType,
  type VNode,
  useSlots,
  watch,
} from 'vue'

const emit = defineEmits<{
  scroll: [event: Event]
}>()

const props = withDefaults(
  defineProps<{
    loading?: boolean
    empty?: boolean
    emptyMessage?: string
    maxHeight?: string
    paginate?: boolean
    initialPageSize?: number
    pageSizes?: number[]
  }>(),
  {
    loading: false,
    empty: false,
    emptyMessage: 'No rows to display.',
    maxHeight: '34rem',
    paginate: true,
    initialPageSize: 10,
    pageSizes: () => [10, 25, 50, 100],
  },
)

const slots = useSlots()
const page = ref(1)
const pageSize = ref(props.initialPageSize)

function flattenRows(nodes: VNode[]): VNode[] {
  const result: VNode[] = []
  for (const node of nodes) {
    if (node.type === Comment) continue
    if (node.type === Fragment && Array.isArray(node.children)) {
      result.push(...flattenRows(node.children as VNode[]))
      continue
    }
    if (node.type === 'tr') result.push(node)
  }
  return result
}

const rows = computed(() => flattenRows((slots.default?.() ?? []) as VNode[]))
const totalRows = computed(() => rows.value.length)
const pageCount = computed(() => Math.max(1, Math.ceil(totalRows.value / pageSize.value)))
const visibleRows = computed(() => {
  if (!props.paginate) return rows.value
  const start = (page.value - 1) * pageSize.value
  return rows.value.slice(start, start + pageSize.value)
})
const rangeStart = computed(() => totalRows.value === 0 ? 0 : (page.value - 1) * pageSize.value + 1)
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, totalRows.value))
const showPagination = computed(() => props.paginate && totalRows.value > Math.min(...props.pageSizes))
const shouldBoundHeight = computed(() => !props.paginate || pageSize.value > 10)

watch([totalRows, pageSize], () => {
  if (page.value > pageCount.value) page.value = pageCount.value
  if (page.value < 1) page.value = 1
})

watch(pageSize, () => {
  page.value = 1
})

const RowRenderer = defineComponent({
  name: 'ScrollableTableRows',
  props: {
    nodes: {
      type: Array as PropType<VNode[]>,
      required: true,
    },
  },
  setup(childProps) {
    return () => childProps.nodes
  },
})
</script>

<template>
  <div v-if="loading" class="reusable-table-state">
    Loading...
  </div>
  <div v-else-if="empty" class="reusable-table-state">
    {{ emptyMessage }}
  </div>
  <template v-else>
    <div
      class="reusable-table-shell"
      :style="{ maxHeight: shouldBoundHeight ? maxHeight : undefined }"
      @scroll="emit('scroll', $event)"
    >
      <table class="reusable-data-table">
        <thead>
          <slot name="header" />
        </thead>
        <tbody>
          <RowRenderer :nodes="visibleRows" />
        </tbody>
      </table>
    </div>

    <div v-if="showPagination" class="reusable-table-pagination">
      <span>Showing {{ rangeStart }}–{{ rangeEnd }} of {{ totalRows }}</span>
      <div class="reusable-table-pagination__controls">
        <label>
          Rows per page
          <select v-model.number="pageSize">
            <option v-for="size in pageSizes" :key="size" :value="size">{{ size }}</option>
          </select>
        </label>
        <button type="button" class="secondary-button compact-button" :disabled="page <= 1" @click="page -= 1">Previous</button>
        <span>Page {{ page }} of {{ pageCount }}</span>
        <button type="button" class="secondary-button compact-button" :disabled="page >= pageCount" @click="page += 1">Next</button>
      </div>
    </div>
  </template>
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
  padding: 1rem;
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

.reusable-table-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  margin-top: .75rem;
  color: var(--text-muted);
  font-size: .875rem;
}

.reusable-table-pagination__controls,
.reusable-table-pagination__controls label {
  display: flex;
  align-items: center;
  gap: .5rem;
}

.reusable-table-pagination__controls select {
  min-width: 4.5rem;
}

@media (max-width: 720px) {
  .reusable-table-pagination {
    align-items: flex-start;
    flex-direction: column;
  }
  .reusable-table-pagination__controls {
    flex-wrap: wrap;
  }
}
</style>
