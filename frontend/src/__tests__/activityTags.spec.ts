// Homelab fork: activity tags (Race, Workout, Long Run).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'

import type { ActivityDto } from '@/features/activities/types'
import type { ActivityTagKey } from '@/features/activityTags/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import ActivityEditDialog from '@/features/activities/components/ActivityEditDialog.vue'
import ActivityListItem from '@/features/activities/components/ActivityListItem.vue'
import { fetchUserActivitiesPage } from '@/features/activities/services/activities'
import { ACTIVITY_METRIC_COLUMNS } from '@/features/activities/utils/activityListColumns'
import ActivityTagBadges from '@/features/activityTags/components/ActivityTagBadges.vue'
import ActivityTagCheckboxGroup from '@/features/activityTags/components/ActivityTagCheckboxGroup.vue'
import {
  fetchActivityTags,
  MAX_ACTIVITY_IDS_PER_REQUEST,
  setActivityTags,
} from '@/features/activityTags/services/activityTags'
import {
  formatActivityTagsQuery,
  parseActivityTagsQuery,
  sameActivityTags,
  sortActivityTags,
} from '@/features/activityTags/utils/activityTags'
import { useAuthStore } from '@/features/auth/stores/auth'

import { makeActivity } from './fixtures/activity'

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

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('activity tag utils', () => {
  it('sorts into display order, dropping duplicates and unknown keys', () => {
    expect(sortActivityTags(['long_run', 'bogus', 'race', 'long_run'])).toEqual([
      'race',
      'long_run',
    ])
  })

  it('round-trips the URL query param and ignores junk', () => {
    expect(parseActivityTagsQuery('long_run,race,nope')).toEqual(['race', 'long_run'])
    expect(parseActivityTagsQuery(['race'])).toEqual([])
    expect(parseActivityTagsQuery('')).toEqual([])
    expect(formatActivityTagsQuery(['workout', 'race'])).toBe('race,workout')
  })

  it('compares tag sets regardless of order', () => {
    expect(sameActivityTags(['workout', 'race'], ['race', 'workout'])).toBe(true)
    expect(sameActivityTags(['race'], ['race', 'workout'])).toBe(false)
  })
})

describe('fetchActivityTags', () => {
  it('batches the ids into one authenticated request and maps the result', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([
      { activity_id: 3, tags: ['long_run', 'race'] },
      { activity_id: 5, tags: [] },
    ])

    const result = await fetchActivityTags([3, 5, 3], { authenticated: true })

    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch).toHaveBeenCalledWith(
      '/homelab/activity_tags?activity_id=3&activity_id=5',
      expect.objectContaining({ auth: true }),
    )
    expect(result.get(3)).toEqual(['race', 'long_run'])
    expect(result.get(5)).toEqual([])
  })

  it('uses the public endpoint for unauthenticated viewers', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)

    const result = await fetchActivityTags([9], { authenticated: false })

    expect(apiFetch).toHaveBeenCalledWith(
      '/public/homelab/activity_tags?activity_id=9',
      expect.objectContaining({ auth: false }),
    )
    expect(result.size).toBe(0)
  })

  it('makes no request for no ids and splits oversized batches', async () => {
    expect((await fetchActivityTags([], { authenticated: true })).size).toBe(0)
    expect(apiFetch).not.toHaveBeenCalled()

    vi.mocked(apiFetch).mockResolvedValue([])
    const ids = Array.from({ length: MAX_ACTIVITY_IDS_PER_REQUEST + 1 }, (_, i) => i + 1)
    await fetchActivityTags(ids, { authenticated: true })
    expect(apiFetch).toHaveBeenCalledTimes(2)
  })
})

describe('setActivityTags', () => {
  it('PUTs the complete tag set in display order', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ activity_id: 4, tags: ['race', 'workout'] })

    const tags = await setActivityTags(4, ['workout', 'race'])

    expect(apiFetch).toHaveBeenCalledWith('/homelab/activity_tags/4', {
      method: 'PUT',
      body: JSON.stringify({ tags: ['race', 'workout'] }),
    })
    expect(tags).toEqual(['race', 'workout'])
  })
})

describe('fetchUserActivitiesPage tag filter', () => {
  it('sends every selected tag to both the list and the count', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([]).mockResolvedValueOnce(0)

    await fetchUserActivitiesPage({
      userId: 1,
      page: 1,
      numRecords: 25,
      filters: {
        type: null,
        startDate: null,
        endDate: null,
        nameSearch: null,
        tags: ['race', 'long_run'],
      },
      sortBy: 'start_time',
      sortOrder: 'desc',
    })

    expect(apiFetch).toHaveBeenNthCalledWith(
      1,
      '/activities/user/1/page_number/1/num_records/25?tag=race&tag=long_run&sort_by=start_time&sort_order=desc',
      expect.anything(),
    )
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/activities/number?tag=race&tag=long_run',
      expect.anything(),
    )
  })
})

describe('ActivityTagBadges', () => {
  it('shows the tags in display order with their labels', () => {
    const wrapper = mount(ActivityTagBadges, {
      props: { tags: ['long_run', 'race'] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('[data-tag]').map((badge) => badge.text())).toEqual(['Race', 'Long Run'])
  })

  it('renders nothing without tags', () => {
    const wrapper = mount(ActivityTagBadges, {
      props: { tags: [] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('[data-testid="activity-tag-badges"]').exists()).toBe(false)
  })
})

describe('ActivityTagCheckboxGroup', () => {
  it('lists Race, Workout, Long Run and emits the selection in display order', async () => {
    const wrapper = mount(ActivityTagCheckboxGroup, {
      props: { legend: 'Activity Tags', modelValue: ['long_run'] as ActivityTagKey[] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('legend').text()).toBe('Activity Tags')
    expect(wrapper.findAll('label').map((label) => label.text())).toEqual([
      'Race',
      'Workout',
      'Long Run',
    ])
    expect((wrapper.find('input[data-tag="long_run"]').element as HTMLInputElement).checked).toBe(
      true,
    )

    await wrapper.find('input[data-tag="race"]').setValue(true)
    expect(wrapper.emitted('update:modelValue')?.slice(-1)[0]).toEqual([['race', 'long_run']])
  })
})

describe('ActivityListItem tags', () => {
  function mountItem(tags?: ActivityTagKey[]) {
    return mount(ActivityListItem, {
      props: { activity: makeActivity(), units: 'metric', columns: ACTIVITY_METRIC_COLUMNS, tags },
      global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
    })
  }

  it('shows tag badges on the row when the activity has tags', () => {
    expect(mountItem(['workout']).find('[data-tag="workout"]').text()).toBe('Workout')
  })

  it('shows no badges without tags', () => {
    expect(mountItem().find('[data-testid="activity-tag-badges"]').exists()).toBe(false)
  })
})

describe('ActivityEditDialog tags', () => {
  const passthrough = { template: '<div><slot /></div>' }
  const activityDto: ActivityDto = {
    id: 1,
    user_id: 7,
    name: 'Morning run',
    activity_type: 1,
    distance: 10000,
    is_hidden: false,
    visibility: 0,
    total_elapsed_time: 3600,
    total_timer_time: 3500,
  }

  function mountDialog() {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().isAuthenticated = true
    return mount(ActivityEditDialog, {
      props: { activity: makeActivity({ id: 1 }), open: true },
      global: {
        plugins: [
          i18n,
          pinia,
          [
            VueQueryPlugin,
            { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          ],
        ],
        stubs: {
          Dialog: passthrough,
          DialogContent: passthrough,
          DialogHeader: passthrough,
          DialogTitle: passthrough,
          DialogDescription: passthrough,
          DialogFooter: passthrough,
          MarkdownEditor: true,
        },
      },
    })
  }

  /** Routes the mocked network by path: tag GET/PUT and the activity edit. */
  function mockApi(currentTags: ActivityTagKey[]) {
    vi.mocked(apiFetch).mockImplementation(async (path: string, init?: { body?: unknown }) => {
      if (path.startsWith('/homelab/activity_tags?')) {
        return [{ activity_id: 1, tags: currentTags }]
      }
      if (path === '/homelab/activity_tags/1') {
        return { activity_id: 1, ...JSON.parse(String(init?.body)) }
      }
      return activityDto
    })
  }

  function tagPutCalls() {
    return vi.mocked(apiFetch).mock.calls.filter(([path]) => path === '/homelab/activity_tags/1')
  }

  it('shows the "Activity Tags" group seeded with the current tags and saves a change', async () => {
    mockApi(['workout'])
    const wrapper = mountDialog()
    await flushPromises()

    expect(wrapper.text()).toContain('Activity Tags')
    const workout = wrapper.find('input[data-tag="workout"]').element as HTMLInputElement
    expect(workout.checked).toBe(true)

    await wrapper.find('input[data-tag="race"]').setValue(true)
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(tagPutCalls()).toEqual([
      [
        '/homelab/activity_tags/1',
        { method: 'PUT', body: JSON.stringify({ tags: ['race', 'workout'] }) },
      ],
    ])
    expect(wrapper.emitted('update:open')?.slice(-1)[0]).toEqual([false])
  })

  it('does not touch tags when they were not changed', async () => {
    mockApi(['race'])
    const wrapper = mountDialog()
    await flushPromises()

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(vi.mocked(apiFetch).mock.calls.some(([path]) => path === '/activities/edit')).toBe(true)
    expect(tagPutCalls()).toHaveLength(0)
  })
})
