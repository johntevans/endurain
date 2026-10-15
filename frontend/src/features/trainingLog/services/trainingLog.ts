import { apiFetch } from '@/services/http'

import type {
  TrainingLogActivity,
  TrainingLogActivityDto,
  TrainingLogRange,
  TrainingLogRangeDto,
} from '@/features/trainingLog/types'
import { sortActivityTags } from '@/features/activityTags/utils/activityTags'

/** Maps a training-log activity DTO to the view model. */
export function mapTrainingLogActivity(dto: TrainingLogActivityDto): TrainingLogActivity {
  return {
    id: dto.id,
    name: dto.name,
    activityType: dto.activity_type,
    localDate: dto.local_date,
    startTime: dto.start_time,
    distance: dto.distance,
    movingTime: dto.total_timer_time,
    elapsedTime: dto.total_elapsed_time,
    elevationGain: dto.elevation_gain ?? null,
    tags: sortActivityTags(dto.tags ?? []),
  }
}

/**
 * Fetches the signed-in user's activities between two local dates (inclusive),
 * each with its tags. The backend allows at most 400 days per request.
 *
 * @param range - Inclusive `YYYY-MM-DD` bounds.
 * @param signal - Optional abort signal.
 * @returns Activities in chronological order.
 * @throws {HttpError} When the request fails.
 */
export async function fetchTrainingLog(
  range: { startDate: string; endDate: string },
  signal?: AbortSignal,
): Promise<TrainingLogActivity[]> {
  const params = new URLSearchParams({ start_date: range.startDate, end_date: range.endDate })
  const dtos = await apiFetch<TrainingLogActivityDto[] | null>(
    `/homelab/training_log?${params.toString()}`,
    { signal },
  )
  return (dtos ?? []).map(mapTrainingLogActivity)
}

/**
 * Fetches the local dates of the user's first and last activity, which decide
 * which years the log shows.
 *
 * @param signal - Optional abort signal.
 * @returns The range; both dates are `null` for a user with no activities.
 * @throws {HttpError} When the request fails.
 */
export async function fetchTrainingLogRange(signal?: AbortSignal): Promise<TrainingLogRange> {
  const dto = await apiFetch<TrainingLogRangeDto>('/homelab/training_log/range', { signal })
  return { firstDate: dto.first_date ?? null, lastDate: dto.last_date ?? null }
}
