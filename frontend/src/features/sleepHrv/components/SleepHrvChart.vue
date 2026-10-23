<script setup lang="ts">
// Homelab fork: nightly HRV against its 7-day average and usual range.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { SleepHrvEntry } from '@/features/sleepHrv/types'

import { themeColor } from '@/lib/themeColor'
import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'
import { formatHealthEntryDate } from '@/features/health/utils/healthFormat'
import { formatHrv, hrvChartSeries } from '@/features/sleepHrv/utils/sleepHrv'

const props = defineProps<{
  /** Every night in the window, newest first. */
  entries: SleepHrvEntry[]
}>()

const { t, locale } = useI18n()

const NIGHTLY_COLOR = themeColor('--color-brand-mid')
const AVERAGE_COLOR = themeColor('--color-hr')
const RANGE_COLOR = themeColor('--color-info')

const chartRender = computed<ChartRenderOptions>(() => {
  const { dates, series } = hrvChartSeries(
    props.entries,
    { nightly: NIGHTLY_COLOR, average: AVERAGE_COLOR, range: RANGE_COLOR },
    {
      nightly: t('sleepHrv.chart.nightly'),
      average: t('sleepHrv.chart.average'),
      range: t('sleepHrv.chart.range'),
    },
  )
  return {
    kind: 'line',
    series,
    labels: dates.map((date) => formatHealthEntryDate(date, locale.value)),
    valueFormat: (value) => formatHrv(value),
    hoverIndex: true,
    xMaxTicks: 6,
  }
})

useHealthMetricChart(chartRender)
</script>

<template>
  <HealthChartCard :title="t('sleepHrv.chart.title')" :accent-color="NIGHTLY_COLOR">
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
  </HealthChartCard>
</template>
