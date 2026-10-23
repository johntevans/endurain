// Homelab fork: nightly metric queries.
import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'

import type { HealthInterval } from '@/features/health/types'
import type { NightlyMetricKind } from '@/features/sleepMetrics/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  fetchLatestNightlyMetric,
  fetchNightlyMetric,
} from '@/features/sleepMetrics/services/sleepMetrics'

/**
 * Query keys, under the `health` prefix so every health invalidation (a sleep
 * edit, a target change) refreshes them too.
 */
export const nightlyMetricQueryKeys = {
  list: (kind: NightlyMetricKind, filters: Record<string, unknown>) =>
    [...queryKeys.health.all(), 'homelab-nightly', kind, filters] as const,
  latest: (kind: NightlyMetricKind) =>
    [...queryKeys.health.all(), 'homelab-nightly', kind, 'latest'] as const,
}

/** One page of nights for the list. */
export function useNightlyMetricPageQuery(
  kind: MaybeRefOrGetter<NightlyMetricKind>,
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
    queryKey: computed(() => nightlyMetricQueryKeys.list(toValue(kind), params.value)),
    queryFn: ({ signal }) => fetchNightlyMetric(toValue(kind), params.value, signal),
    placeholderData: keepPreviousData,
    enabled: isAuthenticated,
  })
}

/**
 * Every night in the window, for the chart: a trend needs the whole window,
 * not one list page.
 */
export function useNightlyMetricWindowQuery(
  kind: MaybeRefOrGetter<NightlyMetricKind>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  return useQuery({
    queryKey: computed(() =>
      nightlyMetricQueryKeys.list(toValue(kind), { interval: toValue(interval) }),
    ),
    queryFn: ({ signal }) =>
      fetchNightlyMetric(toValue(kind), { interval: toValue(interval) }, signal),
    placeholderData: keepPreviousData,
    enabled: isAuthenticated,
  })
}

/** The most recent night, for a dashboard tile. */
export function useLatestNightlyMetricQuery(kind: NightlyMetricKind) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  return useQuery({
    queryKey: nightlyMetricQueryKeys.latest(kind),
    queryFn: ({ signal }) => fetchLatestNightlyMetric(kind, signal),
    enabled: isAuthenticated,
  })
}
