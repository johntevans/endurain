// Homelab fork: training log (Strava-style week-by-week view).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { SportFilter, TagFilter, TrainingLogActivity } from '@/features/trainingLog/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import TrainingLogDay from '@/features/trainingLog/components/TrainingLogDay.vue'
import TrainingLogLegend from '@/features/trainingLog/components/TrainingLogLegend.vue'
import TrainingLogWeek from '@/features/trainingLog/components/TrainingLogWeek.vue'
import TrainingLogYear from '@/features/trainingLog/components/TrainingLogYear.vue'
import TrainingLogView from '@/features/trainingLog/views/TrainingLogView.vue'
import {
  fetchTrainingLog,
  fetchTrainingLogRange,
} from '@/features/trainingLog/services/trainingLog'
import {
  addDays,
  buildTrainingLogYears,
  circleFraction,
  circleStyle,
  clusterScale,
  filterFamilies,
  formatClock,
  formatLogDuration,
  formatMetricValue,
  groupByDate,
  localTodayIso,
  matchesSport,
  matchesTag,
  metricHasQuality,
  metricTotal,
  metricValue,
  MIN_CIRCLE_FRACTION,
  monthWeekIndex,
  parseMetric,
  parseSportFilter,
  parseTagFilter,
  qualityPercent,
  qualityTotal,
  sportFamily,
  sportFilterOptions,
  weekMonth,
  weekOf,
  weekRangeLabel,
  weeksWindow,
  weekYear,
  yearMonths,
} from '@/features/trainingLog/utils/trainingLog'

vi.mock('@/services/http', () => {
  class HttpError extends Error {
    constructor(
      readonly status: number,
      statusText: string,
      readonly detail: unknown = null,
    ) {
      super(`HTTP ${status} ${statusText}`)
      this.name = 'HttpError'
    }
  }
  return { apiFetch: vi.fn<typeof apiFetch>(), HttpError }
})

vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ units: 'metric', firstDayOfWeek: 'monday' }) }),
}))

vi.mock('@/features/activities/composables/useActivities', () => ({
  useUserActivityTypeMapQuery: () => ({
    data: ref(
      new Map([
        [1, 'Run'],
        [4, 'Ride'],
        [14, 'Yoga'],
      ]),
    ),
  }),
}))

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

function makeLogActivity(overrides: Partial<TrainingLogActivity> = {}): TrainingLogActivity {
  return {
    id: 1,
    name: 'Morning Run',
    activityType: 1,
    localDate: '2026-10-12',
    startTime: '2026-10-12T07:00:00',
    distance: 10_000,
    movingTime: 3_600,
    elapsedTime: 3_700,
    elevationGain: 80,
    tags: [],
    qualityTime: 0,
    qualityDistance: 0,
    ...overrides,
  }
}

function withPlugins() {
  return {
    plugins: [
      i18n,
      [
        VueQueryPlugin,
        { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
      ],
    ] as never,
    stubs: { RouterLink: RouterLinkStub },
  }
}

describe('training log weeks and years', () => {
  it('builds a week from the first weekday, anchored on its fourth day', () => {
    expect(weekOf('2026-10-15', 'monday')).toEqual({
      start: '2026-10-12',
      days: [
        '2026-10-12',
        '2026-10-13',
        '2026-10-14',
        '2026-10-15',
        '2026-10-16',
        '2026-10-17',
        '2026-10-18',
      ],
      anchor: '2026-10-15',
    })
    expect(weekOf('2026-10-15', 'sunday').start).toBe('2026-10-11')
  })

  it('puts a week split across New Year in the year that holds most of it', () => {
    // Mon 2025-12-29 .. Sun 2026-01-04: Thursday is 2026-01-01.
    expect(weekYear(weekOf('2025-12-30', 'monday'))).toBe(2026)
    // Mon 2026-12-28 .. Sun 2027-01-03: Thursday is 2026-12-31.
    expect(weekYear(weekOf('2027-01-02', 'monday'))).toBe(2026)
    expect(weekMonth(weekOf('2026-09-30', 'monday'))).toBe('2026-10')
  })

  it('lists every week between two dates, newest year and week first', () => {
    const years = buildTrainingLogYears('2025-12-20', '2026-01-10', 'monday')
    expect(years.map((entry) => entry.year)).toEqual([2026, 2025])
    expect(years[0]?.weeks.map((week) => week.start)).toEqual(['2026-01-05', '2025-12-29'])
    expect(years[1]?.weeks.map((week) => week.start)).toEqual(['2025-12-22', '2025-12-15'])
  })

  it('tolerates a range given backwards and a single day', () => {
    expect(buildTrainingLogYears('2026-10-15', '2026-10-15', 'monday')).toHaveLength(1)
    expect(buildTrainingLogYears('2026-10-20', '2026-10-15', 'monday')[0]?.weeks).toHaveLength(1)
  })

  it('covers a set of weeks with one inclusive window', () => {
    const { weeks } = buildTrainingLogYears('2026-01-01', '2026-03-01', 'monday')[0] ?? {
      weeks: [],
    }
    expect(weeksWindow(weeks)).toEqual({ startDate: '2025-12-29', endDate: '2026-03-01' })
    expect(weeksWindow([])).toBeNull()
  })

  it('finds where a month starts and which months a year shows', () => {
    const { weeks } = buildTrainingLogYears('2026-01-01', '2026-10-15', 'monday')[0] ?? {
      weeks: [],
    }
    expect(yearMonths(weeks).slice(0, 3)).toEqual(['2026-10', '2026-09', '2026-08'])
    expect(yearMonths(weeks).slice(-1)).toEqual(['2026-01'])
    const september = monthWeekIndex(weeks, '2026-09')
    expect(weekMonth(weeks[september] as never)).toBe('2026-09')
    expect(weekMonth(weeks[september - 1] as never)).toBe('2026-10')
    expect(monthWeekIndex(weeks, '2025-06')).toBe(-1)
  })

  it('labels weeks within and across months', () => {
    expect(weekRangeLabel(weekOf('2026-10-15', 'monday'), 'en')).toBe('Oct 12 – 18')
    expect(weekRangeLabel(weekOf('2026-10-01', 'monday'), 'en')).toBe('Sep 28 – Oct 4')
  })

  it('adds days and reads the local date', () => {
    expect(addDays('2026-02-27', 2)).toBe('2026-03-01')
    expect(addDays('2026-01-01', -1)).toBe('2025-12-31')
    expect(localTodayIso(new Date(2026, 9, 15, 23, 30))).toBe('2026-10-15')
  })
})

describe('training log filters', () => {
  it('groups types into sport families', () => {
    expect([1, 40, 4, 28, 8, 12, 14].map(sportFamily)).toEqual([
      'run',
      'run',
      'ride',
      'ride',
      'swim',
      'walk',
      'other',
    ])
  })

  it('offers the families a user has, then other types one by one', () => {
    expect(sportFilterOptions([19, 1, 2, 14, 4])).toEqual([
      { value: 'run', labelKey: 'trainingLog.sports.run' },
      { value: 'ride', labelKey: 'trainingLog.sports.ride' },
      { value: 'type-14', activityType: 14 },
      { value: 'type-19', activityType: 19 },
    ])
  })

  it('matches sports, single types and tags', () => {
    expect(matchesSport(2, ['run'])).toBe(true)
    expect(matchesSport(4, ['run'])).toBe(false)
    expect(matchesSport(14, ['type-14'])).toBe(true)
    expect(matchesSport(19, ['type-14'])).toBe(false)
    expect(matchesSport(19, [])).toBe(true)
    // Ticked sports are alternatives: runs or physical therapy.
    expect(matchesSport(2, ['run', 'type-1001'])).toBe(true)
    expect(matchesSport(1001, ['run', 'type-1001'])).toBe(true)
    expect(matchesSport(4, ['run', 'type-1001'])).toBe(false)
    expect(matchesTag(['race'], ['race'])).toBe(true)
    expect(matchesTag([], ['race'])).toBe(false)
    expect(matchesTag([], [])).toBe(true)
    // Ticked tags must all be there.
    expect(matchesTag(['workout', 'long_run'], ['workout', 'long_run'])).toBe(true)
    expect(matchesTag(['workout', 'long_run', 'race'], ['workout', 'long_run'])).toBe(true)
    expect(matchesTag(['workout'], ['workout', 'long_run'])).toBe(false)
  })

  it('parses URL params, ignoring junk', () => {
    expect(parseSportFilter('ride')).toEqual(['ride'])
    expect(parseSportFilter('type-14')).toEqual(['type-14'])
    expect(parseSportFilter('run,type-1001,run')).toEqual(['run', 'type-1001'])
    expect(parseSportFilter('type-0')).toEqual([])
    expect(parseSportFilter('other,swim,')).toEqual(['swim'])
    expect(parseSportFilter(['run'])).toEqual([])
    expect(parseSportFilter(undefined)).toEqual([])
    expect(parseTagFilter('nsm_long')).toEqual(['nsm_long'])
    expect(parseTagFilter('workout,long_run')).toEqual(['workout', 'long_run'])
    expect(parseTagFilter('tempo,race')).toEqual(['race'])
    expect(parseMetric('elevation')).toBe('elevation')
    expect(parseMetric('pace')).toBe('time')
    expect(filterFamilies([])).toEqual([])
    expect(filterFamilies(['type-14'])).toEqual(['other'])
    expect(filterFamilies(['swim'])).toEqual(['swim'])
    expect(filterFamilies(['run', 'type-1001', 'swim', 'type-14'])).toEqual([
      'run',
      'other',
      'swim',
    ])
  })
})

describe('training log circles and numbers', () => {
  it('styles races over workouts over long runs', () => {
    expect(circleStyle(['race', 'workout', 'long_run'])).toBe('race')
    expect(circleStyle(['long_run', 'workout'])).toBe('workout')
    expect(circleStyle(['nsm_medium'])).toBe('workout')
    expect(circleStyle(['long_run'])).toBe('long')
    expect(circleStyle([])).toBe('base')
  })

  it('reads metric values, falling back to elapsed time', () => {
    const activity = makeLogActivity()
    expect(metricValue(activity, 'time')).toBe(3_600)
    expect(metricValue(makeLogActivity({ movingTime: 0 }), 'time')).toBe(3_700)
    expect(metricValue(activity, 'distance')).toBe(10_000)
    expect(metricValue(makeLogActivity({ elevationGain: null }), 'elevation')).toBe(0)
    expect(metricTotal([activity, activity], 'distance')).toBe(20_000)
  })

  it('totals quality work and its share, with none for elevation', () => {
    const workout = makeLogActivity({ qualityTime: 1_800, qualityDistance: 6_000 })
    const easy = makeLogActivity()
    expect(qualityTotal([workout, easy], 'time')).toBe(1_800)
    expect(qualityTotal([workout, easy], 'distance')).toBe(6_000)
    expect(qualityTotal([workout, easy], 'elevation')).toBe(0)
    expect(metricHasQuality('time')).toBe(true)
    expect(metricHasQuality('elevation')).toBe(false)
    expect(qualityPercent(1_800, 7_200)).toBe(25)
    expect(qualityPercent(1_000, 3_000)).toBe(33)
    expect(qualityPercent(0, 0)).toBe(0)
    // Lap sums can run a little past the activity's own time.
    expect(qualityPercent(3_610, 3_600)).toBe(100)
  })

  it('sizes circles by area between a floor and a full circle', () => {
    expect(circleFraction(0, 'time', 1)).toBe(MIN_CIRCLE_FRACTION)
    expect(circleFraction(10_800, 'time', 1)).toBe(1)
    expect(circleFraction(99_999, 'time', 1)).toBe(1)
    const quarter = circleFraction(2_700, 'time', 1)
    expect(quarter).toBeCloseTo(MIN_CIRCLE_FRACTION + (1 - MIN_CIRCLE_FRACTION) * 0.5)
    // A 30 km ride is a smaller circle than a 30 km run.
    expect(circleFraction(30_000, 'distance', 4)).toBeLessThan(
      circleFraction(30_000, 'distance', 1),
    )
    expect([1, 2, 3, 5].map(clusterScale)).toEqual([1, 0.74, 0.6, 0.6])
  })

  it('formats times, distances and elevations', () => {
    expect(formatLogDuration(4_800)).toBe('1h 20m')
    expect(formatLogDuration(3_300)).toBe('55m')
    expect(formatClock(2_453)).toBe('40:53')
    expect(formatClock(5_025)).toBe('1:23:45')
    expect(formatMetricValue(42_195, 'distance', 'metric')).toEqual({ value: '42.2', unit: 'km' })
    expect(formatMetricValue(42_195, 'distance', 'imperial')).toEqual({ value: '26.2', unit: 'mi' })
    expect(formatMetricValue(2_500, 'distance', 'metric', true)).toEqual({
      value: '2,500',
      unit: 'm',
    })
    expect(formatMetricValue(1_000, 'elevation', 'imperial')).toEqual({
      value: '3,281',
      unit: 'ft',
    })
    expect(formatMetricValue(4_800, 'time', 'metric')).toEqual({ value: '1h 20m', unit: '' })
  })

  it('groups activities by local date', () => {
    const grouped = groupByDate([
      makeLogActivity({ id: 1 }),
      makeLogActivity({ id: 2 }),
      makeLogActivity({ id: 3, localDate: '2026-10-13' }),
    ])
    expect(grouped.get('2026-10-12')?.map((activity) => activity.id)).toEqual([1, 2])
    expect(grouped.get('2026-10-13')?.map((activity) => activity.id)).toEqual([3])
  })
})

describe('training log service', () => {
  it('fetches a window and maps it', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([
      {
        id: 5,
        name: 'Half',
        activity_type: 1,
        local_date: '2026-10-04',
        start_time: '2026-10-04T07:30:00',
        distance: 21_097,
        total_timer_time: 5_400,
        total_elapsed_time: 5_420,
        elevation_gain: null,
        tags: ['long_run', 'race'],
        quality_time: 5_400,
        quality_distance: 21_097,
      },
    ])

    const result = await fetchTrainingLog({ startDate: '2025-12-29', endDate: '2027-01-03' })

    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe(
      '/homelab/training_log?start_date=2025-12-29&end_date=2027-01-03',
    )
    expect(result).toEqual([
      {
        id: 5,
        name: 'Half',
        activityType: 1,
        localDate: '2026-10-04',
        startTime: '2026-10-04T07:30:00',
        distance: 21_097,
        movingTime: 5_400,
        elapsedTime: 5_420,
        elevationGain: null,
        tags: ['race', 'long_run'],
        qualityTime: 5_400,
        qualityDistance: 21_097,
      },
    ])
  })

  it('treats a null body as no activities, and reads the range', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchTrainingLog({ startDate: '2026-01-01', endDate: '2026-01-07' })).toEqual([])

    vi.mocked(apiFetch).mockResolvedValueOnce({ first_date: '2021-03-02', last_date: null })
    expect(await fetchTrainingLogRange()).toEqual({ firstDate: '2021-03-02', lastDate: null })
    expect(vi.mocked(apiFetch).mock.calls[1]?.[0]).toBe('/homelab/training_log/range')
  })
})

describe('TrainingLogDay', () => {
  function mountDay(activities: TrainingLogActivity[], props: Record<string, unknown> = {}) {
    return mount(TrainingLogDay, {
      props: {
        date: '2026-10-12',
        activities,
        metric: 'time',
        units: 'metric',
        swim: false,
        rest: true,
        isToday: false,
        ...props,
      },
      global: withPlugins(),
    })
  }

  it('draws one circle per activity in its tag style, with the first name linked', () => {
    const wrapper = mountDay([
      makeLogActivity({ id: 1, tags: ['long_run'] }),
      makeLogActivity({ id: 2, name: 'Shakeout', tags: ['race'] }),
    ])
    const circles = wrapper.findAll('[data-style]')
    expect(circles.map((circle) => circle.attributes('data-style'))).toEqual(['long', 'race'])
    expect(circles[0]?.classes()).toContain('tl-family-run')
    const link = wrapper.findComponent(RouterLinkStub)
    expect(link.props('to')).toEqual({ name: 'activity', params: { id: 1 } })
    expect(link.text()).toBe('Morning Run +1')
    expect(wrapper.find('[data-testid="training-log-rest"]').exists()).toBe(false)
    expect(
      wrapper.get('[data-testid="training-log-day-trigger"]').attributes('aria-label'),
    ).toContain('Morning Run, 1h 0m')
  })

  it('shows Rest on an empty past day and marks today', () => {
    const wrapper = mountDay([], { isToday: true })
    expect(wrapper.get('[data-testid="training-log-rest"]').text()).toBe('Rest')
    expect(wrapper.find('[data-testid="training-log-today"]').exists()).toBe(true)
    expect(mountDay([], { rest: false }).find('[data-testid="training-log-rest"]').exists()).toBe(
      false,
    )
  })
})

describe('TrainingLogWeek', () => {
  function mountWeek(metric: 'time' | 'distance' | 'elevation' = 'time') {
    const byDate = groupByDate([
      makeLogActivity({ id: 1, localDate: '2026-10-12', movingTime: 4_800 }),
      makeLogActivity({
        id: 2,
        localDate: '2026-10-14',
        movingTime: 3_300,
        distance: 8_000,
        qualityTime: 1_800,
        qualityDistance: 5_000,
      }),
    ])
    return mount(TrainingLogWeek, {
      props: {
        week: weekOf('2026-10-12', 'monday'),
        byDate,
        activeDates: new Set(['2026-10-12', '2026-10-14', '2026-10-16']),
        metric,
        units: 'metric',
        swim: false,
        today: '2026-10-15',
        firstDate: '2020-01-01',
        loading: false,
      },
      global: withPlugins(),
    })
  }

  it('totals the week for the chosen metric and only rests past days', () => {
    const wrapper = mountWeek()
    expect(wrapper.text()).toContain('Oct 12 – 18')
    expect(wrapper.text()).toContain('Total Time')
    expect(wrapper.get('[data-testid="training-log-week-total"]').text()).toBe('2h 15m')
    // Tue 13 is the only past empty day; Thu 15 is today (no Rest), Fri-Sun are future.
    expect(wrapper.findAll('[data-testid="training-log-rest"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="training-log-today"]')).toHaveLength(1)
  })

  it('shows the quality total and its share of the week', async () => {
    const wrapper = mountWeek()
    expect(wrapper.text()).toContain('Total Quality')
    expect(wrapper.text()).toContain('Quality %')
    expect(wrapper.get('[data-testid="training-log-week-quality"]').text()).toBe('30m')
    // 30 of 135 minutes.
    expect(wrapper.get('[data-testid="training-log-week-quality-percent"]').text()).toBe('22%')
    expect(wrapper.get('[data-testid="training-log-week-quality-short"]').text()).toBe(
      '22% quality',
    )

    await wrapper.setProps({ metric: 'distance' })
    expect(wrapper.get('[data-testid="training-log-week-quality"]').text()).toBe('5.0 km')
    expect(wrapper.get('[data-testid="training-log-week-quality-percent"]').text()).toBe('28%')

    await wrapper.setProps({ metric: 'elevation' })
    expect(wrapper.find('[data-testid="training-log-week-quality"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Quality')
  })
})

describe('TrainingLogYear', () => {
  it('loads its weeks and applies the sport and tag filters', async () => {
    vi.mocked(apiFetch).mockResolvedValue([
      {
        id: 1,
        name: 'Long one',
        activity_type: 1,
        local_date: '2026-10-11',
        start_time: '2026-10-11T07:00:00',
        distance: 30_000,
        total_timer_time: 9_000,
        total_elapsed_time: 9_100,
        elevation_gain: 200,
        tags: ['long_run'],
      },
      {
        id: 3,
        name: 'Sub-T',
        activity_type: 1,
        local_date: '2026-10-07',
        start_time: '2026-10-07T07:00:00',
        distance: 10_000,
        total_timer_time: 3_600,
        total_elapsed_time: 3_700,
        elevation_gain: 40,
        tags: ['nsm_long'],
        quality_time: 1_800,
        quality_distance: 6_300,
      },
      {
        id: 2,
        name: 'Commute',
        activity_type: 4,
        local_date: '2026-10-08',
        start_time: '2026-10-08T08:00:00',
        distance: 12_000,
        total_timer_time: 1_800,
        total_elapsed_time: 1_900,
        elevation_gain: 10,
        tags: [],
      },
    ])
    const weeks = buildTrainingLogYears('2026-10-05', '2026-10-15', 'monday')[0]?.weeks ?? []
    const props = {
      year: 2026,
      weeks,
      sport: [] as SportFilter,
      tag: [] as TagFilter,
      metric: 'distance' as const,
      units: 'metric' as const,
      swim: false,
      today: '2026-10-15',
      firstDate: '2026-10-05',
    }
    const wrapper = mount(TrainingLogYear, { props, global: withPlugins() })
    await flushPromises()

    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe(
      '/homelab/training_log?start_date=2026-10-05&end_date=2026-10-18',
    )
    expect(wrapper.findAll('[data-testid="training-log-week"]')).toHaveLength(2)
    expect(wrapper.get('[data-testid="training-log-year-total"]').text()).toContain('52.0 km')
    expect(wrapper.get('[data-testid="training-log-year-quality"]').text()).toBe('6.3 km (12%)')
    expect(wrapper.findAll('[data-style]')).toHaveLength(3)

    const restDays = () => wrapper.findAll('[data-testid="training-log-rest"]').length
    const restBefore = restDays()

    await wrapper.setProps({ sport: ['ride'] })
    expect(wrapper.findAll('[data-style]')).toHaveLength(1)
    expect(wrapper.get('[data-testid="training-log-year-quality"]').text()).toBe('0.0 km (0%)')
    // Filtering out Sunday's run does not turn Sunday into a rest day.
    expect(restDays()).toBe(restBefore)
    expect(wrapper.get('[data-testid="training-log-year-total"]').text()).toContain('12.0 km')

    await wrapper.setProps({ sport: ['run', 'ride'] })
    expect(wrapper.findAll('[data-style]')).toHaveLength(3)

    await wrapper.setProps({ sport: [], tag: ['long_run'] })
    expect(
      wrapper.findAll('[data-style]').map((circle) => circle.attributes('data-style')),
    ).toEqual(['long'])

    // Every ticked tag must be on the activity.
    await wrapper.setProps({ tag: ['long_run', 'nsm_long'] })
    expect(wrapper.findAll('[data-style]')).toHaveLength(0)

    // Sport and tag filters both apply.
    await wrapper.setProps({ sport: ['ride'], tag: ['long_run'] })
    expect(wrapper.findAll('[data-style]')).toHaveLength(0)
  })
})

describe('TrainingLogLegend', () => {
  it('lists sport colours, then the tag styles', () => {
    const wrapper = mount(TrainingLogLegend, {
      props: { families: ['run'], styleFamily: 'run', showLongRun: true },
      global: withPlugins(),
    })
    expect(wrapper.findAll('li').map((item) => item.text())).toEqual([
      'Run',
      'Long Run',
      'Workout',
      'Race',
    ])
  })
})

describe('TrainingLogView', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  async function mountView(path: string) {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 15, 12))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/training-log', name: 'training-log', component: TrainingLogView },
        { path: '/activity/:id', name: 'activity', component: { template: '<div />' } },
      ],
    })
    await router.push(path)
    await router.isReady()
    const wrapper = mount(TrainingLogView, {
      attachTo: document.body,
      global: { ...withPlugins(), plugins: [...withPlugins().plugins, router] as never },
    })
    await flushPromises()
    return { wrapper, router }
  }

  /** Opens a filter pulldown; its menu is portalled to the document body. */
  async function openMenu(wrapper: Awaited<ReturnType<typeof mountView>>['wrapper'], id: string) {
    await wrapper.get(`${id} button`).trigger('keydown', { key: 'Enter' })
    await flushPromises()
    return [...document.body.querySelectorAll<HTMLElement>('[role="menuitemcheckbox"]')]
  }

  it('shows every year since the first activity, with filters from the URL', async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: string) =>
      url.endsWith('/range') ? { first_date: '2025-03-04', last_date: '2026-10-14' } : [],
    )

    const { wrapper, router } = await mountView(
      '/training-log?sport=ride&metric=elevation&tag=race,workout',
    )

    expect(
      wrapper.findAll('section[data-tl-year]').map((s) => s.attributes('data-tl-year')),
    ).toEqual(['2026', '2025'])
    expect(wrapper.get('#training-log-sport').text()).toBe('Ride')
    expect((wrapper.get('#training-log-metric').element as HTMLSelectElement).value).toBe(
      'elevation',
    )
    expect(wrapper.get('#training-log-tag').text()).toBe('Race, Workout')
    expect(wrapper.text()).toContain('Total Elevation')

    await wrapper.get('#training-log-metric').setValue('time')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ sport: 'ride', tag: 'race,workout' })
    wrapper.unmount()
  })

  it('ticks several sports and tags, keeping the menu open', async () => {
    vi.mocked(apiFetch).mockImplementation(async (url: string) =>
      url.endsWith('/range') ? { first_date: '2026-03-04', last_date: '2026-10-14' } : [],
    )

    const { wrapper, router } = await mountView('/training-log')
    expect(wrapper.get('#training-log-sport').text()).toBe('All sports')

    let items = await openMenu(wrapper, '#training-log-sport')
    expect(items.map((item) => item.dataset.option)).toEqual(['all', 'run', 'ride', 'type-14'])
    expect(items[0]?.getAttribute('aria-checked')).toBe('true')

    // Ticked in any order, kept in option order.
    items.find((item) => item.dataset.option === 'type-14')?.click()
    await flushPromises()
    items = [...document.body.querySelectorAll<HTMLElement>('[role="menuitemcheckbox"]')]
    expect(items).toHaveLength(4)
    items.find((item) => item.dataset.option === 'run')?.click()
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ sport: 'run,type-14' })
    items = [...document.body.querySelectorAll<HTMLElement>('[role="menuitemcheckbox"]')]
    expect(items.map((item) => item.getAttribute('aria-checked'))).toEqual([
      'false',
      'true',
      'false',
      'true',
    ])

    items.find((item) => item.dataset.option === 'ride')?.click()
    await flushPromises()
    expect(wrapper.get('#training-log-sport').text()).toBe('3 sports')

    // "All sports" clears the ticks.
    items[0]?.click()
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
    expect(wrapper.get('#training-log-sport').text()).toBe('All sports')
    wrapper.unmount()
    await flushPromises()

    const view = await mountView('/training-log')
    items = await openMenu(view.wrapper, '#training-log-tag')
    items.find((item) => item.dataset.option === 'workout')?.click()
    await flushPromises()
    items.find((item) => item.dataset.option === 'long_run')?.click()
    await flushPromises()
    expect(view.router.currentRoute.value.query).toEqual({ tag: 'workout,long_run' })
    expect(view.wrapper.get('#training-log-tag').text()).toBe('Workout, Long Run')
    view.wrapper.unmount()
  })

  it('offers sport options from the user types and an empty state without activities', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ first_date: null, last_date: null })

    const { wrapper } = await mountView('/training-log')

    expect(wrapper.text()).toContain('No activities yet')
    wrapper.unmount()
  })
})
