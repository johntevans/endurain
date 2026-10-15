/**
 * Pure helpers for the training log: the week/year layout, filters, circle
 * sizes and styles, and the metric formatting. Dates are `YYYY-MM-DD` strings
 * computed in UTC so they never drift with the viewer's timezone.
 */
import type { Schemas } from '@/types'

import type { ActivityTagKey } from '@/features/activityTags/types'
import type { Units } from '@/features/activities/utils/format'
import type {
  CircleStyle,
  SportFamily,
  SportFilter,
  TagFilter,
  TrainingLogActivity,
  TrainingLogMetric,
  TrainingLogWeek,
} from '@/features/trainingLog/types'

import { isActivityTagKey } from '@/features/activityTags/utils/activityTags'
import {
  activityTypeIsCycling,
  activityTypeIsRunning,
  activityTypeIsSwimming,
  activityTypeIsWalking,
} from '@/features/activities/utils/activityType'
import { weekStart } from '@/utils/datetime'
import { kmToMiles } from '@/utils/units'

const MS_PER_DAY = 86_400_000
const METERS_TO_FEET = 3.28084
const METERS_PER_YARD = 0.9144

// ---------------------------------------------------------------------------
// Dates and weeks
// ---------------------------------------------------------------------------

function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, day ?? 1))
}

function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

/** Adds whole days to a `YYYY-MM-DD` date. */
export function addDays(iso: string, days: number): string {
  return toIsoDate(new Date(parseIsoDate(iso).getTime() + days * MS_PER_DAY))
}

/**
 * Today's date in the viewer's local timezone (not UTC, which would already be
 * tomorrow on a US evening).
 */
export function localTodayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

/** The week containing a date, starting on the user's first weekday. */
export function weekOf(iso: string, firstDayOfWeek: Schemas['WeekDay']): TrainingLogWeek {
  const start = weekStart(iso, firstDayOfWeek)
  const days = Array.from({ length: 7 }, (_, index) => addDays(start, index))
  return { start, days, anchor: days[3] ?? start }
}

/** The year a week belongs to (that of its fourth day). */
export function weekYear(week: TrainingLogWeek): number {
  return Number(week.anchor.slice(0, 4))
}

/** The month a week belongs to, as `YYYY-MM` (that of its fourth day). */
export function weekMonth(week: TrainingLogWeek): string {
  return week.anchor.slice(0, 7)
}

/**
 * Every week from the one holding `firstDate` to the one holding `lastDate`,
 * grouped by year, newest year and newest week first (the order the log
 * scrolls in).
 *
 * @param firstDate - Oldest date to show (the first activity).
 * @param lastDate - Newest date to show (today, or a later activity).
 * @param firstDayOfWeek - The user's first weekday.
 * @returns `[year, weeks]` pairs, newest first.
 */
export function buildTrainingLogYears(
  firstDate: string,
  lastDate: string,
  firstDayOfWeek: Schemas['WeekDay'],
): Array<{ year: number; weeks: TrainingLogWeek[] }> {
  const oldest = weekOf(firstDate <= lastDate ? firstDate : lastDate, firstDayOfWeek).start
  const years: Array<{ year: number; weeks: TrainingLogWeek[] }> = []
  let week = weekOf(lastDate, firstDayOfWeek)
  while (week.start >= oldest) {
    const year = weekYear(week)
    const last = years[years.length - 1]
    if (last?.year === year) {
      last.weeks.push(week)
    } else {
      years.push({ year, weeks: [week] })
    }
    week = weekOf(addDays(week.start, -7), firstDayOfWeek)
  }
  return years
}

/** The inclusive date window covering a list of weeks (in any order). */
export function weeksWindow(
  weeks: readonly TrainingLogWeek[],
): { startDate: string; endDate: string } | null {
  if (weeks.length === 0) {
    return null
  }
  const starts = weeks.map((week) => week.start).sort()
  const first = starts[0] as string
  const last = starts[starts.length - 1] as string
  return { startDate: first, endDate: addDays(last, 6) }
}

/**
 * The index of the first (newest) week of a month within a year's weeks, or
 * the nearest older week when the month has none (e.g. a month before the
 * first activity), or `-1` when nothing is that old.
 */
export function monthWeekIndex(weeks: readonly TrainingLogWeek[], month: string): number {
  return weeks.findIndex((week) => weekMonth(week) <= month)
}

/** The months a year's weeks cover, as `YYYY-MM`, newest first. */
export function yearMonths(weeks: readonly TrainingLogWeek[]): string[] {
  return [...new Set(weeks.map(weekMonth))]
}

/**
 * A week's short label, e.g. "Oct 12 – 18", "Sep 28 – Oct 4" or
 * "Dec 29 – Jan 4".
 */
export function weekRangeLabel(week: TrainingLogWeek, locale: string): string {
  const first = parseIsoDate(week.start)
  const last = parseIsoDate(week.days[6] ?? week.start)
  const monthDay = new Intl.DateTimeFormat(locale, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
  const dayOnly = new Intl.DateTimeFormat(locale, { day: 'numeric', timeZone: 'UTC' })
  const sameMonth = first.getUTCMonth() === last.getUTCMonth()
  return `${monthDay.format(first)} – ${sameMonth ? dayOnly.format(last) : monthDay.format(last)}`
}

/** Groups activities by local date. */
export function groupByDate(
  activities: readonly TrainingLogActivity[],
): Map<string, TrainingLogActivity[]> {
  const byDate = new Map<string, TrainingLogActivity[]>()
  for (const activity of activities) {
    const list = byDate.get(activity.localDate)
    if (list) {
      list.push(activity)
    } else {
      byDate.set(activity.localDate, [activity])
    }
  }
  return byDate
}

// ---------------------------------------------------------------------------
// Sports and filters
// ---------------------------------------------------------------------------

/** The colour/scale family of an activity type. */
export function sportFamily(activityType: number): SportFamily {
  if (activityTypeIsRunning(activityType)) {
    return 'run'
  }
  if (activityTypeIsCycling(activityType)) {
    return 'ride'
  }
  if (activityTypeIsSwimming(activityType)) {
    return 'swim'
  }
  if (activityTypeIsWalking(activityType)) {
    return 'walk'
  }
  return 'other'
}

/** Label keys for the family filter options (`trainingLog.sports.*`). */
export const SPORT_FAMILY_LABEL_KEYS: Record<SportFamily, string> = {
  run: 'trainingLog.sports.run',
  ride: 'trainingLog.sports.ride',
  swim: 'trainingLog.sports.swim',
  walk: 'trainingLog.sports.walk',
  other: 'trainingLog.sports.other',
}

const FILTER_FAMILIES = ['run', 'ride', 'swim', 'walk'] as const

/** One option of the sport filter. */
export interface SportFilterOption {
  value: SportFilter
  /** Set for families; a single type is labelled from its activity type. */
  labelKey?: string
  /** Set for single types. */
  activityType?: number
}

/**
 * The sport filter's options for the types a user has: the families they
 * have activities in (Run, Ride, Swim, Walk & Hike), then each remaining
 * type on its own. "All sports" is not included.
 */
export function sportFilterOptions(typeCodes: readonly number[]): SportFilterOption[] {
  const families = new Set(typeCodes.map(sportFamily))
  const options: SportFilterOption[] = FILTER_FAMILIES.filter((family) => families.has(family)).map(
    (family) => ({ value: family, labelKey: SPORT_FAMILY_LABEL_KEYS[family] }),
  )
  for (const code of [...typeCodes].sort((a, b) => a - b)) {
    if (sportFamily(code) === 'other') {
      options.push({ value: `type-${code}`, activityType: code })
    }
  }
  return options
}

/** Whether an activity type passes the sport filter. */
export function matchesSport(activityType: number, filter: SportFilter): boolean {
  if (filter === 'all') {
    return true
  }
  if (filter.startsWith('type-')) {
    return activityType === Number(filter.slice(5))
  }
  return sportFamily(activityType) === filter
}

/** Whether an activity's tags pass the tag filter. */
export function matchesTag(tags: readonly ActivityTagKey[], filter: TagFilter): boolean {
  return filter === 'all' || tags.includes(filter)
}

/** Parses the `sport` query param; anything unknown means all sports. */
export function parseSportFilter(value: unknown): SportFilter {
  if (typeof value !== 'string') {
    return 'all'
  }
  if ((FILTER_FAMILIES as readonly string[]).includes(value)) {
    return value as SportFilter
  }
  const match = /^type-(\d+)$/.exec(value)
  return match && Number(match[1]) > 0 ? (value as SportFilter) : 'all'
}

/** Parses the `tag` query param; anything unknown means all tags. */
export function parseTagFilter(value: unknown): TagFilter {
  return isActivityTagKey(value) ? value : 'all'
}

/** Parses the `metric` query param; defaults to time, as Strava does for runs. */
export function parseMetric(value: unknown): TrainingLogMetric {
  return value === 'distance' || value === 'elevation' ? value : 'time'
}

/** The sport family the filter shows (for the legend), or `null` for a mix. */
export function filterFamily(filter: SportFilter): SportFamily | null {
  if (filter === 'all') {
    return null
  }
  if (filter.startsWith('type-')) {
    return sportFamily(Number(filter.slice(5)))
  }
  return filter as SportFamily
}

// ---------------------------------------------------------------------------
// Circles
// ---------------------------------------------------------------------------

/**
 * How an activity's circle is drawn, from its tags: a race stands out most,
 * then workouts (any NSM session is a workout), then long runs.
 */
export function circleStyle(tags: readonly ActivityTagKey[]): CircleStyle {
  if (tags.includes('race')) {
    return 'race'
  }
  if (tags.some((tag) => tag === 'workout' || tag.startsWith('nsm_'))) {
    return 'workout'
  }
  if (tags.includes('long_run')) {
    return 'long'
  }
  return 'base'
}

/** An activity's value for a metric, in seconds or metres. */
export function metricValue(activity: TrainingLogActivity, metric: TrainingLogMetric): number {
  switch (metric) {
    case 'time':
      return activity.movingTime > 0 ? activity.movingTime : activity.elapsedTime
    case 'distance':
      return activity.distance
    case 'elevation':
      return Math.max(activity.elevationGain ?? 0, 0)
  }
}

/** Sum of a metric over activities. */
export function metricTotal(
  activities: readonly TrainingLogActivity[],
  metric: TrainingLogMetric,
): number {
  return activities.reduce((sum, activity) => sum + metricValue(activity, metric), 0)
}

/**
 * The value that fills a whole circle, per metric and sport. Fixed rather
 * than relative to the data on screen, so a circle keeps its size as more
 * years load.
 */
const FULL_CIRCLE: Record<TrainingLogMetric, Record<SportFamily, number>> = {
  time: { run: 10_800, ride: 14_400, swim: 7_200, walk: 10_800, other: 7_200 },
  distance: { run: 32_000, ride: 120_000, swim: 4_000, walk: 20_000, other: 30_000 },
  elevation: { run: 1_000, ride: 2_000, swim: 1_000, walk: 1_500, other: 1_000 },
}

/** The smallest circle, as a fraction of the largest. */
export const MIN_CIRCLE_FRACTION = 0.3

/**
 * A circle's diameter as a fraction of the largest circle. Area grows with
 * the value (diameter with its square root), as on Strava, between
 * {@link MIN_CIRCLE_FRACTION} and 1.
 */
export function circleFraction(
  value: number,
  metric: TrainingLogMetric,
  activityType: number,
): number {
  const full = FULL_CIRCLE[metric][sportFamily(activityType)]
  const ratio = Math.min(Math.max(value / full, 0), 1)
  return MIN_CIRCLE_FRACTION + (1 - MIN_CIRCLE_FRACTION) * Math.sqrt(ratio)
}

/**
 * How much a day's circles shrink when it has several activities, so the
 * overlapping cluster still fits its column.
 */
export function clusterScale(count: number): number {
  if (count <= 1) {
    return 1
  }
  return count === 2 ? 0.74 : 0.6
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

/** A formatted value and its unit (empty when embedded, as for times). */
export interface FormattedValue {
  value: string
  unit: string
}

/** `1h 20m`, `55m` (Strava's training-log style). */
export function formatLogDuration(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds / 60))
  const hours = Math.floor(whole / 60)
  const minutes = whole % 60
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`
}

/** `1:23:45`, or `40:53` under an hour: a race result. */
export function formatClock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds))
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const secs = String(whole % 60).padStart(2, '0')
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${secs}` : `${minutes}:${secs}`
}

/**
 * Formats a metric value. Distances are km/mi with one decimal, except a
 * swim-only view, which counts metres/yards.
 *
 * @param value - Seconds (time) or metres (distance, elevation).
 * @param metric - Which metric the value is.
 * @param units - The user's unit system.
 * @param swim - Whether to show distance in pool units.
 * @returns The formatted value and unit.
 */
export function formatMetricValue(
  value: number,
  metric: TrainingLogMetric,
  units: Units,
  swim = false,
): FormattedValue {
  const imperial = units === 'imperial'
  switch (metric) {
    case 'time':
      return { value: formatLogDuration(value), unit: '' }
    case 'distance': {
      if (swim) {
        const pool = imperial ? value / METERS_PER_YARD : value
        return { value: Math.round(pool).toLocaleString('en-US'), unit: imperial ? 'yd' : 'm' }
      }
      const km = value / 1000
      const shown = imperial ? kmToMiles(km) : km
      return { value: shown.toFixed(1), unit: imperial ? 'mi' : 'km' }
    }
    case 'elevation': {
      const shown = imperial ? value * METERS_TO_FEET : value
      return { value: Math.round(shown).toLocaleString('en-US'), unit: imperial ? 'ft' : 'm' }
    }
  }
}

/** A {@link FormattedValue} as one string. */
export function joinValue(formatted: FormattedValue): string {
  return formatted.unit ? `${formatted.value} ${formatted.unit}` : formatted.value
}
