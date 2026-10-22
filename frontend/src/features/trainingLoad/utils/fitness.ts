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

/** Intervals.icu's form zones, top to bottom. */
export type FormZoneKey = 'transition' | 'fresh' | 'grey' | 'optimal' | 'highRisk'

/**
 * The zones' edges on Intervals' absolute form scale (the owner's setting):
 * Transition above +20, Fresh +5 to +20, Grey Zone -10 to +5, Optimal -30 to
 * -10, High Risk below -30. `min` is the zone's lowest value, inclusive.
 */
export const FORM_ZONES: ReadonlyArray<{ key: FormZoneKey; min: number }> = [
  { key: 'transition', min: 21 },
  { key: 'fresh', min: 6 },
  { key: 'grey', min: -10 },
  { key: 'optimal', min: -30 },
  { key: 'highRisk', min: Number.NEGATIVE_INFINITY },
]

/** The edges Intervals draws as the form axis's ticks. */
export const FORM_ZONE_TICKS = [20, 5, -10, -30]

/**
 * The zone a form value falls in, judged on the whole number shown (so a
 * displayed +5 is Grey Zone, as its label says).
 */
export function formZone(form: number): FormZoneKey {
  const shown = Math.round(form) || 0
  return FORM_ZONES.find((zone) => shown >= zone.min)?.key ?? 'highRisk'
}

/**
 * Zone colours, picked per theme and checked with the dataviz palette
 * validator against the card surface (colour-blind separation >= 11 ΔE between
 * neighbouring zones, normal vision >= 15). Grey Zone is the neutral middle
 * of a diverging scale; every zone also carries its name.
 */
export const FORM_ZONE_COLORS: Record<'light' | 'dark', Record<FormZoneKey, string>> = {
  light: {
    transition: '#d9930f',
    fresh: '#2a86cf',
    grey: '#a6a6ae',
    optimal: '#5cbd45',
    highRisk: '#9b1c1c',
  },
  dark: {
    transition: '#c4820f',
    fresh: '#4596e0',
    grey: '#6b6b73',
    optimal: '#55ad3d',
    highRisk: '#c4372b',
  },
}

/**
 * Tinted bands for the form chart, one per zone, clipped to the axis range.
 *
 * @param range - The y-axis bounds.
 * @param colors - The theme's zone colours.
 */
export function formZoneBands(
  range: { min: number; max: number },
  colors: Record<FormZoneKey, string>,
): Array<{ from: number; to: number; color: string }> {
  // Bands meet at the drawn ticks (20, 5, -10, -30), not at the whole-number
  // edges the zone test uses.
  const edges: Record<FormZoneKey, [number, number]> = {
    transition: [20, range.max],
    fresh: [5, 20],
    grey: [-10, 5],
    optimal: [-30, -10],
    highRisk: [range.min, -30],
  }
  return FORM_ZONES.map((zone) => ({
    from: edges[zone.key][0],
    to: edges[zone.key][1],
    color: colors[zone.key],
  }))
}

/** The form axis: every zone edge shown, and room for the data. */
export function formAxisRange(forms: readonly number[]): { min: number; max: number } {
  const low = Math.min(-40, ...forms.map((form) => Math.floor(form) - 5))
  const high = Math.max(25, ...forms.map((form) => Math.ceil(form) + 5))
  return { min: low, max: high }
}
