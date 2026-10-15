import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { ActivityLap } from '@/features/activities/types'

import i18n from '@/i18n'
import ActivityLapsTable from '@/features/activities/components/ActivityLapsTable.vue'

import { makeActivity } from './fixtures/activity'

function makeLap(overrides: Partial<ActivityLap> = {}): ActivityLap {
  return {
    id: 1,
    totalDistance: 1000,
    totalElapsedTime: 300,
    totalTimerTime: 300,
    enhancedAvgPace: 0.3,
    enhancedAvgSpeed: 1 / 0.3,
    gradeAdjustedAvgPace: null,
    gradeAdjustedAvgSpeed: null,
    totalAscent: 10,
    avgHeartRate: 150,
    avgCadence: 80,
    totalCycles: null,
    intensity: null,
    ...overrides,
  }
}

function mountTable(laps: ActivityLap[], activityType = 1) {
  return mount(ActivityLapsTable, {
    props: { laps, activity: makeActivity({ activityType }), units: 'metric' },
    global: { plugins: [i18n] },
  })
}

function headers(wrapper: ReturnType<typeof mountTable>): string[] {
  return wrapper.findAll('th').map((th) => th.text())
}

describe('ActivityLapsTable GAP column', () => {
  it('shows grade-adjusted pace for running laps that have it', () => {
    const wrapper = mountTable([
      makeLap({ id: 1, gradeAdjustedAvgPace: 0.27, gradeAdjustedAvgSpeed: 1 / 0.27 }),
      makeLap({ id: 2 }),
    ])
    expect(headers(wrapper)).toContain('GAP')
    const gapIndex = headers(wrapper).indexOf('GAP')
    const cells = wrapper.findAll('tbody tr').map((tr) => tr.findAll('td')[gapIndex]?.text())
    // 0.27 s/m → 4:30 /km; the lap without GAP shows a placeholder.
    expect(cells[0]).toContain('4:30')
    expect(cells[1]).toBe('--')
  })

  it('hides the column when no lap has grade-adjusted pace', () => {
    expect(headers(mountTable([makeLap()]))).not.toContain('GAP')
  })

  it('hides the column for non-running/walking activities', () => {
    const lap = makeLap({ gradeAdjustedAvgPace: 0.27, gradeAdjustedAvgSpeed: 1 / 0.27 })
    expect(headers(mountTable([lap], 4))).not.toContain('GAP')
  })
})
