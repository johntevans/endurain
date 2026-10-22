/**
 * Homelab fork: pure helpers for the fitness page (ranges, weekly rows,
 * number formatting).
 */
import type { Schemas } from '@/types'

import type { FitnessDay, FitnessRangeKey, FitnessWeekRow } from '@/features/trainingLoad/types'
import { addDays, weekOf } from '@/features/trainingLog/utils/trainingLog'

/** Days in each range, ending today. */
export const FITNESS_RANGE_DAYS: Record<FitnessRangeKey, number> = {
  '6w': 42,
  '3m': 91,
  '6m': 182,
  '1y': 365,
}

export const FITNESS_RANGES = Object.keys(FITNESS_RANGE_DAYS) as FitnessRangeKey[]

export const DEFAULT_FITNESS_RANGE: FitnessRangeKey = '3m'

/**
 * Fitness starts from zero where the loads start, and needs about two 42-day
 * time constants (e^-2, under 14% short) before it reads true.
 */
export const FITNESS_WARMUP_DAYS = 84

/** Parses a `?range=` value, falling back to the default. */
export function parseFitnessRange(value: unknown): FitnessRangeKey {
  return typeof value === 'string' && value in FITNESS_RANGE_DAYS
    ? (value as FitnessRangeKey)
    : DEFAULT_FITNESS_RANGE
}

/** The inclusive local dates a range covers, ending on `today`. */
export function fitnessRangeDates(
  range: FitnessRangeKey,
  today: string,
): { startDate: string; endDate: string } {
  return { startDate: addDays(today, -(FITNESS_RANGE_DAYS[range] - 1)), endDate: today }
}

/**
 * The day the warm-up ends, when the shown days include part of it (the
 * values there read low); otherwise `null`.
 */
export function warmupEnd(days: readonly FitnessDay[], loadsStart: string): string | null {
  const end = addDays(loadsStart, FITNESS_WARMUP_DAYS)
  const first = days[0]?.date
  return first !== undefined && first < end ? end : null
}

/**
 * One row per calendar week, newest first: the week's summed load and the
 * values on its last day in the series (Sunday for a past week, today for
 * the current one), as Intervals.icu's weekly summary shows them.
 */
export function fitnessWeekRows(
  days: readonly FitnessDay[],
  firstDayOfWeek: Schemas['WeekDay'],
): FitnessWeekRow[] {
  const rows = new Map<string, FitnessWeekRow>()
  for (const day of days) {
    const start = weekOf(day.date, firstDayOfWeek).start
    const row = rows.get(start)
    rows.set(start, {
      start,
      load: (row?.load ?? 0) + day.load,
      fitness: day.fitness,
      fatigue: day.fatigue,
      form: day.form,
      ramp: day.ramp,
    })
  }
  return [...rows.values()].reverse()
}

/** A value as Intervals.icu shows it: a whole number. */
export function formatWhole(value: number): string {
  return String(Math.round(value) || 0)
}

/** A whole number with its sign (form, ramp): `+13`, `-10`, `0`. */
export function formatSigned(value: number): string {
  const whole = Math.round(value) || 0
  return whole > 0 ? `+${whole}` : String(whole)
}

/** One decimal with its sign, for a ramp rate: `+2.1`, `-5.0`. */
export function formatSignedDecimal(value: number): string {
  const fixed = (Math.round(value * 10) / 10 || 0).toFixed(1)
  return value >= 0.05 ? `+${fixed}` : fixed
}
