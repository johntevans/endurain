import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'

/**
 * Fetches the total distance of each of the signed-in user's gears.
 *
 * @param signal - Optional abort signal.
 * @returns Metres, keyed by gear id.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGearMileage(signal?: AbortSignal): Promise<Record<number, number>> {
  const dtos = await apiFetch<Schemas['GearMileageRead'][]>('/homelab/gear_mileage', { signal })
  return Object.fromEntries(dtos.map((dto) => [dto.gear_id, dto.total_distance]))
}
