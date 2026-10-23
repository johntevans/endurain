<script setup lang="ts">
// Homelab fork: one health zone per nightly metric (routes health-hrv and
// health-rhr), modelled on upstream's Resting HR zone.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { HealthInterval } from '@/features/health/types'
import type { NightlyMetricKind } from '@/features/sleepMetrics/types'

import NightlyMetricChart from '@/features/sleepMetrics/components/NightlyMetricChart.vue'
import NightlyMetricListItem from '@/features/sleepMetrics/components/NightlyMetricListItem.vue'
import { EmptyState } from '@/components/ui/empty-state'
import { ListPanel } from '@/components/ui/list-panel'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useChartProvider } from '@/composables/useChartProvider'
import { useListPagination } from '@/composables/useListPagination'
import { useRecordsPerPage } from '@/features/config/composables/useRecordsPerPage'
import { NIGHTLY_METRICS } from '@/features/sleepMetrics/metrics'
import {
  useNightlyMetricPageQuery,
  useNightlyMetricWindowQuery,
} from '@/features/sleepMetrics/composables/useSleepMetrics'

const props = defineProps<{
  kind: NightlyMetricKind
}>()

const { t } = useI18n()
const chart = useChartProvider()

const metric = computed(() => NIGHTLY_METRICS[props.kind])
const key = computed(() => metric.value.i18nKey)

/** Selectable windows, in display order. */
const INTERVAL_OPTIONS: HealthInterval[] = [
  'last_7_days',
  'last_30_days',
  'last_90_days',
  'last_year',
  'all_time',
]

// 30 days by default: a week is too short to see a trend against the range.
const interval = ref<HealthInterval>('last_30_days')
const page = ref(1)
const { recordsPerPage } = useRecordsPerPage()

const kind = computed(() => props.kind)
const listQuery = useNightlyMetricPageQuery(kind, page, recordsPerPage, interval)
const windowQuery = useNightlyMetricWindowQuery(kind, interval)

const entries = computed(() => listQuery.data.value?.records ?? [])
const totalCount = computed(() => listQuery.data.value?.total ?? 0)
const chartEntries = computed(() => windowQuery.data.value?.records ?? [])

const { totalPages, reset: resetPage } = useListPagination(page, totalCount, recordsPerPage)

const isPending = computed(() => listQuery.isPending.value)
const isError = computed(() => listQuery.isError.value)
const isEmpty = computed(() => !isPending.value && !isError.value && entries.value.length === 0)

const showChart = computed(
  () => chart.isAvailable && !windowQuery.isError.value && chartEntries.value.length > 1,
)

watch(interval, resetPage)
watch(kind, () => {
  interval.value = 'last_30_days'
  resetPage()
})
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t(`sleepMetrics.${key}.title`) }}</h1>
      <p class="text-body">{{ t(`sleepMetrics.${key}.subtitle`) }}</p>
    </header>

    <div class="flex flex-wrap items-center gap-2">
      <div class="ms-auto w-full sm:w-36">
        <Select v-model="interval" :aria-label="t('sleepMetrics.interval.label')">
          <option v-for="option in INTERVAL_OPTIONS" :key="option" :value="option">
            {{ t(`health.rhr.interval.${option}`) }}
          </option>
        </Select>
      </div>
    </div>

    <NightlyMetricChart v-if="showChart" :kind="kind" :entries="chartEntries" />

    <ListPanel
      v-model:page="page"
      :is-loading="isPending"
      :is-error="isError"
      :is-empty="isEmpty"
      :show-header="false"
      :error-title="t(`sleepMetrics.${key}.errorTitle`)"
      :error-description="t('sleepMetrics.error.description')"
      :retry-label="t('sleepMetrics.error.retry')"
      paginated
      :total-pages="totalPages"
      @retry="listQuery.refetch()"
    >
      <template #loading>
        <div class="divide-y divide-border" aria-busy="true">
          <div v-for="n in 6" :key="n" class="px-4 py-3">
            <Skeleton class="h-4 w-1/4" />
            <Skeleton class="mt-2 h-3 w-1/3" />
          </div>
        </div>
      </template>

      <template #empty>
        <EmptyState
          :title="t(`sleepMetrics.${key}.emptyTitle`)"
          :description="t('sleepMetrics.empty.description')"
          variant="first-time"
        >
          <template #icon>
            <component :is="metric.icon" class="size-8" aria-hidden="true" />
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <li v-for="entry in entries" :key="entry.date">
          <NightlyMetricListItem :kind="kind" :entry="entry" />
        </li>
      </ul>
    </ListPanel>
  </section>
</template>
