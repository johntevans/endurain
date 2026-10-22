<script setup lang="ts">
import type { ChartRenderOptions } from '@/composables/useChartProvider'

import HealthChartCard from '@/features/health/components/HealthChartCard.vue'
import { useHealthMetricChart } from '@/features/health/composables/useHealthMetricChart'

/**
 * Homelab fork: one chart of the fitness page, in the same card and with the
 * same mount lifecycle as the health charts.
 */
const props = defineProps<{
  title: string
  /** Accent-dot colour (a resolved theme hex). */
  accentColor: string
  render: ChartRenderOptions
}>()

useHealthMetricChart(() => props.render)
</script>

<template>
  <HealthChartCard :title="title" :accent-color="accentColor">
    <!-- min-w-0 lets the canvas shrink inside the grid on mobile. -->
    <div ref="chartContainer" class="relative h-56 w-full min-w-0" />
    <!-- Anything under the chart, e.g. a legend of zones. -->
    <slot />
  </HealthChartCard>
</template>
