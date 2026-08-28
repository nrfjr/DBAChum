<script setup lang="ts">
import {
  computed,
  onMounted,
} from 'vue'

import {
  useOracleDbaStore,
} from '@/stores/oracleDba'
import ScrollableDataTable from '@/components/common/ScrollableDataTable.vue'

const props = defineProps<{
  connectionId: string
}>()

const oracleStore = useOracleDbaStore()

const storage = computed(
  () =>
    oracleStore.storage[
      props.connectionId
    ],
)

function formatBytes(bytes: number) {
  if (bytes === 0) {
    return '0 B'
  }

  const units = [
    'B',
    'KB',
    'MB',
    'GB',
    'TB',
    'PB',
  ]

  const index = Math.min(
    Math.floor(
      Math.log(bytes) /
        Math.log(1024),
    ),
    units.length - 1,
  )

  return `${
    (
      bytes /
      Math.pow(1024, index)
    ).toFixed(1)
  } ${units[index]}`
}

onMounted(() => {
  oracleStore.loadStorage(
    props.connectionId,
  )
})
</script>

<template>
  <section>
    <div class="utility-toolbar">
      <div>
        <h2>Storage</h2>
        <p>
          Oracle tablespace and recovery
          area usage.
        </p>
      </div>

      <button
        type="button"
        class="secondary-button"
        :disabled="
          oracleStore.loadingStorage
        "
        @click="
          oracleStore.loadStorage(
            connectionId,
          )
        "
      >
        {{
          oracleStore.loadingStorage
            ? 'Refreshing...'
            : 'Refresh'
        }}
      </button>
    </div>

    <p
      v-if="oracleStore.storageError"
      class="login-error"
    >
      {{ oracleStore.storageError }}
    </p>

    <template v-else-if="storage">
      <div
        v-for="warning in storage.warnings"
        :key="warning"
        class="utility-warning"
      >
        {{ warning }}
      </div>

      <section
        v-if="storage.fra"
        class="panel utility-section"
      >
        <h3>Fast Recovery Area</h3>

        <div class="utility-summary">
          <div>
            <span>Used</span>

            <strong>
              {{
                formatBytes(
                  storage.fra.used_bytes,
                )
              }}
            </strong>
          </div>

          <div>
            <span>Limit</span>

            <strong>
              {{
                formatBytes(
                  storage.fra.limit_bytes,
                )
              }}
            </strong>
          </div>

          <div>
            <span>Used %</span>

            <strong>
              {{
                storage.fra.used_percent
                  != null
                    ? `${storage.fra.used_percent}%`
                    : '—'
              }}
            </strong>
          </div>

          <div>
            <span>Reclaimable</span>

            <strong>
              {{
                formatBytes(
                  storage.fra
                    .reclaimable_bytes,
                )
              }}
            </strong>
          </div>
        </div>
      </section>

      <section class="utility-section">
        <h3>Tablespaces</h3>

        <ScrollableDataTable
          v-if="storage.tablespaces_available"
          :empty="storage.tablespaces.length === 0"
          empty-message="No tablespaces returned."
          max-height="34rem"
        >
          <template #header>
              <tr>
                <th>Tablespace</th>
                <th>Type</th>
                <th>Status</th>
                <th>Used</th>
                <th>Capacity</th>
                <th>Usage</th>
              </tr>
          </template>
              <tr
                v-for="
                  tablespace
                  in storage.tablespaces
                "
                :key="tablespace.name"
              >
                <td>
                  {{ tablespace.name }}
                </td>

                <td>
                  {{
                    tablespace.contents
                  }}
                </td>

                <td>
                  {{ tablespace.status }}
                </td>

                <td>
                  {{
                    formatBytes(
                      tablespace.used_bytes,
                    )
                  }}
                </td>

                <td>
                  {{
                    formatBytes(
                      tablespace.capacity_bytes,
                    )
                  }}
                </td>

                <td>
                  {{
                    tablespace.used_percent
                  }}%
                </td>
              </tr>
        </ScrollableDataTable>
      </section>
    </template>
  </section>
</template>