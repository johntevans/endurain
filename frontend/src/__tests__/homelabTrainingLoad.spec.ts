// Homelab fork: the activity page's training-load tile.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import ActivityLoadPill from '@/features/trainingLoad/components/ActivityLoadPill.vue'
import { mapActivityLoad } from '@/features/trainingLoad/services/trainingLoad'

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
