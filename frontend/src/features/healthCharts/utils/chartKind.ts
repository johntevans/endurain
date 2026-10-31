// Homelab fork: the geometry of a health chart at its record count.
import type { ChartKind } from '@/composables/useChartProvider'

/**
 * Most bars a health chart draws. Past this a phone gives each bar under 3 px,
 * and at a year or more they fade into stripes.
 */
const MAX_BARS = 100

/**
 * Picks bars for a short window and a line for a long one.
 *
 * @param points - Records the chart plots.
 * @returns The chart kind.
 */
export function healthChartKind(points: number): ChartKind {
  return points > MAX_BARS ? 'line' : 'bar'
}
