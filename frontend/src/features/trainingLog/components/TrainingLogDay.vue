<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { Units } from '@/features/activities/utils/format'
import type { TrainingLogActivity, TrainingLogMetric } from '@/features/trainingLog/types'

import ActivityTagBadges from '@/features/activityTags/components/ActivityTagBadges.vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { presentActivityType } from '@/features/activities/utils/activityType'
import { combineMetric, formatDistance, formatElevation } from '@/features/activities/utils/format'
import {
  circleFraction,
  circleStyle,
  clusterScale,
  formatLogDuration,
  formatMetricValue,
  joinValue,
  metricValue,
  sportFamily,
} from '@/features/trainingLog/utils/trainingLog'

/**
 * Homelab fork: one day of the training log. Each activity is a circle sized
 * by the selected metric (several on a day overlap); clicking opens a card
 * with the day's activities and links to each. Below sits the first
 * activity's name, itself a link.
 */
const props = defineProps<{
  /** The day, `YYYY-MM-DD`. */
  date: string
  /** The day's activities that pass the filters, chronological. */
  activities: readonly TrainingLogActivity[]
  metric: TrainingLogMetric
  units: Units
  /** Show distances in pool units (a swim-only view). */
  swim: boolean
  /** Whether to show "Rest" when the day is empty (a past day). */
  rest: boolean
  isToday: boolean
}>()

const { t, locale } = useI18n()

/** Most circles drawn per day; the card lists every activity. */
const MAX_CIRCLES = 3

const circles = computed(() => {
  const scale = clusterScale(Math.min(props.activities.length, MAX_CIRCLES))
  return props.activities.slice(0, MAX_CIRCLES).map((activity) => {
    const value = metricValue(activity, props.metric)
    const fraction = circleFraction(value, props.metric, activity.activityType) * scale
    return {
      activity,
      fraction,
      family: sportFamily(activity.activityType),
      style: circleStyle(activity.tags),
      label: joinValue(formatMetricValue(value, props.metric, props.units, props.swim)),
      // Too small to hold its value legibly: the card still shows it.
      showLabel: fraction >= 0.5,
    }
  })
})

const primary = computed(() => props.activities[0] ?? null)
const primaryLabel = computed(() => {
  if (!primary.value) {
    return ''
  }
  const name = primary.value.name || t('trainingLog.untitled')
  const more = props.activities.length - 1
  return more > 0 ? `${name} ${t('trainingLog.more', { count: more })}` : name
})

const dayLabel = computed(() =>
  new Intl.DateTimeFormat(locale.value, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${props.date}T00:00:00Z`)),
)

const triggerLabel = computed(() =>
  [dayLabel.value, ...circles.value.map((c) => `${c.activity.name}, ${c.label}`)].join('; '),
)

function startTimeLabel(activity: TrainingLogActivity): string {
  // The start time has no offset: parsed as local, it formats back to the
  // activity's own wall-clock time.
  const date = new Date(activity.startTime)
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat(locale.value, { timeStyle: 'short' }).format(date)
}

function detailMetrics(activity: TrainingLogActivity): string[] {
  const parts = [formatLogDuration(activity.movingTime || activity.elapsedTime)]
  if (activity.distance > 0) {
    parts.push(combineMetric(formatDistance(activity.distance, activity.activityType, props.units)))
  }
  if ((activity.elevationGain ?? 0) > 0) {
    parts.push(combineMetric(formatElevation(activity.elevationGain, props.units)))
  }
  if (activity.load !== null) {
    parts.push(t('trainingLoad.value', { value: activity.load }))
  }
  return parts
}
</script>

<template>
  <div class="relative flex min-w-0 flex-col items-center pt-1 sm:pt-3" :data-date="date">
    <div class="flex h-(--tl-circle-zone) w-full items-center justify-center">
      <Popover v-if="circles.length > 0">
        <PopoverTrigger as-child>
          <button
            type="button"
            class="flex items-center justify-center rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :aria-label="triggerLabel"
            data-testid="training-log-day-trigger"
          >
            <span
              v-for="(circle, index) in circles"
              :key="circle.activity.id"
              class="tl-mark flex shrink-0 items-center justify-center text-center font-semibold leading-tight shadow-[0_0_0_2px_var(--color-card)] transition-transform hover:scale-105"
              :class="[`tl-family-${circle.family}`, `tl-style-${circle.style}`]"
              :style="{
                width: `calc(var(--tl-circle) * ${circle.fraction})`,
                height: `calc(var(--tl-circle) * ${circle.fraction})`,
                marginLeft: index > 0 ? `calc(var(--tl-circle) * ${-circle.fraction * 0.3})` : '0',
                zIndex: circles.length - index,
              }"
              :data-style="circle.style"
            >
              <span
                v-if="circle.showLabel"
                class="hidden px-0.5 text-[11px] sm:inline lg:text-[12px]"
                aria-hidden="true"
                >{{ circle.label }}</span
              >
            </span>
          </button>
        </PopoverTrigger>
        <PopoverContent align="center" class="w-80 p-0">
          <div class="border-b border-border px-3 py-2 text-hint">{{ dayLabel }}</div>
          <ul class="divide-y divide-border">
            <li v-for="activity in activities" :key="activity.id" class="flex gap-2.5 px-3 py-2.5">
              <span
                class="tl-mark mt-1 size-3 shrink-0"
                :class="[
                  `tl-family-${sportFamily(activity.activityType)}`,
                  `tl-style-${circleStyle(activity.tags)}`,
                ]"
                aria-hidden="true"
              />
              <div class="flex min-w-0 flex-col gap-0.5">
                <RouterLink
                  :to="{ name: 'activity', params: { id: activity.id } }"
                  class="truncate text-item-title hover:underline"
                  >{{ activity.name || t('trainingLog.untitled') }}</RouterLink
                >
                <span class="text-hint">
                  {{ t(presentActivityType(activity.activityType).labelKey) }}
                  <template v-if="startTimeLabel(activity)">
                    · {{ startTimeLabel(activity) }}</template
                  >
                </span>
                <span class="text-meta text-foreground">{{
                  detailMetrics(activity).join(' · ')
                }}</span>
                <ActivityTagBadges :tags="activity.tags" class="mt-0.5" />
              </div>
            </li>
          </ul>
        </PopoverContent>
      </Popover>
      <span
        v-else-if="rest"
        class="text-micro text-muted-foreground/40 select-none"
        data-testid="training-log-rest"
        >{{ t('trainingLog.rest') }}</span
      >
    </div>
    <RouterLink
      v-if="primary"
      :to="{ name: 'activity', params: { id: primary.id } }"
      class="hidden w-full px-1 text-center text-[11px] leading-snug text-muted-foreground hover:text-foreground hover:underline sm:line-clamp-3"
      >{{ primaryLabel }}</RouterLink
    >
    <span
      v-if="isToday"
      class="tl-today absolute bottom-1.5 left-1/2 -translate-x-1/2"
      :title="t('trainingLog.today')"
      data-testid="training-log-today"
    />
  </div>
</template>
