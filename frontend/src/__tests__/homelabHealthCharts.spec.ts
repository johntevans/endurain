// Homelab fork: health charts plot the whole window, not the list's page.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, nextTick } from 'vue'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import { useAuthStore } from '@/features/auth/stores/auth'
import HealthSleepChart from '@/features/health/components/HealthSleepChart.vue'
import HealthWeightChart from '@/features/health/components/HealthWeightChart.vue'
import { fetchWeightEntries } from '@/features/health/services/health'
import HealthSleepView from '@/features/health/views/HealthSleepView.vue'
import HealthWeightView from '@/features/health/views/HealthWeightView.vue'
import { healthChartKind } from '@/features/healthCharts/utils/chartKind'

vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: { value: { units: 'metric' } } }),
}))
vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))
vi.mock('@/composables/useChartProvider', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/composables/useChartProvider')>()),
  useChartProvider: () => ({ isAvailable: true }),
}))

const PAGE_SIZE = 25
const WINDOW_RECORDS = 60

/** A window of records, newest first. */
const dtos = Array.from({ length: WINDOW_RECORDS }, (_, index) => ({
  id: index + 1,
  user_id: 1,
  date: `2026-08-${String(60 - index).padStart(2, '0')}`,
  weight: 80,
  total_sleep_seconds: 25200,
}))

/** Answers like the backend: a page when asked for one, otherwise everything. */
function fakeApi(path: string): Promise<unknown> {
  if (path === '/health/targets') return Promise.resolve({ id: 1, user_id: 1 })
  if (!path.startsWith('/health/')) return Promise.resolve({ num_records_per_page: PAGE_SIZE })
  const query = new URLSearchParams(path.split('?')[1])
  const pageNumber = query.get('page_number')
  if (pageNumber === null) return Promise.resolve({ total: dtos.length, records: dtos })
  const start = (Number(pageNumber) - 1) * Number(query.get('num_records'))
  return Promise.resolve({
    total: dtos.length,
    records: dtos.slice(start, start + Number(query.get('num_records'))),
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().isAuthenticated = true
  vi.mocked(apiFetch).mockReset()
  vi.mocked(apiFetch).mockImplementation(fakeApi as typeof apiFetch)
})

describe('fetching a whole window', () => {
  it('omits pagination when no page is given', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ total: 0, records: [] })
    await fetchWeightEntries({ interval: 'all_time' })
    expect(apiFetch).toHaveBeenCalledWith('/health/weight?interval=all_time', { signal: undefined })
  })

  it('still sends pagination for a list page', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ total: 0, records: [] })
    await fetchWeightEntries({ page: 2, numRecords: 25, interval: 'last_year' })
    expect(apiFetch).toHaveBeenCalledWith(
      '/health/weight?page_number=2&num_records=25&interval=last_year',
      { signal: undefined },
    )
  })
})

describe('healthChartKind', () => {
  it('draws bars up to the limit and a line past it', () => {
    expect(healthChartKind(100)).toBe('bar')
    expect(healthChartKind(101)).toBe('line')
  })
})

describe.each([
  ['weight', HealthWeightView, HealthWeightChart],
  ['sleep', HealthSleepView, HealthSleepChart],
])('the %s zone', (_name, View, Chart) => {
  const ChartStub = defineComponent({ props: ['entries'], template: '<div data-chart />' })
  const ListItemStub = { template: '<div data-row />' }

  async function mountView() {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(View, {
      global: {
        plugins: [i18n, [VueQueryPlugin, { queryClient }]],
        stubs: {
          [Chart.__name ?? '']: ChartStub,
          HealthWeightListItem: ListItemStub,
          HealthSleepListItem: ListItemStub,
          HealthWeightFormDialog: true,
          HealthWeightTargetDialog: true,
          HealthSleepFormDialog: true,
          HealthSleepTargetDialog: true,
          ConfirmDialog: true,
        },
      },
    })
    await flushPromises()
    return wrapper
  }

  it('charts the whole window while the list shows one page', async () => {
    const wrapper = await mountView()
    expect(wrapper.findAll('[data-row]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.findComponent(ChartStub).props('entries')).toHaveLength(WINDOW_RECORDS)
  })

  it('keeps the chart whole when paging the list', async () => {
    const wrapper = await mountView()
    const list = wrapper.findComponent({ name: 'ListPanel' })
    list.vm.$emit('update:page', 3)
    await nextTick()
    await flushPromises()
    expect(wrapper.findAll('[data-row]')).toHaveLength(WINDOW_RECORDS - 2 * PAGE_SIZE)
    expect(wrapper.findComponent(ChartStub).props('entries')).toHaveLength(WINDOW_RECORDS)
  })
})
