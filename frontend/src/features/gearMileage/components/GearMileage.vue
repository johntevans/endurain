<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Gear } from '@/features/gears/types'

import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useGearMileageQuery } from '@/features/gearMileage/composables/useGearMileage'
import { metersToDisplayDistance } from '@/features/gears/utils/format'
import { GEAR_TYPE } from '@/features/gears/utils/gearType'

/**
 * Homelab fork: a shoe's total distance on its gear list row, the same number
 * as its gear page, so worn-out shoes show without opening each one. Renders
 * nothing for other gear, or until the distance has loaded.
 */
const props = defineProps<{ gear: Gear }>()

const { t } = useI18n()
const { data: currentUser } = useCurrentUser()
const query = useGearMileageQuery()

const units = computed(() => currentUser.value?.units ?? 'metric')
const unit = computed(() => (units.value === 'imperial' ? t('gears.unitMi') : t('gears.unitKm')))
const distance = computed(() => {
  const meters = query.data.value?.[props.gear.id]
  return props.gear.gearType === GEAR_TYPE.SHOES && meters !== undefined
    ? metersToDisplayDistance(meters, units.value)
    : null
})
</script>

<template>
  <p
    v-if="distance !== null"
    class="whitespace-nowrap text-sm text-foreground tabular-nums"
    :title="t('gears.detail.totalDistance')"
    data-testid="gear-mileage"
  >
    <span class="font-medium">{{ distance }}</span> <span class="text-hint">{{ unit }}</span>
  </p>
</template>
