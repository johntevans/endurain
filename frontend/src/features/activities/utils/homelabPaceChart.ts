/**
 * Homelab fork: shapes the pace chart like Garmin's and Strava's: faster pace
 * at the top, an axis scaled to the bulk of the run rather than its worst
 * sample, light smoothing, and a dashed average-pace line.
 */
import type { ChartRenderOptions } from '@/composables/useChartProvider'

import type { Activity, StreamMetric } from '../types'
import { paceToDisplaySeconds, type Units } from './format'

/** X-axis labels per stream chart (upstream draws one per 0.1 km/mi). */
const STREAM_X_MAX_TICKS = 6

/** Samples averaged per point for a watch's own speed (1 s apart). */
export const PACE_SMOOTHING_WINDOW = 5

/** Samples averaged per point for speed derived from GPS fixes (GPX/TCX). */
export const NOISY_PACE_SMOOTHING_WINDOW = 21

/**
 * Median sample-to-sample pace change above which a series counts as GPS-derived.
 * A watch's own speed changes under 0.5% between samples; GPS-derived speed 5–20%.
 */
const NOISY_PACE_JITTER = 0.02

/** Share of samples left outside the axis at each end, so a stop can't stretch it. */
const PACE_RANGE_PERCENTILE = 0.01

/** Most tick intervals the axis may have. */
const PACE_MAX_INTERVALS = 6

/** Clock-friendly tick steps, in seconds. */
const PACE_STEPS = [5, 10, 15, 20, 30, 60, 120, 300, 600, 900] as const
const PACE_LONGEST_STEP = 1800

/** Neutral reference-line colour that reads on both the light and dark card. */
const AVG_LINE_COLOR = '#9ca3af'

/**
 * Smooths pace by averaging speed (its reciprocal) over a centred window, so a
 * single slow sample can't dominate the way averaging pace directly would.
 * Missing samples (`NaN`) are skipped and stay missing.
 *
 * @param data - Pace in display seconds, `NaN` for gaps.
 * @param window - Samples per average.
 * @returns The smoothed pace series.
 */
export function smoothPace(data: number[], window = PACE_SMOOTHING_WINDOW): number[] {
  const half = Math.floor(window / 2)
  return data.map((value, index) => {
    if (Number.isNaN(value)) {
      return Number.NaN
    }
    let speedSum = 0
    let count = 0
    for (let i = Math.max(0, index - half); i <= Math.min(data.length - 1, index + half); i += 1) {
      const pace = data[i] ?? Number.NaN
      if (Number.isFinite(pace) && pace > 0) {
        speedSum += 1 / pace
        count += 1
      }
    }
    return count === 0 ? value : count / speedSum
  })
}

/**
 * Picks the smoothing window: wide for GPS-derived speed, narrow for a watch's
 * own, already filtered, speed.
 *
 * @param data - Pace in display seconds, `NaN` for gaps.
 * @returns Samples per average.
 */
export function paceSmoothingWindow(data: number[]): number {
  const changes: number[] = []
  for (let i = 1; i < data.length; i += 1) {
    const previous = data[i - 1] ?? Number.NaN
    const current = data[i] ?? Number.NaN
    if (Number.isFinite(previous) && Number.isFinite(current) && previous > 0) {
      changes.push(Math.abs(current - previous) / previous)
    }
  }
  changes.sort((a, b) => a - b)
  return percentile(changes, 0.5) > NOISY_PACE_JITTER
    ? NOISY_PACE_SMOOTHING_WINDOW
    : PACE_SMOOTHING_WINDOW
}

/** Value at fraction `p` of an ascending array (nearest rank). */
function percentile(sorted: number[], p: number): number {
  return sorted[Math.round(p * (sorted.length - 1))] ?? Number.NaN
}

/**
 * Picks the pace axis: the 1st–99th percentile of the samples, widened to whole
 * clock-friendly steps (Garmin's 8:33–11:03 run becomes 8:30–11:30).
 *
 * @param data - Pace in display seconds, `NaN` for gaps.
 * @returns The axis bounds and tick step, or `undefined` without samples.
 */
export function paceAxisRange(
  data: number[],
): { min: number; max: number; step: number } | undefined {
  const sorted = data.filter((value) => Number.isFinite(value)).sort((a, b) => a - b)
  if (sorted.length === 0) {
    return undefined
  }
  const low = percentile(sorted, PACE_RANGE_PERCENTILE)
  const high = percentile(sorted, 1 - PACE_RANGE_PERCENTILE)
  const step =
    PACE_STEPS.find((candidate) => (high - low) / candidate <= PACE_MAX_INTERVALS) ??
    PACE_LONGEST_STEP
  const min = Math.max(0, Math.floor(low / step) * step)
  let max = Math.ceil(high / step) * step
  if (max <= min) {
    max = min + step
  }
  return { min, max, step }
}

/**
 * Applies the fork's pace-chart shaping to a pace chart's render options.
 *
 * @param render - The pace chart's render options (one series).
 * @param activity - The activity (type and average pace).
 * @param units - The user's unit system.
 * @returns The reshaped render options.
 */
export function shapePaceChart(
  render: ChartRenderOptions,
  activity: Activity,
  units: Units,
): ChartRenderOptions {
  const [pace, ...rest] = render.series
  if (!pace) {
    return render
  }
  const data = smoothPace(pace.data, paceSmoothingWindow(pace.data))
  const series = [{ ...pace, data }, ...rest]
  if (activity.pace !== null && activity.pace !== undefined && activity.pace > 0) {
    const avg = paceToDisplaySeconds(activity.pace, activity.activityType, units)
    series.push({
      label: 'activities.metrics.avgPace',
      data: data.map(() => avg),
      color: AVG_LINE_COLOR,
      dashed: true,
      legend: false,
    })
  }
  return { ...render, series, invertY: true, yRange: paceAxisRange(data) }
}

/**
 * The fork's adjustments to every stream chart: fewer x-axis labels, and the
 * pace shaping above.
 *
 * @param metric - The chart's metric.
 * @param activity - The activity.
 * @param units - The user's unit system.
 * @param render - Upstream's render options for the chart.
 * @returns The adjusted render options.
 */
export function shapeStreamChart(
  metric: StreamMetric,
  activity: Activity,
  units: Units,
  render: ChartRenderOptions,
): ChartRenderOptions {
  const shaped = { ...render, xMaxTicks: STREAM_X_MAX_TICKS }
  return metric === 'pace' ? shapePaceChart(shaped, activity, units) : shaped
}
