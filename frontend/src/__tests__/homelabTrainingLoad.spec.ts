// Homelab fork: the activity page's training-load tile and the fitness page.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { FitnessDay } from '@/features/trainingLoad/types'

import { apiFetch } from '@/services/http'
import { buildChartConfiguration } from '@/providers/chartJsChartProvider'
import i18n from '@/i18n'
import ActivityLoadPill from '@/features/trainingLoad/components/ActivityLoadPill.vue'
import FitnessView from '@/features/trainingLoad/views/FitnessView.vue'
import { mapActivityLoad, mapFitness } from '@/features/trainingLoad/services/trainingLoad'
import {
  fitnessRangeDates,
  fitnessWeekRows,
  formatSigned,
  formatSignedDecimal,
  formatWhole,
  parseFitnessRange,
  warmupEnd,
} from '@/features/trainingLoad/utils/fitness'

import { makeActivity } from './fixtures/activity'

const viewer = vi.hoisted(() => ({ value: null as { id: number } | null }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: viewer }),
}))
vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const OWNER_ID = 7 // makeActivity's userId

beforeEach(() => {
  viewer.value = null
  vi.mocked(apiFetch).mockReset()
})

function loadDto(overrides: Record<string, unknown> = {}) {
  return { activity_id: 1, load: 74, source: 'pace', pace_load: 74, hr_load: 48, ...overrides }
}

async function mountPill(viewerId: number | null, dto?: unknown) {
  viewer.value = viewerId === null ? null : { id: viewerId }
  if (dto !== undefined) {
    vi.mocked(apiFetch).mockResolvedValueOnce(dto)
  }
  const wrapper = mount(ActivityLoadPill, {
    props: { activity: makeActivity() },
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
  await flushPromises()
  return wrapper
}

describe('ActivityLoadPill (homelab fork)', () => {
  it('shows the owner the load and where it came from', async () => {
    const wrapper = await mountPill(OWNER_ID, loadDto())
    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe('/homelab/training_load?activity_id=1')
    const tile = wrapper.get('[data-testid="activity-training-load"]')
    expect(tile.text()).toContain('Load')
    expect(tile.text()).toContain('74')
    expect(tile.text()).toContain('pace')
  })

  it("shows a strength session's 0 with its HR load beside it, like Intervals", async () => {
    const wrapper = await mountPill(
      OWNER_ID,
      loadDto({ load: 0, source: 'none', pace_load: null, hr_load: 11 }),
    )
    const tile = wrapper.get('[data-testid="activity-training-load"]')
    expect(tile.text()).toContain('0')
    expect(tile.text()).toContain('HR 11')
  })

  it('renders nothing when the activity has no load', async () => {
    const wrapper = await mountPill(
      OWNER_ID,
      loadDto({ load: null, source: null, pace_load: null, hr_load: null }),
    )
    expect(wrapper.find('[data-testid="activity-training-load"]').exists()).toBe(false)
  })

  it('sends no request for anyone but the owner', async () => {
    const wrapper = await mountPill(99)
    expect(apiFetch).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="activity-training-load"]').exists()).toBe(false)
  })

  it('maps the DTO, defaulting missing values to null', () => {
    expect(mapActivityLoad({ activity_id: 3 })).toEqual({
      activityId: 3,
      load: null,
      source: null,
      paceLoad: null,
      hrLoad: null,
    })
  })
})

describe('fitness helpers (homelab fork)', () => {
  function day(date: string, overrides: Partial<FitnessDay> = {}): FitnessDay {
    return { date, load: 0, fitness: 50, fatigue: 60, form: -10, ramp: 1, ...overrides }
  }

  it('turns a range into dates ending today', () => {
    expect(fitnessRangeDates('6w', '2026-10-22')).toEqual({
      startDate: '2026-09-11',
      endDate: '2026-10-22',
    })
    expect(fitnessRangeDates('1y', '2026-10-22').startDate).toBe('2025-10-23')
    expect(parseFitnessRange('6m')).toBe('6m')
    expect(parseFitnessRange('9y')).toBe('3m')
    expect(parseFitnessRange(undefined)).toBe('3m')
  })

  it('sums each week and keeps its last day, newest first', () => {
    const rows = fitnessWeekRows(
      [
        day('2026-10-17', { load: 132, fitness: 53 }),
        day('2026-10-18', { load: 0, fitness: 53.9, fatigue: 63.4, form: -9.5, ramp: 2.1 }),
        day('2026-10-19', { load: 0, fitness: 52.6 }),
        day('2026-10-22', { load: 0, fitness: 49, fatigue: 35.8, form: 13.2, ramp: -5 }),
      ],
      'monday',
    )
    expect(rows).toEqual([
      { start: '2026-10-19', load: 0, fitness: 49, fatigue: 35.8, form: 13.2, ramp: -5 },
      { start: '2026-10-12', load: 132, fitness: 53.9, fatigue: 63.4, form: -9.5, ramp: 2.1 },
    ])
  })

  it('flags the warm-up only when the shown days reach into it', () => {
    expect(warmupEnd([day('2026-02-01')], '2026-01-01')).toBe('2026-03-26')
    expect(warmupEnd([day('2026-07-01')], '2026-01-01')).toBeNull()
    expect(warmupEnd([], '2026-01-01')).toBeNull()
  })

  it('formats like Intervals: whole numbers, signed form and ramp', () => {
    expect(formatWhole(53.9)).toBe('54')
    expect(formatWhole(-0.2)).toBe('0')
    expect(formatSigned(13.2)).toBe('+13')
    expect(formatSigned(-9.6)).toBe('-10')
    expect(formatSigned(0.3)).toBe('0')
    expect(formatSignedDecimal(2.06)).toBe('+2.1')
    expect(formatSignedDecimal(-5)).toBe('-5.0')
    expect(formatSignedDecimal(0.01)).toBe('0.0')
  })

  it('maps the fitness DTO', () => {
    expect(
      mapFitness({
        loads_start: '2026-01-01',
        has_settings: true,
        days: [{ date: '2026-10-22', load: 0, fitness: 49, fatigue: 35.8, form: 13.2, ramp: -5 }],
      }),
    ).toEqual({
      loadsStart: '2026-01-01',
      hasSettings: true,
      days: [{ date: '2026-10-22', load: 0, fitness: 49, fatigue: 35.8, form: 13.2, ramp: -5 }],
    })
  })
})

describe('FitnessView (homelab fork)', () => {
  async function mountView(dto: unknown) {
    viewer.value = { id: OWNER_ID }
    vi.mocked(apiFetch).mockResolvedValue(dto)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/fitness', name: 'fitness', component: FitnessView }],
    })
    await router.push('/fitness')
    const wrapper = mount(FitnessView, {
      global: {
        plugins: [
          i18n,
          router,
          [
            VueQueryPlugin,
            { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          ],
        ] as never,
      },
    })
    await flushPromises()
    return wrapper
  }

  it("shows today's values and the weekly table", async () => {
    const wrapper = await mountView({
      loads_start: '2026-01-01',
      has_settings: true,
      days: [
        { date: '2026-10-18', load: 0, fitness: 53.9, fatigue: 63.4, form: -9.5, ramp: 2.1 },
        { date: '2026-10-22', load: 0, fitness: 49, fatigue: 35.8, form: 13.2, ramp: -5 },
      ],
    })
    const call = vi.mocked(apiFetch).mock.calls[0]?.[0] as string
    expect(call).toMatch(
      /^\/homelab\/training_load\/fitness\?start_date=\d{4}-\d{2}-\d{2}&end_date=/,
    )
    const todayCard = wrapper.get('[data-testid="fitness-today"]').text()
    expect(todayCard).toContain('49')
    expect(todayCard).toContain('36')
    expect(todayCard).toContain('+13')
    expect(todayCard).toContain('-5.0')
    expect(wrapper.findAll('[data-testid="fitness-weeks"] tbody tr')).toHaveLength(2)
    expect(wrapper.find('[data-testid="fitness-warmup"]').exists()).toBe(false)
  })

  it('explains what to do without thresholds', async () => {
    const wrapper = await mountView({ loads_start: '2026-01-01', has_settings: false, days: [] })
    expect(wrapper.text()).toContain('No training load yet')
    expect(wrapper.find('[data-testid="fitness-today"]').exists()).toBe(false)
  })
})

describe('chart hover by x position (homelab fork)', () => {
  it('is opt-in', () => {
    const hovered = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'Fitness', data: [1] }],
      hoverIndex: true,
    })
    expect(hovered.options?.interaction).toEqual({ mode: 'index', intersect: false })
    const plain = buildChartConfiguration({ kind: 'line', series: [{ label: 'A', data: [1] }] })
    expect(plain.options?.interaction).toBeUndefined()
  })
})
