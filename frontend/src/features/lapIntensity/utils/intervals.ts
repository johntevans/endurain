/**
 * Homelab fork: Garmin-style work intervals. Consecutive work laps (effective
 * intensity `active` or `interval`) form one interval, so a 10-minute rep that
 * auto-lap split at the mile reads as one row with its two laps beneath it.
 * Any other intensity (warm-up, cool-down, rest, recovery, other) ends the
 * interval. Pure, so it is unit-testable.
 */
import type { ActivityLap } from '@/features/activities/types'

import { activityTypeIsSwimming } from '@/features/activities/utils/activityType'

/**
 * The intensities that count as work. A lap without one reads as `active`,
 * FIT's default, as everywhere else in the fork (training-log quality time).
 */
const WORK_INTENSITIES: ReadonlySet<string> = new Set(['active', 'interval'])

/** Whether a lap is a work lap. */
export function isWorkLap(lap: ActivityLap): boolean {
  return WORK_INTENSITIES.has(lap.intensity ?? 'active')
}

/** Totals over a run of laps. Every average is weighted by elapsed time. */
export interface LapTotals {
  /** Metres. */
  distance: number
  /** Elapsed seconds. */
  elapsedTime: number
  /** Metres per second (distance / time), or `null` without time. */
  avgSpeed: number | null
  /** Seconds per metre, or `null` without distance. */
  avgPace: number | null
  /** Grade-adjusted speed over the laps that have one, or `null`. */
  gapSpeed: number | null
  /** Grade-adjusted pace over the laps that have one, or `null`. */
  gapPace: number | null
  avgHeartRate: number | null
  maxHeartRate: number | null
  /** Metres, or `null` when no lap has an ascent. */
  ascent: number | null
  /** Raw cadence, as on the lap. */
  avgCadence: number | null
}

/** One lap of an interval. */
export interface IntervalLap {
  lap: ActivityLap
  /** 1-based position in the activity's laps, as the laps table numbers it. */
  lapNumber: number
  /** Elapsed seconds from the start of the first lap to the end of this one. */
  cumulativeTime: number
}

/** A run of consecutive work laps. */
export interface WorkInterval {
  /** 1-based interval number. */
  number: number
  laps: IntervalLap[]
  totals: LapTotals
  /** Cumulative time at the end of the interval's last lap. */
  cumulativeTime: number
}

/** The work intervals of an activity and their combined totals. */
export interface WorkIntervals {
  intervals: WorkInterval[]
  total: LapTotals
}

/**
 * Time-weighted mean of one value over the laps that have it.
 *
 * @returns The mean, or `null` when no lap with time has the value.
 */
function weightedMean(laps: ActivityLap[], value: (lap: ActivityLap) => number | null) {
  let weighted = 0
  let time = 0
  for (const lap of laps) {
    const v = value(lap)
    const t = lap.totalElapsedTime ?? 0
    if (v !== null && t > 0) {
      weighted += v * t
      time += t
    }
  }
  return time > 0 ? weighted / time : null
}

/**
 * Sums and averages a run of laps the way Garmin's interval rows do: time and
 * distance add up, pace is total time over total distance, and heart rate,
 * cadence and GAP are averaged by time. A single lap keeps its recorded pace,
 * so it reads the same as on the laps table.
 *
 * @param laps - The laps to combine.
 * @returns Their totals.
 */
export function totalLaps(laps: ActivityLap[]): LapTotals {
  const distance = laps.reduce((sum, lap) => sum + (lap.totalDistance ?? 0), 0)
  const elapsedTime = laps.reduce((sum, lap) => sum + (lap.totalElapsedTime ?? 0), 0)
  const only = laps.length === 1 ? laps[0]! : null
  const avgSpeed = only?.enhancedAvgSpeed ?? (elapsedTime > 0 ? distance / elapsedTime : null)
  const avgPace =
    only?.enhancedAvgPace ?? (distance > 0 && elapsedTime > 0 ? elapsedTime / distance : null)
  const gapSpeed = weightedMean(laps, (lap) => lap.gradeAdjustedAvgSpeed)
  const ascents = laps.map((lap) => lap.totalAscent).filter((v): v is number => v !== null)
  const maxHeartRates = laps.map((lap) => lap.maxHeartRate).filter((v): v is number => v !== null)
  return {
    distance,
    elapsedTime,
    avgSpeed,
    avgPace,
    gapSpeed,
    gapPace: gapSpeed !== null && gapSpeed > 0 ? 1 / gapSpeed : null,
    avgHeartRate: weightedMean(laps, (lap) => lap.avgHeartRate),
    maxHeartRate: maxHeartRates.length > 0 ? Math.max(...maxHeartRates) : null,
    ascent: ascents.length > 0 ? ascents.reduce((sum, v) => sum + v, 0) : null,
    avgCadence: weightedMean(laps, (lap) => lap.avgCadence),
  }
}

/**
 * Groups an activity's laps into work intervals.
 *
 * @param laps - The activity's laps, in order, with their effective intensity.
 * @returns The intervals in order, and the totals over all their laps.
 */
export function groupWorkIntervals(laps: ActivityLap[]): WorkIntervals {
  const groups: IntervalLap[][] = []
  let current: IntervalLap[] | null = null
  let elapsed = 0
  laps.forEach((lap, index) => {
    elapsed += lap.totalElapsedTime ?? 0
    if (!isWorkLap(lap)) {
      current = null
      return
    }
    if (current === null) {
      current = []
      groups.push(current)
    }
    current.push({ lap, lapNumber: index + 1, cumulativeTime: elapsed })
  })

  const intervals = groups.map((group, index) => ({
    number: index + 1,
    laps: group,
    totals: totalLaps(group.map((entry) => entry.lap)),
    cumulativeTime: group[group.length - 1]!.cumulativeTime,
  }))
  return {
    intervals,
    total: totalLaps(groups.flat().map((entry) => entry.lap)),
  }
}

/**
 * Whether the laps describe a structured session worth an intervals view: a
 * distance sport other than swimming, with work laps that cover distance and
 * at least one lap that is not work. A free run (every lap work) or a session
 * without distance (strength sets) has none.
 *
 * @param laps - The activity's laps, with their effective intensity.
 * @param activityType - Numeric activity-type code.
 */
export function hasWorkIntervals(laps: ActivityLap[], activityType: number): boolean {
  if (activityTypeIsSwimming(activityType)) {
    return false
  }
  const work = laps.filter(isWorkLap)
  return (
    work.length > 0 && work.length < laps.length && work.some((lap) => (lap.totalDistance ?? 0) > 0)
  )
}
