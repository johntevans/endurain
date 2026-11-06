import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ActivityLap } from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import WorkoutIntervalsTable from '@/features/lapIntensity/components/WorkoutIntervalsTable.vue'
import {
  groupWorkIntervals,
  hasWorkIntervals,
  totalLaps,
} from '@/features/lapIntensity/utils/intervals'

import { makeActivity } from './fixtures/activity'

// The table asks who is viewing (only the owner's intensity overrides apply).
const viewer = vi.hoisted(() => ({ value: null as { id: number } | null }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: viewer }),
}))
vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

beforeEach(() => {
  viewer.value = null
  vi.mocked(apiFetch).mockReset()
})

let nextId = 1

function makeLap(
  intensity: string | null,
  distance: number,
  time: number,
  extra = {},
): ActivityLap {
  return {
    id: nextId++,
    totalDistance: distance,
    totalElapsedTime: time,
    totalTimerTime: time,
    enhancedAvgPace: time / distance,
    enhancedAvgSpeed: distance / time,
    gradeAdjustedAvgPace: null,
    gradeAdjustedAvgSpeed: null,
    totalAscent: 2,
    avgHeartRate: 140,
    maxHeartRate: 150,
    avgCadence: 90,
    totalCycles: null,
    intensity,
    ...extra,
  }
}

/** The shape of a real NSM long run: 3 × 10 min, each auto-lapped at the mile. */
function nsmLong(): ActivityLap[] {
  return [
    makeLap('warmup', 1609, 575),
    makeLap('warmup', 423, 147),
    makeLap('rest', 155, 120),
    makeLap('active', 1609, 427, { avgHeartRate: 137, maxHeartRate: 145 }),
    makeLap('active', 657, 173, { avgHeartRate: 140, maxHeartRate: 148 }),
    makeLap('rest', 164, 120),
    makeLap('active', 1609, 427),
    makeLap('active', 645, 173),
    makeLap('rest', 150, 120),
    makeLap('active', 1609, 423),
    makeLap('active', 672, 177),
    makeLap('cooldown', 1609, 525),
    makeLap('cooldown', 672, 219),
  ]
}

describe('groupWorkIntervals', () => {
  it('joins consecutive work laps and breaks on any other intensity', () => {
    const { intervals } = groupWorkIntervals(nsmLong())
    expect(intervals.map((i) => i.laps.map((l) => l.lapNumber))).toEqual([
      [4, 5],
      [7, 8],
      [10, 11],
    ])
  })

  it('totals an interval like Garmin: summed time and distance, pace from them', () => {
    const first = groupWorkIntervals(nsmLong()).intervals[0]!
    expect(first.totals.elapsedTime).toBe(600)
    expect(first.totals.distance).toBe(2266)
    expect(first.totals.avgPace).toBeCloseTo(600 / 2266)
    // Heart rate is time-weighted; max is the max.
    expect(first.totals.avgHeartRate).toBeCloseTo((137 * 427 + 140 * 173) / 600)
    expect(first.totals.maxHeartRate).toBe(148)
    // Cumulative time runs from the activity's start, rests and warm-up included.
    expect(first.laps.map((l) => l.cumulativeTime)).toEqual([1269, 1442])
    expect(first.cumulativeTime).toBe(1442)
  })

  it('totals every interval together', () => {
    const { total } = groupWorkIntervals(nsmLong())
    expect(total.elapsedTime).toBe(1800)
    expect(total.distance).toBe(1609 + 657 + 1609 + 645 + 1609 + 672)
  })

  it('treats a lap without intensity as active, and interval as work', () => {
    const { intervals } = groupWorkIntervals([
      makeLap(null, 1000, 240),
      makeLap('interval', 1000, 240),
      makeLap('recovery', 200, 90),
      makeLap('active', 1000, 240),
    ])
    expect(intervals.map((i) => i.laps.length)).toEqual([2, 1])
  })
})

describe('totalLaps', () => {
  it('time-weights GAP over the laps that have it', () => {
    const totals = totalLaps([
      makeLap('active', 1000, 300, { gradeAdjustedAvgSpeed: 4 }),
      makeLap('active', 1000, 100, { gradeAdjustedAvgSpeed: 2 }),
      makeLap('active', 1000, 100),
    ])
    expect(totals.gapSpeed).toBeCloseTo(3.5)
    expect(totals.gapPace).toBeCloseTo(1 / 3.5)
  })

  it('leaves GAP empty when no lap has one', () => {
    expect(totalLaps([makeLap('active', 1000, 300)]).gapSpeed).toBeNull()
  })
})

describe('hasWorkIntervals', () => {
  it('is true for a structured run', () => {
    expect(hasWorkIntervals(nsmLong(), 1)).toBe(true)
  })

  it('is false for a free run whose laps are all work', () => {
    expect(hasWorkIntervals([makeLap('interval', 1609, 500), makeLap(null, 1609, 500)], 1)).toBe(
      false,
    )
  })

  it('is false for swims and for sessions without distance', () => {
    expect(hasWorkIntervals(nsmLong(), 8)).toBe(false)
    expect(hasWorkIntervals([makeLap('active', 0, 60), makeLap('rest', 0, 60)], 1)).toBe(false)
  })
})

describe('WorkoutIntervalsTable', () => {
  function mountTable(laps: ActivityLap[]) {
    return mount(WorkoutIntervalsTable, {
      props: { laps, activity: makeActivity({ activityType: 1 }), units: 'imperial' },
      global: {
        plugins: [
          i18n,
          [
            VueQueryPlugin,
            { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          ],
        ] as never,
      },
    })
  }

  it('shows each interval, its laps, and a total', () => {
    const wrapper = mountTable(nsmLong())
    const kinds = wrapper.findAll('tbody tr').map((tr) => tr.attributes('data-kind'))
    expect(kinds).toEqual([
      'interval', 'lap', 'lap',
      'interval', 'lap', 'lap',
      'interval', 'lap', 'lap',
      'total',
    ]) // prettier-ignore
    const first = wrapper
      .find('tbody tr')
      .findAll('td')
      .map((td) => td.text())
    // Int, Lap, Time, Cumulative time, Distance, Pace…
    expect(first.slice(0, 5)).toEqual(['1', '', '10:00.0', '24:02.0', '1.41 mi'])
    const rows = wrapper.findAll('tbody tr')
    const total = rows[rows.length - 1]!.findAll('td').map((td) => td.text())
    expect(total[0]).toBe('Total')
    expect(total[2]).toBe('30:00.0')
  })

  it('puts a one-lap interval on a single row naming its lap', () => {
    const wrapper = mountTable([
      makeLap('warmup', 1609, 560),
      makeLap('active', 720, 180),
      makeLap('rest', 80, 60),
      makeLap('active', 720, 180),
    ])
    const rows = wrapper.findAll('tbody tr')
    expect(rows.map((tr) => tr.attributes('data-kind'))).toEqual(['interval', 'interval', 'total'])
    expect(rows[1]!.findAll('td')[1]!.text()).toBe('4')
  })
})
