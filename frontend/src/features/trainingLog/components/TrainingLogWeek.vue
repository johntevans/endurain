<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Units } from '@/features/activities/utils/format'
import type {
  QualityDisplay,
  TrainingLogActivity,
  TrainingLogMetric,
  TrainingLogWeek,
} from '@/features/trainingLog/types'

import TrainingLogDay from '@/features/trainingLog/components/TrainingLogDay.vue'
import { Skeleton } from '@/components/ui/skeleton'
import {
  aerobicTotal,
  formatMetricValue,
  joinValue,
  loadTotal,
  metricHasAerobic,
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
  /** Whether quality shows as an amount or as a share of aerobic. */
  qualityDisplay: QualityDisplay
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

const aerobicValue = computed(() => aerobicTotal(weekActivities.value, props.metric))
// The week's aerobic time, all but strength and mobility (time only).
const aerobic = computed(() =>
  metricHasAerobic(props.metric)
    ? joinValue(formatMetricValue(aerobicValue.value, props.metric, props.units, props.swim))
    : null,
)

// The week's quality work (time or distance; elevation has none), as an
// amount or as its share of the aerobic total, per the toggle.
const quality = computed(() => {
  if (!metricHasQuality(props.metric)) {
    return null
  }
  const value = qualityTotal(weekActivities.value, props.metric)
  return props.qualityDisplay === 'percent'
    ? `${qualityPercent(value, aerobicValue.value)}%`
    : joinValue(formatMetricValue(value, props.metric, props.units, props.swim))
})

// Time shows three numbers, more than fit stacked in a row, so it lists them
// one per line; the other metrics keep the large total.
const stats = computed(() =>
  aerobic.value !== null && quality.value !== null
    ? [
        { key: 'total', label: t('trainingLog.stats.total'), value: total.value },
        { key: 'aerobic', label: t('trainingLog.stats.aerobic'), value: aerobic.value },
        { key: 'quality', label: t('trainingLog.stats.quality'), value: quality.value },
      ]
    : null,
)

const label = computed(() => weekRangeLabel(props.week, locale.value))

// The week's training load (features/trainingLoad); null when no activity has one.
const weekLoad = computed(() => loadTotal(weekActivities.value))
</script>

<template>
  <div
    class="grid h-(--tl-row-h) grid-cols-7 grid-rows-[auto_1fr] border-b border-border sm:grid-cols-[8.5rem_repeat(7,minmax(0,1fr))] sm:grid-rows-1 lg:grid-cols-[10rem_repeat(7,minmax(0,1fr))]"
    :data-week="week.start"
    data-testid="training-log-week"
  >
    <div
      class="col-span-7 flex flex-wrap items-baseline justify-between gap-x-2 px-1 pt-2 sm:col-span-1 sm:flex-col sm:justify-start sm:gap-0 sm:pt-4"
    >
      <span class="text-[15px] font-medium whitespace-nowrap text-foreground sm:text-[17px]">{{
        label
      }}</span>
      <span
        v-if="weekLoad !== null && !loading"
        class="text-micro text-muted-foreground"
        data-testid="training-log-week-load"
        >{{ t('trainingLoad.value', { value: weekLoad }) }}</span
      >
      <span
        class="flex basis-full items-baseline gap-3 sm:mt-3 sm:basis-auto sm:flex-col sm:gap-0.5"
        :class="{ 'sm:hidden': stats }"
      >
        <!-- On a phone, time's three numbers need the room the label would take. -->
        <span v-if="!stats" class="text-micro text-muted-foreground">{{
          t(`trainingLog.total.${metric}`)
        }}</span>
        <Skeleton v-if="loading" class="h-5 w-16 sm:h-6" />
        <span
          v-else
          class="text-[15px] font-medium whitespace-nowrap text-foreground sm:text-[20px]"
          data-testid="training-log-week-total"
          >{{ total }}</span
        >
        <span
          v-if="aerobic !== null && !loading"
          class="text-micro whitespace-nowrap text-muted-foreground sm:hidden"
          data-testid="training-log-week-aerobic-short"
          >{{ t('trainingLog.aerobic.short', { value: aerobic }) }}</span
        >
        <span
          v-if="quality !== null && !loading"
          class="text-micro whitespace-nowrap text-muted-foreground sm:hidden"
          data-testid="training-log-week-quality-short"
          >{{ t('trainingLog.quality.short', { value: quality }) }}</span
        >
      </span>
      <dl
        v-if="stats"
        class="hidden w-full flex-col gap-1 sm:mt-3 sm:flex"
        data-testid="training-log-week-stats"
      >
        <div
          v-for="stat in stats"
          :key="stat.key"
          class="flex items-baseline justify-between gap-2 whitespace-nowrap"
        >
          <dt class="text-micro text-muted-foreground">{{ stat.label }}</dt>
          <dd>
            <Skeleton v-if="loading" class="h-5 w-12" />
            <span
              v-else
              class="text-[15px] font-medium text-foreground"
              :data-testid="`training-log-week-stat-${stat.key}`"
              >{{ stat.value }}</span
            >
          </dd>
        </div>
      </dl>
      <span v-else-if="quality !== null" class="hidden flex-col gap-0.5 sm:mt-2.5 sm:flex">
        <span class="text-micro text-muted-foreground">{{ t('trainingLog.stats.quality') }}</span>
        <Skeleton v-if="loading" class="h-5 w-12" />
        <span
          v-else
          class="text-[15px] font-medium text-foreground"
          data-testid="training-log-week-quality"
          >{{ quality }}</span
        >
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
