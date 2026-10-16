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
  /**
   * Seconds in quality laps (effective intensity active or interval) of a
   * race, workout or NSM session; 0 for any other activity.
   */
  qualityTime: number
  /** Metres in those laps; 0 for any other activity. */
  qualityDistance: number
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
 * One option of the sport filter: a family, or one activity type (`type-14`
 * for yoga) for types that belong to no family.
 */
export type SportOption = Exclude<SportFamily, 'other'> | `type-${number}`

/**
 * The sport filter: the options ticked, in option order. An activity passes
 * when it matches any of them; none ticked means every sport.
 */
export type SportFilter = readonly SportOption[]

/**
 * The tag filter: the tags ticked. An activity passes only when it has every
 * one of them; none ticked means every activity.
 */
export type TagFilter = readonly ActivityTagKey[]

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
