<script setup lang="ts">
import { computed } from 'vue'
import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'
import type {
  OracleAccessCompareCategory,
  OracleAccessCompareItem,
  OracleAccessGrantSource,
} from '@/stores/oracleDba'

const props = withDefaults(
  defineProps<{
    title: string
    category: OracleAccessCompareCategory
    leftUsername: string
    rightUsername: string
    filter?: string
    open?: boolean
  }>(),
  {
    filter: '',
    open: false,
  },
)

type CompareRow = {
  side: 'common' | 'left' | 'right'
  item: OracleAccessCompareItem
}

function formatSource(source: OracleAccessGrantSource) {
  if (source.kind === 'direct') return 'Direct'
  if (source.kind === 'public') return 'PUBLIC'
  if (source.kind === 'password_file') return 'Password file'
  if (source.via.length) return `via ${source.via.join(' → ')}`
  return source.kind
}

function formatSources(sources: OracleAccessGrantSource[]) {
  if (!sources.length) return '—'
  return sources.map(formatSource).join('; ')
}

const rows = computed<CompareRow[]>(() => [
  ...props.category.common.map((item) => ({ side: 'common' as const, item })),
  ...props.category.left_only.map((item) => ({ side: 'left' as const, item })),
  ...props.category.right_only.map((item) => ({ side: 'right' as const, item })),
])

const filteredRows = computed(() => {
  const term = props.filter.trim().toLowerCase()
  if (!term) return rows.value
  return rows.value.filter((row) =>
    [
      row.item.label,
      row.side,
      formatSources(row.item.left_sources),
      formatSources(row.item.right_sources),
    ].some((value) => value.toLowerCase().includes(term)),
  )
})

function sideLabel(side: CompareRow['side']) {
  if (side === 'common') return 'Common'
  if (side === 'left') return `Only ${props.leftUsername}`
  return `Only ${props.rightUsername}`
}
</script>

<template>
  <details class="compare-category" :open="open || undefined">
    <summary>
      <span>{{ title }}</span>
      <small>
        {{ category.common.length }} common ·
        {{ category.left_only.length }} only {{ leftUsername }} ·
        {{ category.right_only.length }} only {{ rightUsername }}
      </small>
    </summary>

    <div class="compare-category-body">
      <ScrollableDataTable
        :empty="filteredRows.length === 0"
        empty-message="No matching access in this category."
        max-height="28rem"
      >
        <template #header>
          <tr>
            <th>Comparison</th>
            <th>Access</th>
            <th>{{ leftUsername }} source</th>
            <th>{{ rightUsername }} source</th>
            <th>Flag</th>
          </tr>
        </template>
        <tr
          v-for="row in filteredRows"
          :key="`${row.side}-${row.item.key}`"
        >
          <td><strong>{{ sideLabel(row.side) }}</strong></td>
          <td>{{ row.item.label }}</td>
          <td>{{ formatSources(row.item.left_sources) }}</td>
          <td>{{ formatSources(row.item.right_sources) }}</td>
          <td>{{ row.item.powerful ? '⚠ Elevated' : '—' }}</td>
        </tr>
      </ScrollableDataTable>
    </div>
  </details>
</template>

<style scoped>
.compare-category {
  border: 1px solid var(--border);
  border-radius: .75rem;
  overflow: hidden;
}

.compare-category > summary {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: .8rem .9rem;
  cursor: pointer;
  font-weight: 700;
}

.compare-category > summary small {
  color: var(--text-muted);
  font-weight: 400;
  text-align: right;
}

.compare-category-body {
  padding: 0 .85rem .85rem;
}

@media (max-width: 800px) {
  .compare-category > summary {
    align-items: flex-start;
    flex-direction: column;
  }

  .compare-category > summary small {
    text-align: left;
  }
}
</style>
