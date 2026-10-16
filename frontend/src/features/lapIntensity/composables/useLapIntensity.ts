import { computed, type MaybeRefOrGetter, ref, toValue } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { Activity, ActivityLap } from '@/features/activities/types'
import type { LapIntensity, LapIntensityKey } from '@/features/lapIntensity/types'

import { queryKeys } from '@/services/queryKeys'
import { useToasts } from '@/composables/useToasts'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { isActivityOwner } from '@/features/activities/utils/privacy'
import { fetchLapIntensities, setLapIntensity } from '@/features/lapIntensity/services/lapIntensity'

/**
 * Query key for one activity's lap intensities. Under the `activities` prefix
 * so every existing `queryKeys.activities.all()` invalidation refreshes it.
 */
export function lapIntensityQueryKey(activityId: number) {
  return [...queryKeys.activities.all(), 'homelab-lap-intensity', activityId] as const
}

/** Prefix of every training-log query, whose quality totals follow the laps. */
const TRAINING_LOG_PREFIX = [...queryKeys.activities.all(), 'homelab-training-log'] as const

/**
 * Lap intensity for the laps table. For the activity's owner it fetches each
 * lap's effective intensity (the override, else the recorded value, else the
 * `active` default) and lets them change it; for anyone else it does nothing
 * and the table shows the laps as upstream serves them.
 *
 * @param activity - The activity whose laps are shown.
 * @returns Whether the viewer may edit, each lap's entry, `apply()` to put the
 *   effective values into the laps, and `set()` to change one.
 */
export function useActivityLapIntensity(activity: MaybeRefOrGetter<Activity>) {
  const client = useQueryClient()
  const { t } = useI18n()
  const toasts = useToasts()
  const { data: currentUser } = useCurrentUser()

  const activityId = computed(() => toValue(activity).id)
  const editable = computed(() => isActivityOwner(toValue(activity), currentUser.value?.id ?? null))

  const query = useQuery({
    queryKey: computed(() => lapIntensityQueryKey(activityId.value)),
    queryFn: ({ signal }) => fetchLapIntensities(activityId.value, signal),
    enabled: editable,
  })

  const byLapId = computed(
    () =>
      new Map<number, LapIntensity>(
        editable.value ? (query.data.value ?? []).map((entry) => [entry.lapId, entry]) : [],
      ),
  )

  const savingLapId = ref<number | null>(null)
  const mutation = useMutation<
    LapIntensity,
    Error,
    { lapId: number; intensity: LapIntensityKey | null }
  >({
    mutationFn: ({ lapId, intensity }) => setLapIntensity(lapId, intensity),
    onSuccess: (updated) => {
      client.setQueryData<LapIntensity[]>(lapIntensityQueryKey(activityId.value), (old) =>
        old?.map((entry) => (entry.lapId === updated.lapId ? updated : entry)),
      )
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: TRAINING_LOG_PREFIX })
    },
  })

  /**
   * The laps with their effective intensity in place of the recorded one, so
   * rest detection and the active totals follow the owner's corrections.
   */
  function apply(laps: ActivityLap[]): ActivityLap[] {
    if (byLapId.value.size === 0) {
      return laps
    }
    return laps.map((lap) => {
      const entry = byLapId.value.get(lap.id)
      return entry && entry.intensity !== lap.intensity
        ? { ...lap, intensity: entry.intensity }
        : lap
    })
  }

  /**
   * Changes one lap. Picking the value the lap would have without an override
   * (its recorded value, or the default) clears the override instead. A
   * failure is reported as a toast.
   */
  async function set(lapId: number, intensity: LapIntensityKey | null): Promise<void> {
    const entry = byLapId.value.get(lapId)
    const unchanged = entry?.recorded ?? 'active'
    const override = intensity === null || intensity === unchanged ? null : intensity
    if (entry && override === null && entry.source !== 'override') {
      return
    }
    savingLapId.value = lapId
    try {
      await mutation.mutateAsync({ lapId, intensity: override })
    } catch {
      toasts.error(t('lapIntensity.saveError'))
    } finally {
      savingLapId.value = null
    }
  }

  return { editable, byLapId, apply, set, savingLapId }
}
