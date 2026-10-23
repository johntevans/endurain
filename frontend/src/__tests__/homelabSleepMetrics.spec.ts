// Homelab fork: nightly HRV (features/sleepHrv).
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { SleepHrvEntry } from '@/features/sleepHrv/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import SleepHrvListItem from '@/features/sleepHrv/components/SleepHrvListItem.vue'
import { HEALTH_ZONES } from '@/features/health/healthNav'
import {
  fetchLatestSleepHrv,
  fetchSleepHrv,
  mapSleepHrv,
} from '@/features/sleepHrv/services/sleepHrv'
import {
  formatHrv,
  formatHrvRange,
  hrvChartSeries,
  hrvStatus,
} from '@/features/sleepHrv/utils/sleepHrv'
import { mount } from '@vue/test-utils'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const DTO = {
  date: '2026-10-08',
  hrv_ms: 71.5,
  avg_7d_ms: 72.7,
  baseline_ms: 72.9,
  range_low_ms: 65.6,
  range_high_ms: 80.2,
  source: 'eight_sleep',
}

function night(overrides: Partial<SleepHrvEntry> = {}): SleepHrvEntry {
  return { ...mapSleepHrv(DTO), ...overrides }
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('sleep HRV service', () => {
  it('maps the DTO', () => {
    expect(mapSleepHrv(DTO)).toEqual({
      date: '2026-10-08',
      hrvMs: 71.5,
      avg7dMs: 72.7,
      baselineMs: 72.9,
      rangeLowMs: 65.6,
      rangeHighMs: 80.2,
      source: 'eight_sleep',
    })
  })

  it('pages the list but fetches the whole window for the chart', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ total: 1, records: [DTO] })

    await fetchSleepHrv({ interval: 'last_30_days', page: 2, numRecords: 25 })
    await fetchSleepHrv({ interval: 'all_time' })

    expect(vi.mocked(apiFetch).mock.calls.map((call) => call[0])).toEqual([
      '/homelab/sleep_hrv?interval=last_30_days&page_number=2&num_records=25',
      '/homelab/sleep_hrv?interval=all_time',
    ])
  })

  it('returns null when there is no latest night', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchLatestSleepHrv()).toBeNull()
  })
})

describe('sleep HRV formatting', () => {
  it('rounds like the Eight Sleep app (71.5 shows as 72)', () => {
    expect(formatHrv(71.5)).toBe('72 ms')
    expect(formatHrvRange(65.6, 80.2)).toBe('66–80 ms')
    expect(formatHrvRange(null, 80.2)).toBeNull()
  })

  it('places a night against its own usual range', () => {
    expect(hrvStatus(night())).toBe('within')
    expect(hrvStatus(night({ hrvMs: 49.2 }))).toBe('below')
    expect(hrvStatus(night({ hrvMs: 95 }))).toBe('above')
    expect(hrvStatus(night({ rangeLowMs: null }))).toBeNull()
  })
})

describe('sleep HRV chart series', () => {
  const colors = { nightly: '#111111', average: '#222222', range: '#333333' }
  const labels = { nightly: 'HRV', average: '7-day average', range: 'Usual range' }

  it('is oldest first, with the average dashed and one legend entry for the range', () => {
    const newestFirst = [
      night({ date: '2026-10-09', hrvMs: 75 }),
      night({ date: '2026-10-08', avg7dMs: null }),
    ]

    const { dates, series } = hrvChartSeries(newestFirst, colors, labels)

    expect(dates).toEqual(['2026-10-08', '2026-10-09'])
    expect(series.map((s) => s.label)).toEqual([
      'HRV',
      '7-day average',
      'Usual range',
      'Usual range',
    ])
    expect(series[0]?.data).toEqual([71.5, 75])
    expect(series[1]?.dashed).toBe(true)
    // A missing average is a gap, not a zero.
    expect(Number.isNaN(series[1]?.data[0])).toBe(true)
    expect(series[2]?.data).toEqual([80.2, 80.2])
    expect(series[3]?.data).toEqual([65.6, 65.6])
    expect(series[3]?.legend).toBe(false)
  })
})

describe('sleep HRV wiring', () => {
  it('is a health zone right after resting heart rate', () => {
    const names = HEALTH_ZONES.map((zone) => zone.name)
    expect(names.indexOf('health-hrv')).toBe(names.indexOf('health-rhr') + 1)
  })

  it('flags a night outside its usual range in the list', () => {
    const wrapper = mount(SleepHrvListItem, {
      props: { entry: night({ hrvMs: 49.2 }) },
      global: { plugins: [i18n] },
    })

    expect(wrapper.text()).toContain('49 ms')
    expect(wrapper.text()).toContain('Below usual')
    expect(wrapper.text()).toContain('7-day avg 73 ms')
    expect(wrapper.text()).toContain('usual 66–80 ms')
  })
})
