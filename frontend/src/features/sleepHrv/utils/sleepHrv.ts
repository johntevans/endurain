// Homelab fork: nightly HRV formatting and chart shaping.
import type { ChartSeries } from '@/composables/useChartProvider'
import type { SleepHrvEntry, SleepHrvStatus } from '@/features/sleepHrv/types'

/**
 * Formats HRV in whole milliseconds, as the Eight Sleep app does (71.5 → "72 ms").
 *
 * @param ms - HRV in milliseconds.
 */
export function formatHrv(ms: number): string {
  return `${Math.round(ms)} ms`
}

/**
 * Formats the usual range, e.g. "66–80 ms".
 *
 * @returns The range, or `null` when either edge is unknown.
 */
export function formatHrvRange(low: number | null, high: number | null): string | null {
  if (low === null || high === null) return null
  return `${Math.round(low)}–${Math.round(high)} ms`
}

/**
 * Where a night sits against its own usual range: one night's HRV is noisy,
 * and being outside the range is the signal worth reading.
 *
 * @returns The status, or `null` when the night has no range.
 */
export function hrvStatus(entry: SleepHrvEntry): SleepHrvStatus | null {
  if (entry.rangeLowMs === null || entry.rangeHighMs === null) return null
  if (entry.hrvMs < entry.rangeLowMs) return 'below'
  if (entry.hrvMs > entry.rangeHighMs) return 'above'
  return 'within'
}

/** Colours for {@link hrvChartSeries}, resolved by the caller from theme tokens. */
export interface HrvChartColors {
  nightly: string
  average: string
  range: string
}

/** Labels for {@link hrvChartSeries}, already translated. */
export interface HrvChartLabels {
  nightly: string
  average: string
  range: string
}

/**
 * The chart's series, oldest first: the nightly value, its 7-day average
 * (dashed), and the usual range as two faint lines. The range is drawn per
 * night rather than as one band because it moves (about 88–108 ms in 2022
 * against 65–80 ms in 2026), so a fixed band would misstate older nights.
 * A missing value is drawn as a gap (`NaN`).
 *
 * @param entries - Nights, newest first as the API returns them.
 */
export function hrvChartSeries(
  entries: SleepHrvEntry[],
  colors: HrvChartColors,
  labels: HrvChartLabels,
): { dates: string[]; series: ChartSeries[] } {
  const ordered = entries.slice().reverse()
  const value = (v: number | null) => (v === null ? Number.NaN : Math.round(v * 10) / 10)
  return {
    dates: ordered.map((entry) => entry.date),
    series: [
      {
        label: labels.nightly,
        data: ordered.map((entry) => value(entry.hrvMs)),
        color: colors.nightly,
        fill: false,
      },
      {
        label: labels.average,
        data: ordered.map((entry) => value(entry.avg7dMs)),
        color: colors.average,
        dashed: true,
        fill: false,
      },
      {
        label: labels.range,
        data: ordered.map((entry) => value(entry.rangeHighMs)),
        color: colors.range,
        fill: false,
      },
      {
        label: labels.range,
        data: ordered.map((entry) => value(entry.rangeLowMs)),
        color: colors.range,
        fill: false,
        legend: false,
      },
    ],
  }
}
