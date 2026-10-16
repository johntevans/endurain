/**
 * Homelab fork: lap intensity. Laps the file left without an intensity read
 * as `active`, and the owner can override any lap. The backend lives in
 * `backend/app/homelab/lap_intensity` and keeps overrides in the fork-owned
 * `homelab` schema; upstream's recorded value is never changed.
 */
import type { Schemas } from '@/types'

/** An intensity the owner can set (FIT's values). */
export type LapIntensityKey = Schemas['LapIntensityKey']

/** Where a lap's effective intensity comes from. */
export type LapIntensitySource = Schemas['LapIntensitySource']

/** One lap's effective intensity, as the endpoint returns it. */
export type LapIntensityReadDto = Schemas['LapIntensityRead']

/** One lap's effective intensity, mapped for the view. */
export interface LapIntensity {
  lapId: number
  /** The override, else the recorded value, else the default. */
  intensity: string
  /** As recorded in the activity file, or `null` when it had none. */
  recorded: string | null
  source: LapIntensitySource
}

/** Every value the override picker offers, in picker order. */
export const LAP_INTENSITY_KEYS: readonly LapIntensityKey[] = [
  'active',
  'interval',
  'warmup',
  'cooldown',
  'recovery',
  'rest',
  'other',
]
