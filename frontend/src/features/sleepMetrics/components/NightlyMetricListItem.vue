<script setup lang="ts">
// Homelab fork: one night of a nightly metric in the list.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { NightlyMetricEntry, NightlyMetricKind } from '@/features/sleepMetrics/types'

import { formatHealthEntryDate } from '@/features/health/utils/healthFormat'
import {
  formatNightlyMetric,
  formatNightlyMetricRange,
  nightlyMetricStatus,
} from '@/features/sleepMetrics/utils/sleepMetrics'

const props = defineProps<{
  kind: NightlyMetricKind
  /** The night to render. */
  entry: NightlyMetricEntry
}>()

const { t, locale } = useI18n()

const dateLabel = computed(() => formatHealthEntryDate(props.entry.date, locale.value))
const status = computed(() => nightlyMetricStatus(props.entry))
const detail = computed(() => {
  const parts: string[] = []
  if (props.entry.avg7d !== null) {
    parts.push(
      t('sleepMetrics.list.average', { value: formatNightlyMetric(props.kind, props.entry.avg7d) }),
    )
  }
  const range = formatNightlyMetricRange(props.kind, props.entry.rangeLow, props.entry.rangeHigh)
  if (range) parts.push(t('sleepMetrics.list.range', { value: range }))
  return parts.join(' · ')
})
</script>

<template>
  <div class="px-4 py-3">
    <div class="flex items-center justify-between gap-3">
      <p class="text-item-title">{{ formatNightlyMetric(kind, entry.value) }}</p>
      <span
        v-if="status && status !== 'within'"
        class="rounded-full border border-border px-2 py-0.5 text-hint"
      >
        {{ t(`sleepMetrics.status.${status}`) }}
      </span>
    </div>
    <p class="text-hint">
      {{ dateLabel }}<template v-if="detail"> · {{ detail }}</template>
    </p>
  </div>
</template>
