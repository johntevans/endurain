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

/** One day of fitness, fatigue and form, as the endpoint returns it. */
export type FitnessDayDto = Schemas['FitnessDayRead']

/** A fitness series, as the endpoint returns it. */
export type FitnessDto = Schemas['FitnessRead']

/** Fitness, fatigue and form at the end of one local day (one decimal). */
export interface FitnessDay {
  /** Local date, `YYYY-MM-DD`. */
  date: string
  /** Sum of the day's activity loads. */
  load: number
  /** 42-day exponentially weighted load (Intervals' Fitness, CTL). */
  fitness: number
  /** 7-day exponentially weighted load (Intervals' Fatigue, ATL). */
  fatigue: number
  /** Fitness minus fatigue. */
  form: number
  /** Change in fitness over the last 7 days. */
  ramp: number
}

/** A fitness series. */
export interface Fitness {
  /** First date with loads (`YYYY-MM-DD`): the averages start from zero there. */
  loadsStart: string
  /** Whether the user has set thresholds; without them there are no days. */
  hasSettings: boolean
  /** One entry per day, oldest first. */
  days: FitnessDay[]
}

/** The time ranges the fitness page offers. */
export type FitnessRangeKey = '6w' | '3m' | '6m' | '1y'

/** One week of the fitness table: its load, and the values on its last day shown. */
export interface FitnessWeekRow {
  /** First day of the week, `YYYY-MM-DD`. */
  start: string
  load: number
  fitness: number
  fatigue: number
  form: number
  ramp: number
}
