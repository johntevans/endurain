<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Activity, ActivityLap } from '@/features/activities/types'
import type { Units } from '@/features/activities/utils/format'
import type { LapTotals } from '@/features/lapIntensity/utils/intervals'

import {
  activityTypeIsRunning,
  activityTypeIsWalking,
  activityTypeUsesPace,
} from '@/features/activities/utils/activityType'
import {
  cadenceUnitLabel,
  combineMetric,
  formatDistance,
  formatElevation,
  formatHmsDuration,
  presentCadence,
} from '@/features/activities/utils/format'
import { formatLapTempo } from '@/features/activities/utils/metrics'
import { useActivityLapIntensity } from '@/features/lapIntensity/composables/useLapIntensity'
import { groupWorkIntervals, totalLaps } from '@/features/lapIntensity/utils/intervals'

/**
 * Homelab fork: the activity's work intervals, laid out like Garmin's
 * Intervals tab filtered to the work steps. Each run of consecutive work laps
 * gets a summary row, followed by its laps when there is more than one, and a
 * total over every interval closes the table.
 */
const props = defineProps<{
  laps: ActivityLap[]
  activity: Activity
  units: Units
}>()

const { t } = useI18n()

// The owner's intensity corrections decide where intervals start and end.
const { apply: applyLapIntensity } = useActivityLapIntensity(() => props.activity)
const grouped = computed(() => groupWorkIntervals(applyLapIntensity(props.laps)))

const activityType = computed(() => props.activity.activityType)
const tempoLabelKey = computed(() =>
  activityTypeUsesPace(activityType.value)
    ? 'activities.metrics.avgPace'
    : 'activities.metrics.avgSpeed',
)
const showGap = computed(
  () =>
    (activityTypeIsRunning(activityType.value) || activityTypeIsWalking(activityType.value)) &&
    grouped.value.total.gapSpeed !== null,
)
const showElevation = computed(() => grouped.value.total.ascent !== null)

interface Row {
  key: string
  kind: 'interval' | 'lap' | 'total'
  interval: string
  lap: string
  time: string
  cumulativeTime: string
  distance: string
  tempo: string
  gap: string
  avgHr: string
  maxHr: string
  elevation: string
  cadence: string
}

/**
 * Formats a duration to the tenth of a second, as Garmin does, so a split
 * interval's laps visibly add up to it (7:01.4 + 2:58.6 = 10:00.0).
 */
function formatTenths(seconds: number): string {
  const tenths = Math.round(seconds * 10)
  return `${formatHmsDuration(Math.floor(tenths / 10))}.${tenths % 10}`
}

/** Formats one set of totals into the row's metric cells. */
function metricCells(totals: LapTotals) {
  const type = activityType.value
  return {
    time: formatTenths(totals.elapsedTime),
    distance: combineMetric(formatDistance(totals.distance, type, props.units)),
    tempo: formatLapTempo(totals.avgPace, totals.avgSpeed, type, props.units),
    gap: formatLapTempo(totals.gapPace, totals.gapSpeed, type, props.units),
    avgHr: totals.avgHeartRate === null ? '--' : `${Math.round(totals.avgHeartRate)} bpm`,
    maxHr: totals.maxHeartRate === null ? '--' : `${Math.round(totals.maxHeartRate)} bpm`,
    elevation:
      totals.ascent === null ? '--' : combineMetric(formatElevation(totals.ascent, props.units)),
    cadence:
      totals.avgCadence === null
        ? '--'
        : `${Math.round(presentCadence(totals.avgCadence, type))} ${cadenceUnitLabel(type)}`,
  }
}

const rows = computed<Row[]>(() => {
  const result: Row[] = []
  for (const interval of grouped.value.intervals) {
    const single = interval.laps.length === 1
    result.push({
      key: `interval-${interval.number}`,
      kind: 'interval',
      interval: String(interval.number),
      // A one-lap interval is its lap: name the lap on the summary row
      // instead of repeating the same numbers beneath it.
      lap: single ? String(interval.laps[0]!.lapNumber) : '',
      cumulativeTime: formatTenths(interval.cumulativeTime),
      ...metricCells(interval.totals),
    })
    if (single) {
      continue
    }
    for (const entry of interval.laps) {
      result.push({
        key: `lap-${entry.lap.id}`,
        kind: 'lap',
        interval: '',
        lap: String(entry.lapNumber),
        cumulativeTime: formatTenths(entry.cumulativeTime),
        ...metricCells(totalLaps([entry.lap])),
      })
    }
  }
  if (grouped.value.intervals.length > 0) {
    result.push({
      key: 'total',
      kind: 'total',
      interval: t('lapIntensity.intervals.total'),
      lap: '',
      cumulativeTime: '',
      ...metricCells(grouped.value.total),
    })
  }
  return result
})
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full min-w-[28rem] border-collapse text-meta" data-testid="workout-intervals">
      <thead>
        <tr class="text-caption border-b border-border text-left">
          <th class="py-2 pe-3 font-medium">{{ t('lapIntensity.intervals.interval') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t('activities.laps.lap') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t('activities.laps.time') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t('lapIntensity.intervals.cumulativeTime') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t('activities.laps.distance') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t(tempoLabelKey) }}</th>
          <th v-if="showGap" class="py-2 pe-3 font-medium" :title="t('activities.laps.gapHint')">
            {{ t('activities.laps.gap') }}
          </th>
          <th class="py-2 pe-3 font-medium">{{ t('activities.metrics.avgHr') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t('activities.metrics.maxHr') }}</th>
          <th v-if="showElevation" class="py-2 pe-3 font-medium">
            {{ t('activities.laps.elevation') }}
          </th>
          <th class="py-2 font-medium">{{ t('activities.streams.cadence') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.key"
          :data-kind="row.kind"
          :class="{
            'border-t border-border font-semibold text-foreground': row.kind === 'interval',
            'text-muted-foreground': row.kind === 'lap',
            'border-t-2 border-border font-semibold text-foreground': row.kind === 'total',
          }"
        >
          <td class="py-2 pe-3">{{ row.interval }}</td>
          <td class="py-2 pe-3">{{ row.lap }}</td>
          <td class="py-2 pe-3">{{ row.time }}</td>
          <td class="py-2 pe-3">{{ row.cumulativeTime }}</td>
          <td class="py-2 pe-3">{{ row.distance }}</td>
          <td class="py-2 pe-3">{{ row.tempo }}</td>
          <td v-if="showGap" class="py-2 pe-3">{{ row.gap }}</td>
          <td class="py-2 pe-3">{{ row.avgHr }}</td>
          <td class="py-2 pe-3">{{ row.maxHr }}</td>
          <td v-if="showElevation" class="py-2 pe-3">{{ row.elevation }}</td>
          <td class="py-2">{{ row.cadence }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
