import { apiFetch } from '@/services/http'

import type {
  LapIntensity,
  LapIntensityKey,
  LapIntensityReadDto,
} from '@/features/lapIntensity/types'

/** Maps a lap-intensity DTO to the view model. */
export function mapLapIntensity(dto: LapIntensityReadDto): LapIntensity {
  return {
    lapId: dto.lap_id,
    intensity: dto.intensity,
    recorded: dto.recorded ?? null,
    source: dto.source,
  }
}

/**
 * Fetches the effective intensity of every lap of one of the signed-in user's
 * activities (owner only; the backend answers 404 to anyone else).
 *
 * @param activityId - Activity identifier.
 * @param signal - Optional abort signal.
 * @returns One entry per lap, in lap order.
 * @throws {HttpError} When the request fails.
 */
export async function fetchLapIntensities(
  activityId: number,
  signal?: AbortSignal,
): Promise<LapIntensity[]> {
  const params = new URLSearchParams({ activity_id: String(activityId) })
  const dtos = await apiFetch<LapIntensityReadDto[] | null>(
    `/homelab/lap_intensity?${params.toString()}`,
    { signal },
  )
  return (dtos ?? []).map(mapLapIntensity)
}

/**
 * Sets the override on one lap, or clears it with `null`.
 *
 * @param lapId - Lap identifier.
 * @param intensity - The override, or `null` to go back to the recorded value
 *   (or the default when the file had none).
 * @returns The lap's effective intensity after the change.
 * @throws {HttpError} When the update fails.
 */
export async function setLapIntensity(
  lapId: number,
  intensity: LapIntensityKey | null,
): Promise<LapIntensity> {
  const dto = await apiFetch<LapIntensityReadDto>(`/homelab/lap_intensity/${lapId}`, {
    method: 'PUT',
    body: JSON.stringify({ intensity }),
  })
  return mapLapIntensity(dto)
}
