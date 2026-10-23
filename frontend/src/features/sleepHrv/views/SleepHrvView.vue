<script setup lang="ts">
// Homelab fork: the HRV zone of the health area, modelled on the Resting HR zone.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Activity } from '@lucide/vue'

import type { HealthInterval } from '@/features/health/types'

import SleepHrvChart from '@/features/sleepHrv/components/SleepHrvChart.vue'
import SleepHrvListItem from '@/features/sleepHrv/components/SleepHrvListItem.vue'
import { EmptyState } from '@/components/ui/empty-state'
import { ListPanel } from '@/components/ui/list-panel'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useChartProvider } from '@/composables/useChartProvider'
import { useListPagination } from '@/composables/useListPagination'
import { useRecordsPerPage } from '@/features/config/composables/useRecordsPerPage'
import {
  useSleepHrvPageQuery,
  useSleepHrvWindowQuery,
} from '@/features/sleepHrv/composables/useSleepHrv'

const { t } = useI18n()
const chart = useChartProvider()

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

const listQuery = useSleepHrvPageQuery(page, recordsPerPage, interval)
const windowQuery = useSleepHrvWindowQuery(interval)

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
</script>

<template>
  <section class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('sleepHrv.title') }}</h1>
      <p class="text-body">{{ t('sleepHrv.subtitle') }}</p>
    </header>

    <div class="flex flex-wrap items-center gap-2">
      <div class="ms-auto w-full sm:w-36">
        <Select v-model="interval" :aria-label="t('sleepHrv.interval.label')">
          <option v-for="option in INTERVAL_OPTIONS" :key="option" :value="option">
            {{ t(`health.rhr.interval.${option}`) }}
          </option>
        </Select>
      </div>
    </div>

    <SleepHrvChart v-if="showChart" :entries="chartEntries" />

    <ListPanel
      v-model:page="page"
      :is-loading="isPending"
      :is-error="isError"
      :is-empty="isEmpty"
      :show-header="false"
      :error-title="t('sleepHrv.error.title')"
      :error-description="t('sleepHrv.error.description')"
      :retry-label="t('sleepHrv.error.retry')"
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
          :title="t('sleepHrv.empty.title')"
          :description="t('sleepHrv.empty.description')"
          variant="first-time"
        >
          <template #icon>
            <Activity class="size-8" aria-hidden="true" />
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <li v-for="entry in entries" :key="entry.date">
          <SleepHrvListItem :entry="entry" />
        </li>
      </ul>
    </ListPanel>
  </section>
</template>
