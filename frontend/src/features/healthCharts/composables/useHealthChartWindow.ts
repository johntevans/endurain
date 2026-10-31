// Homelab fork: every record in the chosen window, for a health zone's chart.
// A trend needs the whole window; upstream's views plot the list's current page,
// which cuts "Last year" and "All time" to the newest `num_records_per_page`
// records.
import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'

import type { HealthInterval } from '@/features/health/types'
import type { HealthListParams } from '@/features/health/services/health'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  fetchPoopEntries,
  fetchSleepEntries,
  fetchStepsEntries,
  fetchWaterEntries,
  fetchWeightEntries,
} from '@/features/health/services/health'

/**
 * The window query shared by the zones. The key carries no page or size, so it
 * never collides with a list page, and sits under the zone's own `health` prefix
 * so the zone's mutations refresh the chart too.
 */
function useHealthChartWindowQuery<Page>(
  keyForFilters: (filters: Record<string, unknown>) => readonly unknown[],
  fetchEntries: (params: HealthListParams, signal?: AbortSignal) => Promise<Page>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  return useQuery({
    queryKey: computed(() => keyForFilters({ interval: toValue(interval) })),
    queryFn: ({ signal }) => fetchEntries({ interval: toValue(interval) }, signal),
    placeholderData: keepPreviousData,
    enabled: isAuthenticated,
  })
}

/** Every weight entry in the window. */
export function useWeightChartQuery(interval: MaybeRefOrGetter<HealthInterval>) {
  return useHealthChartWindowQuery(queryKeys.health.weight, fetchWeightEntries, interval)
}

/** Every steps entry in the window. */
export function useStepsChartQuery(interval: MaybeRefOrGetter<HealthInterval>) {
  return useHealthChartWindowQuery(queryKeys.health.steps, fetchStepsEntries, interval)
}

/** Every water entry in the window. */
export function useWaterChartQuery(interval: MaybeRefOrGetter<HealthInterval>) {
  return useHealthChartWindowQuery(queryKeys.health.water, fetchWaterEntries, interval)
}

/** Every bowel-movement entry in the window. */
export function usePoopChartQuery(interval: MaybeRefOrGetter<HealthInterval>) {
  return useHealthChartWindowQuery(queryKeys.health.poop, fetchPoopEntries, interval)
}

/** Every night's sleep entry in the window. */
export function useSleepChartQuery(interval: MaybeRefOrGetter<HealthInterval>) {
  return useHealthChartWindowQuery(queryKeys.health.sleep, fetchSleepEntries, interval)
}
