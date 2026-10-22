import { apiFetch } from '@/services/http'

import type {
  ActivityLoad,
  ActivityLoadReadDto,
  Fitness,
  FitnessDayDto,
  FitnessDto,
} from '@/features/trainingLoad/types'

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

/** Maps a fitness DTO to the view model. */
export function mapFitness(dto: FitnessDto): Fitness {
  return {
    loadsStart: dto.loads_start,
    hasSettings: dto.has_settings,
    days: (dto.days ?? []).map((day: FitnessDayDto) => ({
      date: day.date,
      load: day.load,
      fitness: day.fitness,
      fatigue: day.fatigue,
      form: day.form,
      ramp: day.ramp,
    })),
  }
}

/**
 * Fetches the signed-in user's daily fitness, fatigue and form between two
 * local dates (inclusive; at most 400 days).
 *
 * @param range - Inclusive `YYYY-MM-DD` bounds.
 * @param signal - Optional abort signal.
 * @returns The series; no days when the user has set no thresholds.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFitness(
  range: { startDate: string; endDate: string },
  signal?: AbortSignal,
): Promise<Fitness> {
  const params = new URLSearchParams({ start_date: range.startDate, end_date: range.endDate })
  const dto = await apiFetch<FitnessDto>(`/homelab/training_load/fitness?${params.toString()}`, {
    signal,
  })
  return mapFitness(dto)
}
