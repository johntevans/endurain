/**
 * Homelab fork: the training log, a Strava-style week-by-week view of every
 * activity. The backend lives in `backend/app/homelab/training_log`.
 */
import type { Schemas } from '@/types'

import type { ActivityTagKey } from '@/features/activityTags/types'

/** One activity as the training-log endpoint returns it. */
export type TrainingLogActivityDto = Schemas['TrainingLogActivity']

/** First/last activity dates as the range endpoint returns them. */
export type TrainingLogRangeDto = Schemas['TrainingLogRange']

/** One activity, mapped for the view. */
export interface TrainingLogActivity {
  id: number
  name: string
  activityType: number
  /** The activity's own local calendar date, `YYYY-MM-DD`. */
  localDate: string
  /** Local start time, ISO 8601 without offset. */
  startTime: string
  /** Metres. */
  distance: number
  /** Moving (timer) time in seconds. */
  movingTime: number
  /** Elapsed time in seconds. */
  elapsedTime: number
  /** Metres, or `null` when the activity has none. */
  elevationGain: number | null
  tags: ActivityTagKey[]
}

/** Local dates of the first and last activity (`null` when there are none). */
export interface TrainingLogRange {
  firstDate: string | null
  lastDate: string | null
}

/** The weekly total and circle size measure (Strava's "Time / Distance / Elevation"). */
export type TrainingLogMetric = 'time' | 'distance' | 'elevation'

/** Sport families that share a colour and a size scale. */
export type SportFamily = 'run' | 'ride' | 'swim' | 'walk' | 'other'

/**
 * The sport filter: every activity, a family, or one activity type
 * (`type-14` for yoga) for types that belong to no family.
 */
export type SportFilter = 'all' | Exclude<SportFamily, 'other'> | `type-${number}`

/** The tag filter: every activity, or only those with one tag. */
export type TagFilter = 'all' | ActivityTagKey

/** How a circle is drawn: plain, long run (darker), workout (hatched) or race. */
export type CircleStyle = 'base' | 'long' | 'workout' | 'race'

/** One calendar week of the log. */
export interface TrainingLogWeek {
  /** First day, `YYYY-MM-DD`. */
  start: string
  /** The seven days, first to last. */
  days: string[]
  /**
   * The week's fourth day. A week belongs to the year and month of this day
   * (the ISO-8601 rule), so a week split across New Year sits in the year
   * that holds most of it.
   */
  anchor: string
}
