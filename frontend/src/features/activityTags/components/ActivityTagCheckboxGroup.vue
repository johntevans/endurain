<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { ActivityTagKey } from '@/features/activityTags/types'

import { ACTIVITY_TAGS, sortActivityTags } from '@/features/activityTags/utils/activityTags'

/**
 * Homelab fork: a checkbox group over the fixed activity tags, used both to
 * edit an activity's tags and to filter the activities list.
 */
const props = defineProps<{
  /** The group's visible title. */
  legend: string
  /** Disables every checkbox. */
  disabled?: boolean
}>()

/** The checked tags, always emitted in display order. */
const model = defineModel<ActivityTagKey[]>({ required: true })

const { t } = useI18n()

/** Adds or removes one tag from the selection. */
function toggle(key: ActivityTagKey, checked: boolean): void {
  const next = checked ? [...model.value, key] : model.value.filter((tag) => tag !== key)
  model.value = sortActivityTags(next)
}
</script>

<template>
  <fieldset class="flex flex-col gap-1.5" :disabled="props.disabled">
    <legend class="mb-1.5 text-meta font-medium text-foreground">{{ legend }}</legend>
    <div class="flex flex-wrap gap-x-5 gap-y-1">
      <label
        v-for="tag in ACTIVITY_TAGS"
        :key="tag.key"
        :class="[
          'inline-flex items-center gap-2 py-1 text-body',
          props.disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
        ]"
      >
        <input
          type="checkbox"
          class="size-4 shrink-0 rounded accent-brand focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
          :value="tag.key"
          :checked="model.includes(tag.key)"
          :data-tag="tag.key"
          @change="toggle(tag.key, ($event.target as HTMLInputElement).checked)"
        />
        {{ t(tag.labelKey) }}
      </label>
    </div>
  </fieldset>
</template>
