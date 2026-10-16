<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Units } from '@/features/activities/utils/format'
import type {
  TrainingLogActivity,
  TrainingLogMetric,
  TrainingLogWeek,
} from '@/features/trainingLog/types'

import TrainingLogDay from '@/features/trainingLog/components/TrainingLogDay.vue'
import { Skeleton } from '@/components/ui/skeleton'
import {
  formatMetricValue,
  joinValue,
  metricHasQuality,
  metricTotal,
  qualityPercent,
  qualityTotal,
  weekRangeLabel,
} from '@/features/trainingLog/utils/trainingLog'

/**
 * Homelab fork: one week row of the training log. Its height is fixed by the
 * `--tl-row-h` variable, which is what lets the log place unloaded years and
 * jump to any week by arithmetic alone.
 */
const props = defineProps<{
  week: TrainingLogWeek
  /** Filtered activities by local date (may hold other weeks' days too). */
  byDate: ReadonlyMap<string, readonly TrainingLogActivity[]>
  /** Days with any activity, before filtering; only other past days are rest. */
  activeDates: ReadonlySet<string>
  metric: TrainingLogMetric
  units: Units
  swim: boolean
  /** Today, `YYYY-MM-DD` (local). */
  today: string
  /** Days before this show no "Rest" (the log has no data for them). */
  firstDate: string
  loading: boolean
}>()

const { t, locale } = useI18n()

const days = computed(() =>
  props.week.days.map((date) => ({
    date,
    activities: props.byDate.get(date) ?? [],
    rest: date < props.today && date >= props.firstDate && !props.activeDates.has(date),
    isToday: date === props.today,
  })),
)

const weekActivities = computed(() => days.value.flatMap((day) => day.activities))
const totalValue = computed(() => metricTotal(weekActivities.value, props.metric))
const total = computed(() =>
  joinValue(formatMetricValue(totalValue.value, props.metric, props.units, props.swim)),
)

// The week's quality work (time or distance; elevation has none) and its
// share of the total.
const quality = computed(() => {
  if (!metricHasQuality(props.metric)) {
    return null
  }
  const value = qualityTotal(weekActivities.value, props.metric)
  return {
    total: joinValue(formatMetricValue(value, props.metric, props.units, props.swim)),
    percent: `${qualityPercent(value, totalValue.value)}%`,
  }
})

const label = computed(() => weekRangeLabel(props.week, locale.value))
</script>

<template>
  <div
    class="grid h-(--tl-row-h) grid-cols-7 grid-rows-[auto_1fr] border-b border-border sm:grid-cols-[8.5rem_repeat(7,minmax(0,1fr))] sm:grid-rows-1 lg:grid-cols-[10rem_repeat(7,minmax(0,1fr))]"
    :data-week="week.start"
    data-testid="training-log-week"
  >
    <div
      class="col-span-7 flex items-baseline justify-between gap-2 px-1 pt-2 sm:col-span-1 sm:flex-col sm:justify-start sm:gap-0 sm:pt-4"
    >
      <span class="text-[15px] font-medium text-foreground sm:text-[17px]">{{ label }}</span>
      <span class="flex items-baseline gap-2 sm:mt-3 sm:flex-col sm:gap-0.5">
        <span class="text-micro text-muted-foreground">{{ t(`trainingLog.total.${metric}`) }}</span>
        <Skeleton v-if="loading" class="h-5 w-16 sm:h-6" />
        <span
          v-else
          class="text-[15px] font-medium text-foreground sm:text-[20px]"
          data-testid="training-log-week-total"
          >{{ total }}</span
        >
        <span
          v-if="quality && !loading"
          class="text-micro text-muted-foreground sm:hidden"
          data-testid="training-log-week-quality-short"
          >{{ t('trainingLog.quality.short', { percent: quality.percent }) }}</span
        >
      </span>
      <span v-if="quality" class="hidden gap-4 sm:mt-2.5 sm:flex">
        <span class="flex flex-col gap-0.5">
          <span class="text-micro text-muted-foreground">{{ t('trainingLog.quality.total') }}</span>
          <Skeleton v-if="loading" class="h-5 w-12" />
          <span
            v-else
            class="text-[15px] font-medium text-foreground"
            data-testid="training-log-week-quality"
            >{{ quality.total }}</span
          >
        </span>
        <span class="flex flex-col gap-0.5">
          <span class="text-micro text-muted-foreground">{{
            t('trainingLog.quality.percent')
          }}</span>
          <Skeleton v-if="loading" class="h-5 w-10" />
          <span
            v-else
            class="text-[15px] font-medium text-foreground"
            data-testid="training-log-week-quality-percent"
            >{{ quality.percent }}</span
          >
        </span>
      </span>
    </div>
    <TrainingLogDay
      v-for="day in days"
      :key="day.date"
      :date="day.date"
      :activities="day.activities"
      :metric="metric"
      :units="units"
      :swim="swim"
      :rest="day.rest && !loading"
      :is-today="day.isToday"
    />
  </div>
</template>
