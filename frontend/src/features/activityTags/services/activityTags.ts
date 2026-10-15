import { apiFetch } from '@/services/http'

import type {
  ActivityTagKey,
  ActivityTagsReadDto,
  ActivityTagsUpdateDto,
} from '@/features/activityTags/types'
import { sortActivityTags } from '@/features/activityTags/utils/activityTags'

/** Whether to hit the authenticated or the public endpoint, plus cancellation. */
export interface ActivityTagsFetchContext {
  /** Whether the viewer is authenticated. */
  authenticated: boolean
  /** Optional abort signal (e.g. TanStack Query cancellation). */
  signal?: AbortSignal
}

/** Most ids the batch endpoint accepts per request (one full list page). */
export const MAX_ACTIVITY_IDS_PER_REQUEST = 100

/**
 * Fetches the tags of many activities in one request (no N+1 for a list
 * page). The backend leaves out activities the viewer may not see, so the
 * map only holds visible ones; a missing id means "no tags to show".
 * Unauthenticated viewers use the public endpoint, which only answers for
 * publicly shareable activities.
 *
 * @param ids - Activity ids; empty yields an empty map without a request.
 * @param context - Auth + cancellation context.
 * @returns A map of activity id to its tags, in display order.
 * @throws {HttpError} When a request fails.
 */
export async function fetchActivityTags(
  ids: readonly number[],
  context: ActivityTagsFetchContext,
): Promise<Map<number, ActivityTagKey[]>> {
  const unique = [...new Set(ids)]
  const result = new Map<number, ActivityTagKey[]>()
  const base = context.authenticated ? '/homelab/activity_tags' : '/public/homelab/activity_tags'

  const chunks: number[][] = []
  for (let start = 0; start < unique.length; start += MAX_ACTIVITY_IDS_PER_REQUEST) {
    chunks.push(unique.slice(start, start + MAX_ACTIVITY_IDS_PER_REQUEST))
  }
  const responses = await Promise.all(
    chunks.map((chunk) => {
      const params = new URLSearchParams()
      for (const id of chunk) {
        params.append('activity_id', String(id))
      }
      return apiFetch<ActivityTagsReadDto[] | null>(`${base}?${params.toString()}`, {
        auth: context.authenticated,
        signal: context.signal,
      })
    }),
  )
  for (const dtos of responses) {
    for (const dto of dtos ?? []) {
      result.set(dto.activity_id, sortActivityTags(dto.tags ?? []))
    }
  }
  return result
}

/**
 * Replaces an activity's tags (owner only; the backend answers 404 to anyone
 * else).
 *
 * @param id - Activity identifier.
 * @param tags - The complete new tag set.
 * @returns The activity's tags after the change, in display order.
 * @throws {HttpError} When the update fails.
 */
export async function setActivityTags(
  id: number,
  tags: readonly ActivityTagKey[],
): Promise<ActivityTagKey[]> {
  const body: ActivityTagsUpdateDto = { tags: sortActivityTags(tags) }
  const dto = await apiFetch<ActivityTagsReadDto>(`/homelab/activity_tags/${id}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return sortActivityTags(dto.tags ?? [])
}
