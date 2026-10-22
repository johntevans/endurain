<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { TrendingUp } from '@lucide/vue'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { FitnessRangeKey } from '@/features/trainingLoad/types'

import FitnessChartCard from '@/features/trainingLoad/components/FitnessChartCard.vue'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Label } from '@/components/ui/label'
import { MetricPill } from '@/components/ui/metric-pill'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { themeColor } from '@/lib/themeColor'
import { useRouteQueryReplacement } from '@/composables/useRouteQuery'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useFitnessQuery } from '@/features/trainingLoad/composables/useTrainingLoad'
import {
  DEFAULT_FITNESS_RANGE,
  FITNESS_RANGES,
  fitnessRangeDates,
  fitnessWeekRows,
  formatSigned,
  formatSignedDecimal,
  formatWhole,
  parseFitnessRange,
  warmupEnd,
} from '@/features/trainingLoad/utils/fitness'
import { localTodayIso, weekOf, weekRangeLabel } from '@/features/trainingLog/utils/trainingLog'

/**
 * Homelab fork: Intervals.icu-style fitness page. Today's Fitness, Fatigue,
 * Form and Ramp, their course over a chosen range, and a weekly table (also
 * the charts' table view). Computed from the cached training loads.
 */
const { t, locale } = useI18n()
const route = useRoute()
const { data: currentUser } = useCurrentUser()

const today = localTodayIso()
const range = ref<FitnessRangeKey>(parseFitnessRange(route.query.range))
useRouteQueryReplacement(
  computed(() => ({ range: range.value === DEFAULT_FITNESS_RANGE ? undefined : range.value })),
)

const query = useFitnessQuery(() => fitnessRangeDates(range.value, today))
const data = computed(() => query.data.value ?? null)
const days = computed(() => data.value?.days ?? [])
const current = computed(() => days.value[days.value.length - 1] ?? null)

// Validated together (scripts/validate_palette.js, light and dark card surfaces).
const FITNESS_COLOR = themeColor('--color-info')
const FATIGUE_COLOR = themeColor('--color-hr')
const FORM_COLOR = themeColor('--color-brand')
const LOAD_COLOR = themeColor('--color-brand-mid')

const dateLabels = computed(() => {
  const format = new Intl.DateTimeFormat(locale.value, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
  return days.value.map((day) => format.format(new Date(`${day.date}T00:00:00Z`)))
})

const fitnessChart = computed<ChartRenderOptions>(() => ({
  kind: 'line',
  labels: dateLabels.value,
  xMaxTicks: 6,
  hoverIndex: true,
  valueFormat: formatWhole,
  series: [
    {
      label: t('trainingLoad.fitness.fitness'),
      data: days.value.map((day) => day.fitness),
      color: FITNESS_COLOR,
    },
    {
      label: t('trainingLoad.fitness.fatigue'),
      data: days.value.map((day) => day.fatigue),
      color: FATIGUE_COLOR,
    },
  ],
}))

const formChart = computed<ChartRenderOptions>(() => ({
  kind: 'line',
  labels: dateLabels.value,
  xMaxTicks: 6,
  hoverIndex: true,
  valueFormat: formatSigned,
  series: [
    {
      label: t('trainingLoad.fitness.form'),
      data: days.value.map((day) => day.form),
      color: FORM_COLOR,
    },
  ],
}))

const loadChart = computed<ChartRenderOptions>(() => ({
  kind: 'bar',
  labels: dateLabels.value,
  xMaxTicks: 6,
  hoverIndex: true,
  valueFormat: formatWhole,
  series: [
    {
      label: t('trainingLoad.label'),
      data: days.value.map((day) => day.load),
      color: LOAD_COLOR,
    },
  ],
}))

const weeks = computed(() =>
  fitnessWeekRows(days.value, currentUser.value?.firstDayOfWeek ?? 'monday').map((row) => ({
    ...row,
    label: weekRangeLabel(
      weekOf(row.start, currentUser.value?.firstDayOfWeek ?? 'monday'),
      locale.value,
    ),
  })),
)

const warmup = computed(() => {
  const end = data.value ? warmupEnd(days.value, data.value.loadsStart) : null
  if (!end || !data.value) {
    return null
  }
  const format = new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeZone: 'UTC' })
  return t('trainingLoad.fitness.warmup', {
    start: format.format(new Date(`${data.value.loadsStart}T00:00:00Z`)),
    end: format.format(new Date(`${end}T00:00:00Z`)),
  })
})
</script>

<template>
  <section class="flex flex-col gap-4">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('trainingLoad.fitness.title') }}</h1>
        <p class="text-hint">{{ t('trainingLoad.fitness.subtitle') }}</p>
      </div>
      <div>
        <Label for="fitness-range" class="sr-only">{{ t('trainingLoad.fitness.range') }}</Label>
        <Select id="fitness-range" v-model="range" class="w-40" data-testid="fitness-range">
          <option v-for="key in FITNESS_RANGES" :key="key" :value="key">
            {{ t(`trainingLoad.fitness.ranges.${key}`) }}
          </option>
        </Select>
      </div>
    </header>

    <div v-if="query.isPending.value" class="flex flex-col gap-3">
      <Skeleton class="h-20 w-full" />
      <Skeleton v-for="index in 2" :key="index" class="h-64 w-full" />
    </div>
    <ErrorState
      v-else-if="query.isError.value"
      :title="t('trainingLoad.fitness.error.title')"
      :description="t('trainingLoad.fitness.error.description')"
      @retry="query.refetch()"
    />
    <EmptyState
      v-else-if="!data?.hasSettings || !current"
      :title="t('trainingLoad.fitness.empty.title')"
      :description="t('trainingLoad.fitness.empty.description')"
    >
      <template #icon>
        <TrendingUp class="size-8" aria-hidden="true" />
      </template>
    </EmptyState>

    <template v-else>
      <Card class="grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="fitness-today">
        <MetricPill
          :label="t('trainingLoad.fitness.fitness')"
          :value="formatWhole(current.fitness)"
          accent="info"
        />
        <MetricPill
          :label="t('trainingLoad.fitness.fatigue')"
          :value="formatWhole(current.fatigue)"
          accent="hr"
        />
        <MetricPill :label="t('trainingLoad.fitness.form')" :value="formatSigned(current.form)" />
        <MetricPill
          :label="t('trainingLoad.fitness.ramp')"
          :value="formatSignedDecimal(current.ramp)"
        />
      </Card>

      <p v-if="warmup" class="text-hint" data-testid="fitness-warmup">{{ warmup }}</p>

      <div class="grid gap-3 lg:grid-cols-2">
        <FitnessChartCard
          class="lg:col-span-2"
          :title="t('trainingLoad.fitness.fitnessChart')"
          :accent-color="FITNESS_COLOR"
          :render="fitnessChart"
        />
        <FitnessChartCard
          :title="t('trainingLoad.fitness.form')"
          :accent-color="FORM_COLOR"
          :render="formChart"
        />
        <FitnessChartCard
          :title="t('trainingLoad.fitness.dailyLoad')"
          :accent-color="LOAD_COLOR"
          :render="loadChart"
        />
      </div>

      <Card class="flex flex-col gap-3">
        <h2 class="text-item-title">{{ t('trainingLoad.fitness.weeks') }}</h2>
        <div class="overflow-x-auto">
          <table class="w-full border-collapse text-body" data-testid="fitness-weeks">
            <thead>
              <tr class="border-b border-border">
                <th scope="col" class="py-2 pe-3 text-start text-caption">
                  {{ t('trainingLoad.fitness.week') }}
                </th>
                <th scope="col" class="px-3 py-2 text-end text-caption">
                  {{ t('trainingLoad.label') }}
                </th>
                <th scope="col" class="px-3 py-2 text-end text-caption">
                  {{ t('trainingLoad.fitness.fitness') }}
                </th>
                <th scope="col" class="px-3 py-2 text-end text-caption">
                  {{ t('trainingLoad.fitness.fatigue') }}
                </th>
                <th scope="col" class="px-3 py-2 text-end text-caption">
                  {{ t('trainingLoad.fitness.form') }}
                </th>
                <th scope="col" class="hidden py-2 ps-3 text-end text-caption sm:table-cell">
                  {{ t('trainingLoad.fitness.ramp') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="week in weeks"
                :key="week.start"
                class="border-b border-border last:border-0"
              >
                <td class="py-2 pe-3 whitespace-nowrap">{{ week.label }}</td>
                <td class="px-3 py-2 text-end tabular-nums">{{ formatWhole(week.load) }}</td>
                <td class="px-3 py-2 text-end tabular-nums">{{ formatWhole(week.fitness) }}</td>
                <td class="px-3 py-2 text-end tabular-nums">{{ formatWhole(week.fatigue) }}</td>
                <td class="px-3 py-2 text-end tabular-nums">{{ formatSigned(week.form) }}</td>
                <td class="hidden py-2 ps-3 text-end tabular-nums sm:table-cell">
                  {{ formatSignedDecimal(week.ramp) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="text-hint">{{ t('trainingLoad.fitness.weeksHint') }}</p>
      </Card>
    </template>
  </section>
</template>
