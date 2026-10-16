<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Activity, ActivityLap } from '@/features/activities/types'
import type { Units } from '@/features/activities/utils/format'

import {
  activityTypeIsRunning,
  activityTypeIsSwimming,
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
import { normalizeLaps, summarizeActiveLaps } from '@/features/activities/utils/laps'
import { formatLapTempo } from '@/features/activities/utils/metrics'
import LapIntensityCell from '@/features/lapIntensity/components/LapIntensityCell.vue' // homelab fork
import { useActivityLapIntensity } from '@/features/lapIntensity/composables/useLapIntensity' // homelab fork

const props = defineProps<{
  laps: ActivityLap[]
  activity: Activity
  units: Units
}>()

const { t } = useI18n()

const isSwimming = computed(() => activityTypeIsSwimming(props.activity.activityType))
// Swimming has no elevation (v1 parity).
const showElevation = computed(() => !isSwimming.value)
// The tempo column is pace or speed depending on the sport (see formatLapTempo).
const tempoLabelKey = computed(() =>
  activityTypeUsesPace(props.activity.activityType)
    ? 'activities.metrics.avgPace'
    : 'activities.metrics.avgSpeed',
)
// A swim's lap cadence is its stroke rate, which has no spm/rpm unit.
const cadenceLabelKey = computed(() =>
  isSwimming.value ? 'activities.laps.strokeRate' : 'activities.streams.cadence',
)

// homelab fork: the owner sees each lap's effective intensity (defaulted or
// overridden) and can change it; everyone else sees the laps as recorded.
const {
  byLapId: lapIntensities,
  savingLapId,
  set: setLapIntensity,
  apply: applyLapIntensity,
} = useActivityLapIntensity(() => props.activity)
const laps = computed(() => applyLapIntensity(props.laps))

const normalized = computed(() => normalizeLaps(laps.value, props.activity.activityType))
const hasIntensity = computed(() => normalized.value.some((entry) => entry.lap.intensity !== null))
// Any rest lap, whether flagged via FIT intensity or the swim heuristic. Swim
// rests carry no intensity field, so gating on hasIntensity alone would hide the
// active-total breakdown for swims — use this instead.
const hasRest = computed(() => normalized.value.some((entry) => entry.isRest))
// Grade-adjusted pace is computed server-side for running/walking laps that
// have elevation and speed streams; show the column only when there is a value.
const showGap = computed(
  () =>
    (activityTypeIsRunning(props.activity.activityType) ||
      activityTypeIsWalking(props.activity.activityType)) &&
    normalized.value.some((entry) => !entry.isRest && entry.lap.gradeAdjustedAvgPace !== null),
)

// Active-only totals, shown only when the activity distinguishes rest laps
// (otherwise the header already covers the same numbers).
const activeSummary = computed(() => {
  if (!hasRest.value) {
    return null
  }
  const summary = summarizeActiveLaps(laps.value, props.activity.activityType) // homelab fork
  if (summary === null) {
    return null
  }
  return {
    distance: combineMetric(
      formatDistance(summary.totalDistance, props.activity.activityType, props.units),
    ),
    time: formatHmsDuration(summary.totalElapsedTime),
    tempo: formatLapTempo(
      summary.avgPace,
      summary.avgSpeed,
      props.activity.activityType,
      props.units,
    ),
  }
})

interface LapRow {
  id: number
  index: number
  intensity: string | null
  distance: string
  time: string
  tempo: string
  /** Relative-pace score (0–100), or `null` when the lap has no pace. */
  tempoScore: number | null
  gap: string
  avgHr: string
  maxHr: string
  elevation: string
  cadence: string
  isRest: boolean
}

/**
 * Formats a lap's average cadence: running doubled to spm, other sports in
 * rpm, swimming as a bare stroke rate.
 *
 * @param avgCadence - Raw lap average cadence.
 * @returns The display string, or `--` when absent.
 */
function formatLapCadence(avgCadence: number | null): string {
  if (avgCadence === null) {
    return '--'
  }
  const type = props.activity.activityType
  if (isSwimming.value) {
    return `${Math.round(avgCadence)}`
  }
  return `${Math.round(presentCadence(avgCadence, type))} ${cadenceUnitLabel(type)}`
}

const rows = computed<LapRow[]>(() =>
  normalized.value.map((entry, index) => {
    const lap = entry.lap
    return {
      id: lap.id,
      index: index + 1,
      intensity: lap.intensity,
      distance: combineMetric(
        formatDistance(lap.totalDistance, props.activity.activityType, props.units),
      ),
      time: formatHmsDuration(lap.totalElapsedTime),
      // Rest laps record idle drift, so their pace is meaningless — blank it.
      tempo: entry.isRest
        ? '--'
        : formatLapTempo(
            lap.enhancedAvgPace,
            lap.enhancedAvgSpeed,
            props.activity.activityType,
            props.units,
          ),
      tempoScore: entry.isRest ? null : entry.normalizedScore,
      gap: entry.isRest
        ? '--'
        : formatLapTempo(
            lap.gradeAdjustedAvgPace,
            lap.gradeAdjustedAvgSpeed,
            props.activity.activityType,
            props.units,
          ),
      avgHr: lap.avgHeartRate === null ? '--' : `${Math.round(lap.avgHeartRate)} bpm`,
      maxHr: lap.maxHeartRate === null ? '--' : `${Math.round(lap.maxHeartRate)} bpm`,
      elevation:
        lap.totalAscent === null
          ? '--'
          : combineMetric(formatElevation(lap.totalAscent, props.units)),
      cadence: formatLapCadence(lap.avgCadence),
      isRest: entry.isRest,
    }
  }),
)
</script>

<template>
  <div>
    <p v-if="activeSummary" class="text-caption mb-2 text-muted-foreground">
      {{ t('activities.laps.activeSummary') }}:
      <span class="text-foreground">{{ activeSummary.distance }}</span>
      · <span class="text-foreground">{{ activeSummary.time }}</span> ·
      <span class="text-foreground">{{ activeSummary.tempo }}</span>
    </p>
    <div class="overflow-x-auto">
      <table class="w-full min-w-[28rem] border-collapse text-meta">
        <thead>
          <tr class="text-caption border-b border-border text-left">
            <th class="py-2 pe-3 font-medium">{{ t('activities.laps.lap') }}</th>
            <th v-if="hasIntensity" class="py-2 pe-3 font-medium">
              {{ t('activities.laps.intensity') }}
            </th>
            <th class="py-2 pe-3 font-medium">{{ t('activities.laps.distance') }}</th>
            <th class="py-2 pe-3 font-medium">{{ t('activities.laps.time') }}</th>
            <th class="py-2 pe-3 font-medium">{{ t(tempoLabelKey) }}</th>
            <th v-if="showGap" class="py-2 pe-3 font-medium" :title="t('activities.laps.gapHint')">
              {{ t('activities.laps.gap') }}
            </th>
            <th class="py-2 pe-3 font-medium">{{ t('activities.metrics.avgHr') }}</th>
            <th class="py-2 pe-3 font-medium">{{ t('activities.metrics.maxHr') }}</th>
            <th v-if="showElevation" class="py-2 pe-3 font-medium">
              {{ t('activities.laps.elevation') }}
            </th>
            <th class="py-2 font-medium">{{ t(cadenceLabelKey) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="border-b border-border/60 last:border-0"
            :class="row.isRest ? 'text-muted-foreground opacity-60' : ''"
          >
            <td class="py-2 pe-3 font-medium text-foreground">{{ row.index }}</td>
            <!-- homelab fork: owner's intensity picker -->
            <td v-if="hasIntensity && lapIntensities.get(row.id)" class="py-1 pe-3">
              <LapIntensityCell
                :entry="lapIntensities.get(row.id)!"
                :saving="savingLapId === row.id"
                @change="setLapIntensity(row.id, $event)"
              />
            </td>
            <td v-else-if="hasIntensity" class="py-2 pe-3 capitalize text-muted-foreground">
              {{ row.intensity ?? '--' }}
            </td>
            <td class="py-2 pe-3 text-foreground">{{ row.distance }}</td>
            <td class="py-2 pe-3 text-foreground">{{ row.time }}</td>
            <td class="py-2 pe-3 text-foreground">
              <span>{{ row.tempo }}</span>
              <span
                v-if="row.tempoScore !== null"
                class="mt-1 block h-1 w-16 overflow-hidden rounded-full bg-muted"
                role="progressbar"
                :aria-valuenow="Math.round(row.tempoScore)"
                aria-valuemin="0"
                aria-valuemax="100"
              >
                <span
                  class="block h-full rounded-full bg-brand"
                  :style="{ width: `${row.tempoScore}%` }"
                />
              </span>
            </td>
            <td v-if="showGap" class="py-2 pe-3 text-foreground">{{ row.gap }}</td>
            <td class="py-2 pe-3 text-muted-foreground">{{ row.avgHr }}</td>
            <td class="py-2 pe-3 text-muted-foreground">{{ row.maxHr }}</td>
            <td v-if="showElevation" class="py-2 pe-3 text-muted-foreground">
              {{ row.elevation }}
            </td>
            <td class="py-2 text-muted-foreground">{{ row.cadence }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
