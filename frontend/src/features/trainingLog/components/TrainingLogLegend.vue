<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { CircleStyle, SportFamily } from '@/features/trainingLog/types'

import { SPORT_FAMILY_LABEL_KEYS } from '@/features/trainingLog/utils/trainingLog'

/**
 * Homelab fork: what the circle colours mean. One swatch per sport shown,
 * then the tag styles drawn in the selected sport's colours.
 */
const props = defineProps<{
  /** Sports whose plain colour is listed. */
  families: readonly SportFamily[]
  /** The sport the tag swatches are drawn in. */
  styleFamily: SportFamily
  /** Whether to list the long-run style (only runs are long runs). */
  showLongRun: boolean
}>()

const { t } = useI18n()

const items = computed(() => {
  const list: Array<{ key: string; family: SportFamily; style: CircleStyle; label: string }> =
    props.families.map((family) => ({
      key: family,
      family,
      style: 'base',
      label: t(SPORT_FAMILY_LABEL_KEYS[family]),
    }))
  if (props.showLongRun) {
    list.push({
      key: 'long',
      family: 'run',
      style: 'long',
      label: t('activityTags.labels.longRun'),
    })
  }
  list.push(
    {
      key: 'workout',
      family: props.styleFamily,
      style: 'workout',
      label: t('activityTags.labels.workout'),
    },
    { key: 'race', family: props.styleFamily, style: 'race', label: t('activityTags.labels.race') },
  )
  return list
})
</script>

<template>
  <ul class="flex flex-wrap items-center gap-x-4 gap-y-1.5" :aria-label="t('trainingLog.legend')">
    <li
      v-for="item in items"
      :key="item.key"
      class="flex items-center gap-1.5 text-meta text-foreground"
    >
      <span
        class="tl-mark size-3"
        :class="[`tl-family-${item.family}`, `tl-style-${item.style}`]"
        aria-hidden="true"
      />
      {{ item.label }}
    </li>
  </ul>
</template>
