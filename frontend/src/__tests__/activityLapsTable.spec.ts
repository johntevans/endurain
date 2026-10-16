import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ActivityLap } from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import ActivityLapsTable from '@/features/activities/components/ActivityLapsTable.vue'

import { makeActivity } from './fixtures/activity'

// Homelab fork: the table asks who is viewing (only the owner gets the lap
// intensity picker) and fetches intensities through apiFetch.
const viewer = vi.hoisted(() => ({ value: null as { id: number } | null }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: viewer }),
}))
vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

beforeEach(() => {
  viewer.value = null
  vi.mocked(apiFetch).mockReset()
})

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
    maxHeartRate: 165,
    avgCadence: 80,
    totalCycles: null,
    intensity: null,
    ...overrides,
  }
}

function mountTable(laps: ActivityLap[], activityType = 1) {
  return mount(ActivityLapsTable, {
    props: { laps, activity: makeActivity({ activityType }), units: 'metric' },
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

describe('ActivityLapsTable columns', () => {
  function cells(wrapper: ReturnType<typeof mountTable>, header: string): (string | undefined)[] {
    const index = headers(wrapper).indexOf(header)
    return wrapper.findAll('tbody tr').map((tr) => tr.findAll('td')[index]?.text())
  }

  it('orders running columns with avg/max heart rate and cadence', () => {
    const wrapper = mountTable([
      makeLap({ intensity: 'active', gradeAdjustedAvgPace: 0.27, gradeAdjustedAvgSpeed: 1 / 0.27 }),
    ])
    expect(headers(wrapper)).toEqual([
      'Lap',
      'Intensity',
      'Distance',
      'Time',
      'Avg pace',
      'GAP',
      'Avg heart rate',
      'Max heart rate',
      'Elevation',
      'Cadence',
    ])
  })

  it('shows running cadence doubled to spm and max heart rate', () => {
    const wrapper = mountTable([makeLap({ avgCadence: 90, maxHeartRate: 171.6 })])
    expect(cells(wrapper, 'Cadence')).toEqual(['180 spm'])
    expect(cells(wrapper, 'Max heart rate')).toEqual(['172 bpm'])
  })

  it('labels the tempo column avg speed and shows rpm for cycling', () => {
    const wrapper = mountTable([makeLap({ avgCadence: 88 })], 4)
    expect(headers(wrapper)).toContain('Avg speed')
    expect(cells(wrapper, 'Cadence')).toEqual(['88 rpm'])
  })

  it('shows a bare stroke rate and no elevation for swimming', () => {
    const wrapper = mountTable([makeLap({ avgCadence: 30 })], 8)
    expect(headers(wrapper)).not.toContain('Elevation')
    expect(headers(wrapper)).not.toContain('Cadence')
    expect(cells(wrapper, 'Stroke rate')).toEqual(['30'])
  })

  it('shows placeholders when heart rate and cadence are missing', () => {
    const wrapper = mountTable([
      makeLap({ avgHeartRate: null, maxHeartRate: null, avgCadence: null }),
    ])
    expect(cells(wrapper, 'Avg heart rate')).toEqual(['--'])
    expect(cells(wrapper, 'Max heart rate')).toEqual(['--'])
    expect(cells(wrapper, 'Cadence')).toEqual(['--'])
  })
})

describe('ActivityLapsTable lap intensity (homelab fork)', () => {
  const OWNER_ID = 7 // makeActivity's userId

  function intensityDto(lapId: number, intensity: string, recorded: string | null, source: string) {
    return { lap_id: lapId, intensity, recorded, source }
  }

  async function mountAsOwner(laps: ActivityLap[], dtos: unknown[]) {
    viewer.value = { id: OWNER_ID }
    vi.mocked(apiFetch).mockResolvedValueOnce(dtos)
    const wrapper = mountTable(laps)
    await flushPromises()
    return wrapper
  }

  it('leaves the table as recorded for anyone but the owner', () => {
    viewer.value = { id: 99 }
    const wrapper = mountTable([makeLap({ intensity: 'active' }), makeLap({ id: 2 })])
    expect(apiFetch).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="lap-intensity-select"]').exists()).toBe(false)
    expect(wrapper.findAll('tbody tr')[1]?.findAll('td')[1]?.text()).toBe('--')
  })

  it('shows the owner a picker with defaulted and edited laps marked', async () => {
    const wrapper = await mountAsOwner(
      [makeLap({ id: 1 }), makeLap({ id: 2, intensity: 'interval' }), makeLap({ id: 3 })],
      [
        intensityDto(1, 'active', null, 'default'),
        intensityDto(2, 'warmup', 'interval', 'override'),
        intensityDto(3, 'rest', null, 'override'),
      ],
    )
    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe('/homelab/lap_intensity?activity_id=1')
    expect(headers(wrapper)).toContain('Intensity')
    const selects = wrapper.findAll<HTMLSelectElement>('[data-testid="lap-intensity-select"]')
    expect(selects.map((select) => select.element.value)).toEqual(['active', 'warmup', 'rest'])
    expect(wrapper.findAll('[data-testid="lap-intensity-default"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="lap-intensity-reset"]')).toHaveLength(2)
    // An override to rest dims the lap like a recorded rest lap.
    expect(wrapper.findAll('tbody tr')[2]?.classes()).toContain('opacity-60')
  })

  it('saves a pick, and clears the override when the recorded value is picked', async () => {
    const wrapper = await mountAsOwner(
      [makeLap({ id: 1, intensity: 'interval' }), makeLap({ id: 2, intensity: 'interval' })],
      [
        intensityDto(1, 'interval', 'interval', 'recorded'),
        intensityDto(2, 'cooldown', 'interval', 'override'),
      ],
    )
    vi.mocked(apiFetch).mockResolvedValueOnce(intensityDto(1, 'warmup', 'interval', 'override'))
    await wrapper.findAll('[data-testid="lap-intensity-select"]')[0]?.setValue('warmup')
    await flushPromises()
    expect(vi.mocked(apiFetch).mock.calls[1]).toEqual([
      '/homelab/lap_intensity/1',
      { method: 'PUT', body: JSON.stringify({ intensity: 'warmup' }) },
    ])

    vi.mocked(apiFetch).mockResolvedValueOnce(intensityDto(2, 'interval', 'interval', 'recorded'))
    await wrapper.findAll('[data-testid="lap-intensity-select"]')[1]?.setValue('interval')
    await flushPromises()
    expect(vi.mocked(apiFetch).mock.calls[2]).toEqual([
      '/homelab/lap_intensity/2',
      { method: 'PUT', body: JSON.stringify({ intensity: null }) },
    ])
  })
})
