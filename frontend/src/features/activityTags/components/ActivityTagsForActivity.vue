<script setup lang="ts">
import { computed } from 'vue'

import ActivityTagBadges from '@/features/activityTags/components/ActivityTagBadges.vue'
import { useActivityTagsQuery } from '@/features/activityTags/composables/useActivityTags'

/**
 * Homelab fork: fetches and shows one activity's tag badges (the detail
 * page). Uses the same batch endpoint as the list, with a single id; the
 * backend applies the activity's own visibility rules.
 */
const props = defineProps<{
  /** The activity whose tags to show. */
  activityId: number
}>()

const tagsQuery = useActivityTagsQuery(() => [props.activityId])
const tags = computed(() => tagsQuery.data.value?.get(props.activityId) ?? [])
</script>

<template>
  <ActivityTagBadges :tags="tags" />
</template>
