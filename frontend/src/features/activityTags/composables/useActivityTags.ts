import { computed, type MaybeRefOrGetter, ref, type Ref, toValue, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { ActivityTagKey } from '@/features/activityTags/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { fetchActivityTags, setActivityTags } from '@/features/activityTags/services/activityTags'
import { sameActivityTags } from '@/features/activityTags/utils/activityTags'

/**
 * Query key for a batch of activity tags. Lives under the `activities` prefix
 * so every existing `queryKeys.activities.all()` invalidation (edit, delete,
 * upload) also refreshes tags.
 *
 * @param ids - Activity ids (order-insensitive).
 * @param authenticated - Whether the authenticated or public endpoint is used.
 * @returns A stable query key.
 */
export function activityTagsQueryKey(ids: readonly number[], authenticated: boolean) {
  const sorted = [...new Set(ids)].sort((a, b) => a - b)
  return [...queryKeys.activities.all(), 'homelab-tags', { ids: sorted, authenticated }] as const
}

/**
 * Tags for a set of activities (a list page, or one activity), fetched in a
 * single batch request. Gated on having at least one id.
 *
 * @param ids - Reactive activity ids.
 * @returns The TanStack query result: a map of activity id to its tags.
 */
export function useActivityTagsQuery(ids: MaybeRefOrGetter<readonly number[]>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const validIds = computed(() => toValue(ids).filter((id) => Number.isFinite(id) && id > 0))

  return useQuery({
    queryKey: computed(() => activityTagsQueryKey(validIds.value, isAuthenticated.value)),
    queryFn: ({ signal }) =>
      fetchActivityTags(validIds.value, { authenticated: isAuthenticated.value, signal }),
    placeholderData: keepPreviousData,
    enabled: computed(() => validIds.value.length > 0),
  })
}

/**
 * Replaces an activity's tags. On settle it invalidates the activities domain,
 * which refreshes tag badges and any tag-filtered list or count.
 *
 * @returns The TanStack mutation for setting an activity's tags.
 */
export function useSetActivityTagsMutation() {
  const client = useQueryClient()

  return useMutation<ActivityTagKey[], Error, { id: number; tags: readonly ActivityTagKey[] }>({
    mutationFn: ({ id, tags }) => setActivityTags(id, tags),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.activities.all() })
    },
  })
}

/**
 * Draft tag state for the activity edit dialog. The draft starts from the
 * activity's current tags each time the dialog opens; `save()` only sends a
 * request when the selection actually changed.
 *
 * @param activityId - Reactive id of the activity being edited.
 * @param open - The dialog's open state.
 * @returns The bound selection, loading/saving flags and `save()`.
 */
export function useActivityTagsEditor(activityId: MaybeRefOrGetter<number>, open: Ref<boolean>) {
  const tagsQuery = useActivityTagsQuery(() => [toValue(activityId)])
  const mutation = useSetActivityTagsMutation()

  const current = computed<ActivityTagKey[]>(
    () => tagsQuery.data.value?.get(toValue(activityId)) ?? [],
  )
  const draft = ref<ActivityTagKey[] | null>(null)

  watch(open, (isOpen) => {
    if (isOpen) {
      draft.value = null
    }
  })

  /** The checkbox group's model: the draft, or the current tags until edited. */
  const selected = computed<ActivityTagKey[]>({
    get: () => draft.value ?? current.value,
    set: (tags) => {
      draft.value = [...tags]
    },
  })

  const isLoading = computed(() => tagsQuery.isPending.value)
  const isSaving = computed(() => mutation.isPending.value)

  /** Persists the draft when it differs from the current tags. */
  async function save(): Promise<void> {
    if (draft.value === null || sameActivityTags(draft.value, current.value)) {
      return
    }
    await mutation.mutateAsync({ id: toValue(activityId), tags: draft.value })
    draft.value = null
  }

  return { selected, isLoading, isSaving, save }
}
