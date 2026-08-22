<script setup lang="ts">
import {
  computed,
  onMounted,
  onUnmounted,
  ref,
} from 'vue'

import VChart from 'vue-echarts'

import '@/charts/echarts'

import {
  useDatabaseMetricsStore,
  type DatabaseMetricSample,
} from '@/stores/databaseMetrics'

import {
  useUiStore,
} from '@/stores/ui'


const props = defineProps<{
  connectionId: string
}>()


const metricsStore =
  useDatabaseMetricsStore()

const uiStore =
  useUiStore()


type HistoryRange =
  | 1
  | 6
  | 24
  | 168


type HistoryMetric =
  | 'active'
  | 'connections'
  | 'blocked'
  | 'latency'


const hours =
  ref<HistoryRange>(24)


const metric =
  ref<HistoryMetric>('active')

let refreshTimer:
  ReturnType<typeof setInterval>
  | undefined


const history = computed(
  () =>
    metricsStore.histories[
    props.connectionId
    ],
)

const localTimeFormatter =
  new Intl.DateTimeFormat(
    undefined,
    {
      hour: '2-digit',
      minute: '2-digit',
    },
  )


const localDateTimeFormatter =
  new Intl.DateTimeFormat(
    undefined,
    {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    },
  )


function parseUtcTimestamp(
  value: string,
): number {
  const timestamp =
    value.replace(
      /(\.\d{3})\d+/,
      '$1',
    )

  const hasTimezone =
    /(?:Z|[+-]\d{2}:\d{2})$/i.test(
      timestamp,
    )

  return Date.parse(
    hasTimezone
      ? timestamp
      : `${timestamp}Z`,
  )
}

const rangeLabel = computed(() => {
  if (hours.value === 1) {
    return '1 hour'
  }

  if (hours.value === 168) {
    return '7 days'
  }

  return `${hours.value} hours`
})


const latestSampleTime = computed(() => {
  const items =
    history.value?.items ?? []

  const latest =
    items[items.length - 1]

  if (!latest) {
    return '—'
  }

  const timestamp =
    parseUtcTimestamp(
      latest.collected_at,
    )

  if (!Number.isFinite(timestamp)) {
    return '—'
  }

  return localDateTimeFormatter.format(
    timestamp,
  )
})

const metricLabel = computed(() => {
  switch (metric.value) {
    case 'active':
      return 'Active sessions'

    case 'connections':
      return 'Connections'

    case 'blocked':
      return 'Blocked sessions'

    case 'latency':
      return 'Response latency'
  }

  return 'Metric'
})


const metricAxisLabel = computed(() => {
  if (metric.value === 'latency') {
    return 'Latency (ms)'
  }

  return metricLabel.value
})

type MetricPoint = [
  number,
  number | null,
]


function getMetricValue(
  item: DatabaseMetricSample,
): number | null {
  if (
    item.status === 'unreachable'
  ) {
    return null
  }

  switch (metric.value) {
    case 'active':
      return item.active

    case 'connections':
      return item.connections

    case 'blocked':
      return item.blocked

    case 'latency':
      return item.response_time_ms
  }
}


const metricSeriesData =
  computed<MetricPoint[]>(() => {
    const items =
      history.value?.items ?? []

    const intervalSeconds =
      history.value
        ?.sample_interval_seconds
      ?? 60

    const expectedIntervalMs =
      Math.max(
        intervalSeconds * 1000,
        1000,
      )

    const gapThresholdMs =
      expectedIntervalMs * 2.5

    const points:
      MetricPoint[] = []

    let previousTimestamp:
      number | null = null

    for (const item of items) {
      const timestamp =
        parseUtcTimestamp(
          item.collected_at,
        )

      if (
        !Number.isFinite(timestamp)
      ) {
        continue
      }

      if (
        previousTimestamp !== null &&
        timestamp -
        previousTimestamp >
        gapThresholdMs
      ) {
        const gapTimestamp =
          previousTimestamp +
          (
            timestamp -
            previousTimestamp
          ) / 2

        points.push([
          gapTimestamp,
          null,
        ])
      }

      points.push([
        timestamp,
        getMetricValue(item),
      ])

      previousTimestamp =
        timestamp
    }

    return points
  })

function cssVariable(
  name: string,
) {
  return getComputedStyle(
    document.documentElement,
  )
    .getPropertyValue(name)
    .trim()
}


const chartOption = computed(() => {
  // Make theme changes reactive.
  void uiStore.theme

  const textColor =
    cssVariable(
      '--color-text-secondary',
    )

  const purple =
    cssVariable(
      '--color-purple',
    )

  return {
    animation: false,

    useUTC: false,

    grid: {
      left: 55,
      right: 24,
      top: 25,
      bottom: 75,
    },

    tooltip: {
      trigger: 'axis',
    },

    xAxis: {
      type: 'time',

      axisLabel: {
        color: textColor,

        formatter: (
          value: number,
        ) =>
          localTimeFormatter.format(
            value,
          ),
      }
    },

    yAxis: {
      type: 'value',

      minInterval:
        metric.value === 'latency'
          ? undefined
          : 1,

      name: metricAxisLabel.value,

      axisLabel: {
        color: textColor,

        formatter:
          metric.value === 'latency'
            ? '{value} ms'
            : '{value}',
      }
    },

    dataZoom: [
      {
        type: 'inside',
      },
      {
        type: 'slider',
        height: 22,
        bottom: 15,
      },
    ],

    series: [
      {
        name: metricLabel.value,
        type: 'line',

        showSymbol: false,
        smooth: false,

        connectNulls: false,

        lineStyle: {
          width: 2,
          color: purple,
        },

        itemStyle: {
          color: purple,
        },

        data: metricSeriesData.value,
      },
    ],
  }
})


async function loadHistory(
  selectedHours: HistoryRange,
) {
  hours.value =
    selectedHours

  try {
    await metricsStore.loadHistory(
      props.connectionId,
      selectedHours,
    )
  } catch {
    // The store exposes the request error for the panel to render.
  }
}


onMounted(async () => {
  await loadHistory(
    hours.value,
  )

  refreshTimer = setInterval(
    () => {
      void loadHistory(
        hours.value,
      )
    },
    60_000,
  )
})


onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(
      refreshTimer
    )
  }
})
</script>


<template>
  <section class="database-history-panel">
    <div class="utility-toolbar">
      <div>
        <h2>Historical monitoring</h2>

        <p>
          Active database sessions collected
          by DBAChum over time.
        </p>
      </div>

      <button type="button" class="secondary-button" :disabled="metricsStore.loading" @click="
        loadHistory(hours)
        ">
        {{
          metricsStore.loading
            ? 'Refreshing...'
            : 'Refresh'
        }}
      </button>
    </div>
    <div class="database-history-metrics">
      <button type="button" :class="{
        active: metric === 'active',
      }" @click="metric = 'active'">
        Active
      </button>

      <button type="button" :class="{
        active: metric === 'connections',
      }" @click="metric = 'connections'">
        Connections
      </button>

      <button type="button" :class="{
        active: metric === 'blocked',
      }" @click="metric = 'blocked'">
        Blocked
      </button>

      <button type="button" :class="{
        active: metric === 'latency',
      }" @click="metric = 'latency'">
        Latency
      </button>
    </div>
    <div class="database-history-ranges">
      <button type="button" :class="{
        active: hours === 1,
      }" @click="loadHistory(1)">
        1h
      </button>

      <button type="button" :class="{
        active: hours === 6,
      }" @click="loadHistory(6)">
        6h
      </button>

      <button type="button" :class="{
        active: hours === 24,
      }" @click="loadHistory(24)">
        24h
      </button>

      <button type="button" :class="{
        active: hours === 168,
      }" @click="loadHistory(168)">
        7d
      </button>
    </div>

    <p v-if="metricsStore.error" class="login-error">
      {{ metricsStore.error }}
    </p>

    <div v-else-if="
      metricsStore.loading &&
      !history
    " class="empty-state">
      Loading historical metrics...
    </div>

    <div v-else-if="
      !history ||
      history.items.length === 0
    " class="database-empty-state">
      <h2>No historical samples yet</h2>

      <p>
        DBAChum has not collected metrics
        for this time range.
      </p>
    </div>

    <template v-else>
      <div class="database-history-summary">
        <span>
          Samples
          <strong>
            {{ history.count }}
          </strong>
        </span>

        <span>
          Range
          <strong>
            {{ rangeLabel }}
          </strong>
        </span>

        <span>
          Latest
          <strong>
            {{ latestSampleTime }}
          </strong>
        </span>
      </div>

      <VChart class="database-history-chart" :option="chartOption" autoresize />
    </template>
  </section>
</template>