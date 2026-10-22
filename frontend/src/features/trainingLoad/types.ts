/**
 * Homelab fork: Intervals.icu-style training load. Runs score by pace (grade
 * adjusted), other sports by heart rate (HRSS), strength sessions 0. The
 * backend lives in `backend/app/homelab/training_load` and caches each load in
 * the fork-owned `homelab` schema.
 */
import type { Schemas } from '@/types'

/** Which calculation an activity's load came from. */
export type LoadSource = Schemas['LoadSource']

/** One activity's load, as the endpoint returns it. */
export type ActivityLoadReadDto = Schemas['ActivityLoadRead']

/** One activity's load, mapped for the view. Every value is `null` when it has none. */
export interface ActivityLoad {
  activityId: number
  load: number | null
  source: LoadSource | null
  paceLoad: number | null
  hrLoad: number | null
}
