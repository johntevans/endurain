// Homelab fork: nightly HRV and heart rate (features/sleepMetrics).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import type { NightlyMetricEntry } from '@/features/sleepMetrics/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import router from '@/router'
import NightlyMetricListItem from '@/features/sleepMetrics/components/NightlyMetricListItem.vue'
import { HEALTH_ZONES } from '@/features/health/healthNav'
import {
  fetchLatestNightlyMetric,
  fetchNightlyMetric,
  mapNightlyMetric,
} from '@/features/sleepMetrics/services/sleepMetrics'
import {
  formatNightlyMetric,
  formatNightlyMetricRange,
  nightlyMetricChartSeries,
  nightlyMetricStatus,
} from '@/features/sleepMetrics/utils/sleepMetrics'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const HRV_DTO = {
  date: '2026-10-08',
  hrv_ms: 71.5,
  avg_7d_ms: 72.7,
  baseline_ms: 72.9,
  range_low_ms: 65.6,
  range_high_ms: 80.2,
  source: 'eight_sleep',
}

const HR_DTO = {
  date: '2026-10-08',
  hr_bpm: 43,
  avg_7d_bpm: 43.6,
  baseline_bpm: 44.1,
  range_low_bpm: 42.3,
  range_high_bpm: 45.9,
  source: 'eight_sleep',
}

function night(overrides: Partial<NightlyMetricEntry> = {}): NightlyMetricEntry {
  return { ...mapNightlyMetric('hrv', HRV_DTO), ...overrides }
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('nightly metric service', () => {
  it('maps each metric to the same shape', () => {
    expect(mapNightlyMetric('hrv', HRV_DTO)).toEqual({
      date: '2026-10-08',
      value: 71.5,
      avg7d: 72.7,
      baseline: 72.9,
      rangeLow: 65.6,
      rangeHigh: 80.2,
      source: 'eight_sleep',
    })
    expect(mapNightlyMetric('heartRate', HR_DTO)).toEqual({
      date: '2026-10-08',
      value: 43,
      avg7d: 43.6,
      baseline: 44.1,
      rangeLow: 42.3,
      rangeHigh: 45.9,
      source: 'eight_sleep',
    })
  })

  it('treats a missing derived value as null', () => {
    expect(mapNightlyMetric('heartRate', { ...HR_DTO, range_low_bpm: null }).rangeLow).toBeNull()
  })

  it('calls each metric’s endpoint, paging the list but not the chart', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ total: 1, records: [HR_DTO] })

    await fetchNightlyMetric('hrv', { interval: 'last_30_days', page: 2, numRecords: 25 })
    await fetchNightlyMetric('heartRate', { interval: 'all_time' })

    expect(vi.mocked(apiFetch).mock.calls.map((call) => call[0])).toEqual([
      '/homelab/sleep_hrv?interval=last_30_days&page_number=2&num_records=25',
      '/homelab/sleep_heart_rate?interval=all_time',
    ])
  })

  it('returns null when there is no latest night', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchLatestNightlyMetric('heartRate')).toBeNull()
    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe('/homelab/sleep_heart_rate/latest')
  })
})

describe('nightly metric formatting', () => {
  it('rounds like the Eight Sleep app, in each metric’s unit', () => {
    expect(formatNightlyMetric('hrv', 71.5)).toBe('72 ms')
    expect(formatNightlyMetric('heartRate', 43.4)).toBe('43 bpm')
    expect(formatNightlyMetricRange('heartRate', 42.3, 45.9)).toBe('42–46 bpm')
    expect(formatNightlyMetricRange('hrv', null, 80.2)).toBeNull()
  })

  it('places a night against its own usual range', () => {
    expect(nightlyMetricStatus(night())).toBe('within')
    expect(nightlyMetricStatus(night({ value: 49.2 }))).toBe('below')
    expect(nightlyMetricStatus(night({ value: 95 }))).toBe('above')
    expect(nightlyMetricStatus(night({ rangeLow: null }))).toBeNull()
  })
})

describe('nightly metric chart series', () => {
  const colors = { nightly: '#111111', average: '#222222', range: '#333333' }
  const labels = { nightly: 'Heart rate', average: '7-day average', range: 'Usual range' }

  it('is oldest first, with the average dashed and one legend entry for the range', () => {
    const newestFirst = [
      night({ date: '2026-10-09', value: 75 }),
      night({ date: '2026-10-08', avg7d: null }),
    ]

    const { dates, series } = nightlyMetricChartSeries(newestFirst, colors, labels)

    expect(dates).toEqual(['2026-10-08', '2026-10-09'])
    expect(series.map((entry) => entry.label)).toEqual([
      'Heart rate',
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

/** The props the router passes to a named route's own (innermost) record. */
function leafProps(name: string): unknown {
  const matched = router.resolve({ name }).matched
  return matched[matched.length - 1]?.props
}

describe('nightly metric wiring', () => {
  it('puts HRV right after resting heart rate in the health nav', () => {
    const names = HEALTH_ZONES.map((zone) => zone.name)
    expect(names.indexOf('health-hrv')).toBe(names.indexOf('health-rhr') + 1)
  })

  it('serves both zones from the shared view, by kind', () => {
    expect(leafProps('health-rhr')).toEqual({
      default: { kind: 'heartRate' },
    })
    expect(leafProps('health-hrv')).toEqual({
      default: { kind: 'hrv' },
    })
  })

  it('flags a heart-rate night above its usual range in the list', () => {
    const wrapper = mount(NightlyMetricListItem, {
      props: { kind: 'heartRate', entry: { ...mapNightlyMetric('heartRate', HR_DTO), value: 50 } },
      global: { plugins: [i18n] },
    })

    expect(wrapper.text()).toContain('50 bpm')
    expect(wrapper.text()).toContain('Above usual')
    expect(wrapper.text()).toContain('7-day avg 44 bpm')
    expect(wrapper.text()).toContain('usual 42–46 bpm')
  })
})
