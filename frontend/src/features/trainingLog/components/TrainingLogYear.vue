<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Units } from '@/features/activities/utils/format'
import type {
  SportFilter,
  TagFilter,
  TrainingLogMetric,
  TrainingLogWeek,
} from '@/features/trainingLog/types'

import TrainingLogWeekRow from '@/features/trainingLog/components/TrainingLogWeek.vue'
import { Button } from '@/components/ui/button'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import { useTrainingLogWindowQuery } from '@/features/trainingLog/composables/useTrainingLog'
import {
  formatMetricValue,
  groupByDate,
  joinValue,
  matchesSport,
  matchesTag,
  metricHasQuality,
  metricTotal,
  qualityPercent,
  qualityTotal,
  weeksWindow,
} from '@/features/trainingLog/utils/trainingLog'

/**
 * Homelab fork: one year of the training log. It fetches its weeks only once
 * it nears the viewport; until then it is an empty block of the exact height
 * its rows will take, so the page height and every jump target stay right.
 */
const props = defineProps<{
  year: number
  /** The year's weeks, newest first. */
  weeks: readonly TrainingLogWeek[]
  sport: SportFilter
  tag: TagFilter
  metric: TrainingLogMetric
  units: Units
  swim: boolean
  today: string
  firstDate: string
}>()

const { t } = useI18n()

const root = ref<HTMLElement | null>(null)
// Without IntersectionObserver (tests, very old browsers) load straight away.
const nearViewport = ref(typeof IntersectionObserver === 'undefined')
useInfiniteScroll(
  root,
  () => {
    nearViewport.value = true
  },
  { rootMargin: '1500px 0px', enabled: () => !nearViewport.value },
)

const query = useTrainingLogWindowQuery(() => weeksWindow(props.weeks), nearViewport)

const filtered = computed(() =>
  (query.data.value ?? []).filter(
    (activity) =>
      matchesSport(activity.activityType, props.sport) && matchesTag(activity.tags, props.tag),
  ),
)
const byDate = computed(() => groupByDate(filtered.value))
// Days with any activity at all, filtered out or not: those are not rest days.
const activeDates = computed(() => new Set((query.data.value ?? []).map((a) => a.localDate)))

const firstDay = computed(() => `${props.year}-01-01`)
const lastDay = computed(() => `${props.year}-12-31`)
const yearActivities = computed(() =>
  filtered.value.filter(
    (activity) => activity.localDate >= firstDay.value && activity.localDate <= lastDay.value,
  ),
)
const yearTotalValue = computed(() => metricTotal(yearActivities.value, props.metric))
const yearTotal = computed(() =>
  joinValue(formatMetricValue(yearTotalValue.value, props.metric, props.units, props.swim)),
)
const yearQuality = computed(() => {
  if (!metricHasQuality(props.metric)) {
    return null
  }
  const value = qualityTotal(yearActivities.value, props.metric)
  return t('trainingLog.quality.value', {
    value: joinValue(formatMetricValue(value, props.metric, props.units, props.swim)),
    percent: `${qualityPercent(value, yearTotalValue.value)}%`,
  })
})

const loading = computed(() => !nearViewport.value || query.isPending.value)
</script>

<template>
  <section ref="root" :data-tl-year="year" :aria-label="String(year)">
    <header
      class="flex h-(--tl-year-h) items-end justify-between gap-3 border-b border-border pb-2"
    >
      <h2 class="text-[22px] font-semibold text-foreground sm:text-[26px]">{{ year }}</h2>
      <div v-if="query.isError.value" class="flex items-center gap-2 text-hint">
        <span>{{ t('trainingLog.loadError') }}</span>
        <Button size="sm" variant="outline" @click="query.refetch()">{{
          t('trainingLog.retry')
        }}</Button>
      </div>
      <span v-else-if="!loading" class="text-hint" data-testid="training-log-year-total">
        {{ t(`trainingLog.total.${metric}`) }}
        <span class="font-medium text-foreground">{{ yearTotal }}</span>
        <template v-if="yearQuality">
          <span class="hidden sm:inline">
            <span class="mx-1.5" aria-hidden="true">·</span>{{ t('trainingLog.quality.total') }}
            <span class="font-medium text-foreground" data-testid="training-log-year-quality">{{
              yearQuality
            }}</span>
          </span>
        </template>
      </span>
    </header>
    <div data-tl-rows :style="{ height: `calc(var(--tl-row-h) * ${weeks.length})` }">
      <template v-if="nearViewport">
        <TrainingLogWeekRow
          v-for="week in weeks"
          :key="week.start"
          :week="week"
          :by-date="byDate"
          :active-dates="activeDates"
          :metric="metric"
          :units="units"
          :swim="swim"
          :today="today"
          :first-date="firstDate"
          :loading="loading"
        />
      </template>
    </div>
  </section>
</template>
