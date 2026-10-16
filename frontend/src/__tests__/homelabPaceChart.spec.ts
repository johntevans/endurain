/** Homelab fork: the Garmin-style pace chart and the chart-provider options it uses. */
import { describe, expect, it } from 'vitest'

import type { ActivityStream } from '@/features/activities/types'

import {
  paceAxisRange,
  paceSmoothingWindow,
  shapeStreamChart,
  smoothPace,
} from '@/features/activities/utils/homelabPaceChart'
import { buildStreamChart } from '@/features/activities/utils/streams'
import { buildChartConfiguration } from '@/providers/chartJsChartProvider'

import { makeActivity } from './fixtures/activity'

function paceStream(paces: number[]): ActivityStream {
  return { id: 6, streamType: 6, waypoints: paces.map((pace) => ({ pace })), hrZones: null }
}

describe('smoothPace', () => {
  it('averages speed, not pace, over the window', () => {
    // 300 s and 600 s: mean speed is (1/300 + 1/600) / 2 → 400 s, not 450 s.
    expect(smoothPace([300, 600], 3)).toEqual([400, 400])
  })

  it('keeps gaps and skips them inside a window', () => {
    const smoothed = smoothPace([300, Number.NaN, 300], 3)
    expect(smoothed[0]).toBe(300)
    expect(Number.isNaN(smoothed[1])).toBe(true)
    expect(smoothed[2]).toBe(300)
  })

  it('flattens a one-sample spike', () => {
    const smoothed = smoothPace([540, 540, 1600, 540, 540])
    expect(Math.max(...smoothed)).toBeLessThan(700)
  })
})

describe('paceSmoothingWindow', () => {
  it('keeps a watch speed lightly smoothed', () => {
    expect(paceSmoothingWindow([540, 540, 541, 542, 542, Number.NaN, 541])).toBe(5)
  })

  it('smooths GPS-derived speed harder', () => {
    expect(paceSmoothingWindow([540, 650, 470, 600, 520, 610])).toBe(21)
  })

  it('treats too few samples as clean', () => {
    expect(paceSmoothingWindow([540])).toBe(5)
  })
})

describe('paceAxisRange', () => {
  it('ignores the slowest and fastest 1% and snaps to clock-friendly steps', () => {
    // 8:33–11:03 with two outliers (a stop and a GPS jump) beyond the percentiles.
    const data = Array.from({ length: 300 }, (_, i) => 513 + (150 * i) / 299)
    data[0] = 300
    data[299] = 1600
    expect(paceAxisRange(data)).toEqual({ min: 510, max: 690, step: 30 })
  })

  it('widens a constant series to one step and skips gaps', () => {
    expect(paceAxisRange([Number.NaN, 300, 300])).toEqual({ min: 300, max: 305, step: 5 })
  })

  it('has no range without samples', () => {
    expect(paceAxisRange([Number.NaN])).toBeUndefined()
  })
})

describe('pace stream chart', () => {
  // 0.33 s/m → 330 s/km; the activity's average 0.3 s/m → 300 s/km.
  const chart = buildStreamChart(
    paceStream([0.33, 0.33, 0.33]),
    makeActivity({ activityType: 1, distance: 1000, pace: 0.3 }),
    'metric',
  )

  it('inverts the axis and fixes its range', () => {
    expect(chart?.render.invertY).toBe(true)
    expect(chart?.render.yRange).toEqual({ min: 330, max: 335, step: 5 })
  })

  it('adds a dashed average-pace line kept out of the legend', () => {
    const avg = chart?.render.series[1]
    expect(avg?.label).toBe('activities.metrics.avgPace')
    expect(avg?.dashed).toBe(true)
    expect(avg?.legend).toBe(false)
    expect(avg?.data[0]).toBeCloseTo(300)
    expect(avg?.data).toHaveLength(3)
  })

  it('caps the x-axis labels', () => {
    expect(chart?.render.xMaxTicks).toBe(6)
  })
})

describe('shapeStreamChart', () => {
  it('leaves other metrics un-inverted and un-scaled', () => {
    const render = shapeStreamChart('hr', makeActivity(), 'metric', {
      kind: 'line',
      series: [{ label: 'HR', data: [120, 130] }],
    })
    expect(render.invertY).toBeUndefined()
    expect(render.yRange).toBeUndefined()
    expect(render.series).toHaveLength(1)
    expect(render.xMaxTicks).toBe(6)
  })
})

describe('chart provider options', () => {
  const config = buildChartConfiguration({
    kind: 'line',
    series: [
      { label: 'Pace', data: [330, 340] },
      { label: 'Avg', data: [335, 335], dashed: true, legend: false },
    ],
    invertY: true,
    yRange: { min: 300, max: 360, step: 30 },
    xMaxTicks: 6,
  })

  it('fills toward the bottom edge on an inverted axis', () => {
    const dataset = config.data.datasets[0] as Record<string, unknown> | undefined
    expect(dataset?.fill).toBe('start')
  })

  it('applies the fixed y-range and x-label cap', () => {
    const y = config.options?.scales?.y as Record<string, unknown> | undefined
    expect(y?.min).toBe(300)
    expect(y?.max).toBe(360)
    expect((y?.ticks as Record<string, unknown>).stepSize).toBe(30)
    const x = config.options?.scales?.x as Record<string, unknown> | undefined
    expect(x?.ticks).toEqual({ maxTicksLimit: 6, maxRotation: 0 })
  })

  it('hides legend-less series from the legend', () => {
    const legend = config.options?.plugins?.legend as
      | { display?: boolean; labels?: { filter?: (item: { datasetIndex: number }) => boolean } }
      | undefined
    expect(legend?.display).toBe(false)
    expect(legend?.labels?.filter?.({ datasetIndex: 0 })).toBe(true)
    expect(legend?.labels?.filter?.({ datasetIndex: 1 })).toBe(false)
  })
})
