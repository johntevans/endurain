<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ActivityTagKey } from '@/features/activityTags/types'

import { Badge } from '@/components/ui/badge'
import { ACTIVITY_TAGS } from '@/features/activityTags/utils/activityTags'

/**
 * Homelab fork: an activity's tags as small badges, in display order. Renders
 * nothing when there are no tags.
 */
const props = defineProps<{
  /** The activity's tags (any order). */
  tags: readonly ActivityTagKey[]
}>()

const { t } = useI18n()

const shown = computed(() => ACTIVITY_TAGS.filter((tag) => props.tags.includes(tag.key)))
</script>

<template>
  <span
    v-if="shown.length > 0"
    class="inline-flex flex-wrap items-center gap-1"
    data-testid="activity-tag-badges"
  >
    <Badge v-for="tag in shown" :key="tag.key" :variant="tag.variant" :data-tag="tag.key">
      {{ t(tag.labelKey) }}
    </Badge>
  </span>
</template>
