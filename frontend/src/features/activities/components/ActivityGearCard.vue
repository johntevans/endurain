<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { Pencil, Plus, Trash2 } from '@lucide/vue'

import type { Activity } from '@/features/activities/types'
import type { Units } from '@/features/activities/utils/format'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useToasts } from '@/composables/useToasts'
import {
  useActivityGearOptionsQuery,
  useSetActivityGearMutation,
} from '@/features/activities/composables/useActivityDetail'
import { activityTypeToGearType } from '@/features/activities/utils/activityType'
import { useGearQuery } from '@/features/gears/composables/useGears'
import { metersToDisplayDistance } from '@/features/gears/utils/format'

const props = defineProps<{
  /** The activity whose gear association is shown and (owner-only) edited. */
  activity: Activity
  /** The viewer's measurement system, for the gear's total distance. */
  units: Units
}>()

const { t } = useI18n()
const toasts = useToasts()

/** The gear type compatible with this activity, or `null` when none applies. */
const gearType = computed(() => activityTypeToGearType(props.activity.activityType))
const gearId = computed(() => props.activity.gearId)

// The currently associated gear, for its nickname + deep link. Gated by
// useGearQuery on a valid id, so it stays idle when no gear is set.
const { data: currentGear } = useGearQuery(gearId)
// The gear's lifetime distance (initial offset plus every assigned activity,
// this one included), e.g. "412.3 mi"; `null` until the detail has loaded.
const currentGearDistance = computed(() => {
  if (!currentGear.value) {
    return null
  }
  const value = metersToDisplayDistance(currentGear.value.totalDistance, props.units)
  const unit = props.units === 'imperial' ? t('gears.unitMi') : t('gears.unitKm')
  return `${value} ${unit}`
})
const optionsQuery = useActivityGearOptionsQuery(gearType)
// Only active (non-retired) gear can be newly assigned to an activity.
const options = computed(() => (optionsQuery.data.value ?? []).filter((gear) => gear.active))

const setGearMutation = useSetActivityGearMutation()
const isSaving = computed(() => setGearMutation.isPending.value)

const isPickerOpen = ref(false)
const isRemoveOpen = ref(false)
const selectedGearId = ref<number | null>(props.activity.gearId)

// Whether the card has anything to show: the activity supports gear, or one is
// already set (e.g. after the activity type changed). Otherwise it is hidden.
const showCard = computed(() => gearType.value !== null || gearId.value !== null)
const canSubmit = computed(() => selectedGearId.value !== null)

// Re-seed the picker with the activity's current gear each time it opens,
// falling back to the placeholder when that gear is retired (not listed).
watch(isPickerOpen, (open) => {
  if (open) {
    const currentId = props.activity.gearId
    selectedGearId.value = options.value.some((gear) => gear.id === currentId) ? currentId : null
  }
})

/** Assigns or changes the activity's gear, then closes the picker. */
async function submitGear(): Promise<void> {
  if (selectedGearId.value === null) {
    return
  }
  try {
    await setGearMutation.mutateAsync({ activity: props.activity, gearId: selectedGearId.value })
    isPickerOpen.value = false
    toasts.success(t('activities.gear.saveSuccess'))
  } catch {
    toasts.error(t('activities.gear.saveError'))
  }
}

/** Removes the gear association from the activity, then closes the dialog. */
async function removeGear(): Promise<void> {
  try {
    await setGearMutation.mutateAsync({ activity: props.activity, gearId: null })
    isRemoveOpen.value = false
    toasts.success(t('activities.gear.removeSuccess'))
  } catch {
    toasts.error(t('activities.gear.removeError'))
  }
}
</script>

<template>
  <Card v-if="showCard" class="flex flex-col gap-3">
    <div class="flex items-center justify-between gap-3">
      <h2 class="text-card-heading">{{ t('activities.gear.title') }}</h2>
      <div v-if="activity.gearId" class="flex items-center gap-1">
        <Button
          v-if="gearType !== null"
          variant="ghost"
          size="sm"
          :aria-label="t('activities.gear.change')"
          @click="isPickerOpen = true"
        >
          <Pencil class="size-4" />
        </Button>
        <Button
          variant="ghostDestructive"
          size="sm"
          :aria-label="t('activities.gear.remove')"
          @click="isRemoveOpen = true"
        >
          <Trash2 class="size-4" />
        </Button>
      </div>
    </div>

    <RouterLink
      v-if="activity.gearId"
      :to="{ name: 'gear', params: { id: String(activity.gearId) } }"
      class="self-start text-body text-brand hover:underline"
    >
      {{ currentGear?.nickname ?? t('activities.gear.loading') }}
      <span v-if="currentGearDistance" class="text-hint">({{ currentGearDistance }})</span>
    </RouterLink>

    <div v-else class="flex flex-col items-start gap-3">
      <p class="text-hint">{{ t('activities.gear.notSet') }}</p>
      <Button v-if="gearType !== null" variant="outline" size="sm" @click="isPickerOpen = true">
        <Plus class="size-4" />
        {{ t('activities.gear.add') }}
      </Button>
    </div>

    <!-- Add / change gear -->
    <FormDialog
      v-model:open="isPickerOpen"
      :title="activity.gearId ? t('activities.gear.changeTitle') : t('activities.gear.addTitle')"
      :submit-label="t('activities.gear.save')"
      :cancel-label="t('activities.gear.cancel')"
      :close-label="t('activities.gear.close')"
      :submitting="isSaving"
      :can-submit="canSubmit"
      @submit="submitGear"
    >
      <FormField :label="t('activities.gear.selectLabel')">
        <template #default="{ fieldId }">
          <select
            :id="fieldId"
            v-model="selectedGearId"
            :class="inputFieldClass"
            :disabled="isSaving"
          >
            <option :value="null" disabled>{{ t('activities.gear.selectPlaceholder') }}</option>
            <option v-for="gear in options" :key="gear.id" :value="gear.id">
              {{ gear.nickname }}
            </option>
          </select>
        </template>
      </FormField>
      <p v-if="options.length === 0" class="text-hint">{{ t('activities.gear.noGears') }}</p>
    </FormDialog>

    <!-- Remove gear -->
    <ConfirmDialog
      v-model:open="isRemoveOpen"
      :title="t('activities.gear.removeTitle')"
      :description="t('activities.gear.removeBody')"
      :confirm-label="t('activities.gear.remove')"
      :cancel-label="t('activities.gear.cancel')"
      :close-label="t('activities.gear.close')"
      :pending="isSaving"
      @confirm="removeGear"
    />
  </Card>
</template>
