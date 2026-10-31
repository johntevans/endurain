// Homelab fork: a shoe's total distance on the gear list.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { Gear } from '@/features/gears/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import GearMileage from '@/features/gearMileage/components/GearMileage.vue'
import { fetchGearMileage } from '@/features/gearMileage/services/gearMileage'
import { GEAR_TYPE } from '@/features/gears/utils/gearType'

const viewer = vi.hoisted(() => ({ value: { units: 'imperial' } as { units: string } | null }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: viewer }),
}))
vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const shoe: Gear = {
  id: 5,
  userId: 1,
  gearType: GEAR_TYPE.SHOES,
  nickname: 'Saucony Ride 18',
  brand: null,
  model: null,
  active: true,
  createdAt: null,
  initialKms: null,
  purchaseValue: null,
  stravaGearId: null,
  garminConnectGearId: null,
}

function mountMileage(gears: Gear[]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return gears.map((gear) =>
    mount(GearMileage, {
      props: { gear },
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient }]] },
    }),
  )
}

beforeEach(() => {
  viewer.value = { units: 'imperial' }
  vi.mocked(apiFetch).mockReset()
  vi.mocked(apiFetch).mockResolvedValue([
    { gear_id: 5, total_distance: 804672 },
    { gear_id: 6, total_distance: 0 },
  ])
})

describe('fetchGearMileage', () => {
  it('keys the distances by gear id', async () => {
    await expect(fetchGearMileage()).resolves.toEqual({ 5: 804672, 6: 0 })
    expect(apiFetch).toHaveBeenCalledWith('/homelab/gear_mileage', { signal: undefined })
  })
})

describe('GearMileage', () => {
  it("shows a shoe's distance in miles for an imperial user", async () => {
    const [wrapper] = mountMileage([shoe])
    await flushPromises()
    expect(wrapper?.get('[data-testid="gear-mileage"]').text()).toBe('500 mi')
  })

  it("shows a shoe's distance in kilometres for a metric user", async () => {
    viewer.value = { units: 'metric' }
    const [wrapper] = mountMileage([shoe])
    await flushPromises()
    expect(wrapper?.get('[data-testid="gear-mileage"]').text()).toBe('804.7 km')
  })

  it('shows zero for a new shoe', async () => {
    const [wrapper] = mountMileage([{ ...shoe, id: 6 }])
    await flushPromises()
    expect(wrapper?.get('[data-testid="gear-mileage"]').text()).toBe('0 mi')
  })

  it('renders nothing for gear other than shoes', async () => {
    const [wrapper] = mountMileage([{ ...shoe, gearType: GEAR_TYPE.BICYCLE }])
    await flushPromises()
    expect(wrapper?.find('[data-testid="gear-mileage"]').exists()).toBe(false)
  })

  it('renders nothing when the distance is unavailable', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('down'))
    const [wrapper] = mountMileage([shoe])
    await flushPromises()
    expect(wrapper?.find('[data-testid="gear-mileage"]').exists()).toBe(false)
  })

  it('sends one request for a whole list of shoes', async () => {
    mountMileage([shoe, { ...shoe, id: 6 }])
    await flushPromises()
    expect(apiFetch).toHaveBeenCalledTimes(1)
  })
})
