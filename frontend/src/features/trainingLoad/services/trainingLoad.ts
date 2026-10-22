import { apiFetch } from '@/services/http'

import type { ActivityLoad, ActivityLoadReadDto } from '@/features/trainingLoad/types'

/** Maps an activity-load DTO to the view model. */
export function mapActivityLoad(dto: ActivityLoadReadDto): ActivityLoad {
  return {
    activityId: dto.activity_id,
    load: dto.load ?? null,
    source: dto.source ?? null,
    paceLoad: dto.pace_load ?? null,
    hrLoad: dto.hr_load ?? null,
  }
}

/**
 * Fetches the training load of one of the signed-in user's activities (owner
 * only; the backend answers 404 to anyone else). The backend computes it on
 * the first request.
 *
 * @param activityId - Activity identifier.
 * @param signal - Optional abort signal.
 * @returns The load; all values `null` when the activity has none.
 * @throws {HttpError} When the request fails.
 */
export async function fetchActivityLoad(
  activityId: number,
  signal?: AbortSignal,
): Promise<ActivityLoad> {
  const params = new URLSearchParams({ activity_id: String(activityId) })
  const dto = await apiFetch<ActivityLoadReadDto>(`/homelab/training_load?${params.toString()}`, {
    signal,
  })
  return mapActivityLoad(dto)
}
