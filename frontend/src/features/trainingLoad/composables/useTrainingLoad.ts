import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { keepPreviousData, useQuery } from '@tanstack/vue-query'

import type { Activity } from '@/features/activities/types'

import { queryKeys } from '@/services/queryKeys'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { isActivityOwner } from '@/features/activities/utils/privacy'
import { fetchActivityLoad, fetchFitness } from '@/features/trainingLoad/services/trainingLoad'

/**
 * Query key for one activity's load. Under the `activities` prefix so every
 * existing `queryKeys.activities.all()` invalidation (an edit that changes
 * the type, a delete) refreshes it.
 */
export function activityLoadQueryKey(activityId: number) {
  return [...queryKeys.activities.all(), 'homelab-training-load', activityId] as const
}

/**
 * The training load of an activity, for its owner only: anyone else sends no
 * request and gets `null`.
 *
 * @param activity - The activity shown.
 * @returns The TanStack query result.
 */
export function useActivityLoad(activity: MaybeRefOrGetter<Activity>) {
  const { data: currentUser } = useCurrentUser()
  const activityId = computed(() => toValue(activity).id)
  const isOwner = computed(() => isActivityOwner(toValue(activity), currentUser.value?.id ?? null))

  return useQuery({
    queryKey: computed(() => activityLoadQueryKey(activityId.value)),
    queryFn: ({ signal }) => fetchActivityLoad(activityId.value, signal),
    enabled: isOwner,
  })
}

/**
 * Query key for a fitness series. Under the `activities` prefix so every
 * activity edit, upload or delete refreshes it.
 */
export function fitnessQueryKey(range: { startDate: string; endDate: string }) {
  return [...queryKeys.activities.all(), 'homelab-fitness', range] as const
}

/**
 * The signed-in user's fitness, fatigue and form over a range of local dates.
 *
 * @param range - Reactive inclusive `YYYY-MM-DD` bounds.
 * @returns The TanStack query result.
 */
export function useFitnessQuery(range: MaybeRefOrGetter<{ startDate: string; endDate: string }>) {
  return useQuery({
    queryKey: computed(() => fitnessQueryKey(toValue(range))),
    queryFn: ({ signal }) => fetchFitness(toValue(range), signal),
    placeholderData: keepPreviousData,
  })
}
