// Homelab fork: nightly HRV queries.
import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'

import type { HealthInterval } from '@/features/health/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { fetchLatestSleepHrv, fetchSleepHrv } from '@/features/sleepHrv/services/sleepHrv'

/**
 * Query keys, under the `health` prefix so every health invalidation (a sleep
 * edit, a target change) refreshes them too.
 */
export const sleepHrvQueryKeys = {
  list: (filters: Record<string, unknown>) =>
    [...queryKeys.health.all(), 'homelab-sleep-hrv', filters] as const,
  latest: () => [...queryKeys.health.all(), 'homelab-sleep-hrv', 'latest'] as const,
}

/**
 * One page of nights for the list.
 *
 * @param page - 1-based page.
 * @param pageSize - Records per page.
 * @param interval - Time window.
 */
export function useSleepHrvPageQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const params = computed(() => ({
    interval: toValue(interval),
    page: toValue(page),
    numRecords: toValue(pageSize),
  }))
  return useQuery({
    queryKey: computed(() => sleepHrvQueryKeys.list(params.value)),
    queryFn: ({ signal }) => fetchSleepHrv(params.value, signal),
    placeholderData: keepPreviousData,
    enabled: isAuthenticated,
  })
}

/**
 * Every night in the window, for the chart: a trend needs the whole window,
 * not one list page.
 *
 * @param interval - Time window.
 */
export function useSleepHrvWindowQuery(interval: MaybeRefOrGetter<HealthInterval>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  return useQuery({
    queryKey: computed(() => sleepHrvQueryKeys.list({ interval: toValue(interval) })),
    queryFn: ({ signal }) => fetchSleepHrv({ interval: toValue(interval) }, signal),
    placeholderData: keepPreviousData,
    enabled: isAuthenticated,
  })
}

/** The most recent night with HRV, for the dashboard tile. */
export function useLatestSleepHrvQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  return useQuery({
    queryKey: sleepHrvQueryKeys.latest(),
    queryFn: ({ signal }) => fetchLatestSleepHrv(signal),
    enabled: isAuthenticated,
  })
}
