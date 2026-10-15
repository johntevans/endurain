import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import { queryKeys } from '@/services/queryKeys'
import {
  fetchTrainingLog,
  fetchTrainingLogRange,
} from '@/features/trainingLog/services/trainingLog'

/**
 * Query keys for the training log. They live under the `activities` prefix so
 * every existing `queryKeys.activities.all()` invalidation (edit, delete,
 * upload, tag change) also refreshes the log.
 */
export const trainingLogQueryKeys = {
  range: () => [...queryKeys.activities.all(), 'homelab-training-log', 'range'] as const,
  window: (startDate: string, endDate: string) =>
    [...queryKeys.activities.all(), 'homelab-training-log', { startDate, endDate }] as const,
}

/** The local dates of the user's first and last activity. */
export function useTrainingLogRangeQuery() {
  return useQuery({
    queryKey: trainingLogQueryKeys.range(),
    queryFn: ({ signal }) => fetchTrainingLogRange(signal),
  })
}

/**
 * The activities of one window of weeks (one year section of the log).
 *
 * @param range - Inclusive `YYYY-MM-DD` bounds of the window.
 * @param enabled - Whether to fetch; a disabled query still returns cached data,
 *   which is how the side nav reads a year the log has already loaded.
 * @returns The TanStack query result.
 */
export function useTrainingLogWindowQuery(
  range: MaybeRefOrGetter<{ startDate: string; endDate: string } | null>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => {
      const value = toValue(range)
      return trainingLogQueryKeys.window(value?.startDate ?? '', value?.endDate ?? '')
    }),
    queryFn: ({ signal }) => {
      const value = toValue(range)
      return value ? fetchTrainingLog(value, signal) : Promise.resolve([])
    },
    enabled: computed(() => toValue(enabled) && toValue(range) !== null),
  })
}
