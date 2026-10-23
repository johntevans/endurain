<script setup lang="ts">
// Homelab fork: a nightly metric against its 7-day average and usual range.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { NightlyMetricEntry, NightlyMetricKind } from '@/features/sleepMetrics/types'

import { themeColor } from '@/lib/themeColor'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthEntryDate } from '@/features/health/utils/healthFormat'
import { NIGHTLY_METRICS } from '@/features/sleepMetrics/metrics'
import {
  formatNightlyMetric,
  nightlyMetricChartSeries,
} from '@/features/sleepMetrics/utils/sleepMetrics'

const props = defineProps<{
  kind: NightlyMetricKind
  /** Every night in the window, newest first. */
  entries: NightlyMetricEntry[]
}>()

const { t, locale } = useI18n()

const NIGHTLY_COLOR = themeColor('--color-brand-mid')
const AVERAGE_COLOR = themeColor('--color-hr')
const RANGE_COLOR = themeColor('--color-info')

const key = computed(() => NIGHTLY_METRICS[props.kind].i18nKey)

const chartRender = computed<ChartRenderOptions>(() => {
  const { dates, series } = nightlyMetricChartSeries(
    props.entries,
    { nightly: NIGHTLY_COLOR, average: AVERAGE_COLOR, range: RANGE_COLOR },
    {
      nightly: t(`sleepMetrics.${key.value}.series`),
      average: t('sleepMetrics.chart.average'),
      range: t('sleepMetrics.chart.range'),
    },
  )
  return {
    kind: 'line',
    series,
    labels: dates.map((date) => formatHealthEntryDate(date, locale.value)),
    valueFormat: (value) => formatNightlyMetric(props.kind, value),
    hoverIndex: true,
    xMaxTicks: 6,
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard :title="t(`sleepMetrics.${key}.chartTitle`)" :accent-color="NIGHTLY_COLOR">
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
