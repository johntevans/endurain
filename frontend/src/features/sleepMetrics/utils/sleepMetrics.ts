// Homelab fork: nightly metric formatting and chart shaping.
import type { ChartSeries } from '@/composables/useChartProvider'
import type {
  NightlyMetricEntry,
  NightlyMetricKind,
  NightlyMetricStatus,
} from '@/features/sleepMetrics/types'

import { NIGHTLY_METRICS } from '@/features/sleepMetrics/metrics'

/**
 * Formats a value in whole units, as the Eight Sleep app does (HRV 71.5 → "72 ms").
 */
export function formatNightlyMetric(kind: NightlyMetricKind, value: number): string {
  return `${Math.round(value)} ${NIGHTLY_METRICS[kind].unit}`
}

/**
 * Formats the usual range, e.g. "66–80 ms".
 *
 * @returns The range, or `null` when either edge is unknown.
 */
export function formatNightlyMetricRange(
  kind: NightlyMetricKind,
  low: number | null,
  high: number | null,
): string | null {
  if (low === null || high === null) return null
  return `${Math.round(low)}–${Math.round(high)} ${NIGHTLY_METRICS[kind].unit}`
}

/**
 * Where a night sits against its own usual range: one night is noisy, and
 * being outside the range is the signal worth reading.
 *
 * @returns The status, or `null` when the night has no range.
 */
export function nightlyMetricStatus(entry: NightlyMetricEntry): NightlyMetricStatus | null {
  if (entry.rangeLow === null || entry.rangeHigh === null) return null
  if (entry.value < entry.rangeLow) return 'below'
  if (entry.value > entry.rangeHigh) return 'above'
  return 'within'
}

/** Colours for {@link nightlyMetricChartSeries}, resolved by the caller from theme tokens. */
export interface NightlyMetricChartColors {
  nightly: string
  average: string
  range: string
}

/** Labels for {@link nightlyMetricChartSeries}, already translated. */
export interface NightlyMetricChartLabels {
  nightly: string
  average: string
  range: string
}

/**
 * The chart's series, oldest first: the nightly value, its 7-day average
 * (dashed), and the usual range as two faint lines. The range is drawn per
 * night rather than as one band because it moves (HRV's was about 88–108 ms
 * in 2022 against 65–80 ms in 2026), so a fixed band would misstate older
 * nights. A missing value is drawn as a gap (`NaN`).
 *
 * @param entries - Nights, newest first as the API returns them.
 */
export function nightlyMetricChartSeries(
  entries: NightlyMetricEntry[],
  colors: NightlyMetricChartColors,
  labels: NightlyMetricChartLabels,
): { dates: string[]; series: ChartSeries[] } {
  const ordered = entries.slice().reverse()
  const value = (v: number | null) => (v === null ? Number.NaN : Math.round(v * 10) / 10)
  return {
    dates: ordered.map((entry) => entry.date),
    series: [
      {
        label: labels.nightly,
        data: ordered.map((entry) => value(entry.value)),
        color: colors.nightly,
        fill: false,
      },
      {
        label: labels.average,
        data: ordered.map((entry) => value(entry.avg7d)),
        color: colors.average,
        dashed: true,
        fill: false,
      },
      {
        label: labels.range,
        data: ordered.map((entry) => value(entry.rangeHigh)),
        color: colors.range,
        fill: false,
      },
      {
        label: labels.range,
        data: ordered.map((entry) => value(entry.rangeLow)),
        color: colors.range,
        fill: false,
        legend: false,
      },
    ],
  }
}
