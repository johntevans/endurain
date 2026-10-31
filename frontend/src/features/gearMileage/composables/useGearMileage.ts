import { useQuery } from '@tanstack/vue-query'

import { queryKeys } from '@/services/queryKeys'
import { fetchGearMileage } from '@/features/gearMileage/services/gearMileage'

/**
 * Query key for the gear mileage. Under the `gears` prefix so every existing
 * `queryKeys.gears.all()` invalidation (a gear edit, an import, a change of an
 * activity's gear) refreshes it.
 */
export function gearMileageQueryKey() {
  return [...queryKeys.gears.all(), 'homelab-mileage'] as const
}

/**
 * The total distance of all the signed-in user's gears. Every row of the gear
 * list shares this one query, so a page of gear sends one request.
 *
 * @returns The TanStack query result, in metres keyed by gear id.
 */
export function useGearMileageQuery() {
  return useQuery({
    queryKey: gearMileageQueryKey(),
    queryFn: ({ signal }) => fetchGearMileage(signal),
  })
}
