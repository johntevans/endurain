<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Activity } from '@/features/activities/types'

import { MetricPill } from '@/components/ui/metric-pill'
import { useActivityLoad } from '@/features/trainingLoad/composables/useTrainingLoad'

/**
 * Homelab fork: the activity's Intervals.icu-style training load, as a tile
 * of the metrics grid. Owner only, and only once it has a load (thresholds
 * set, from the loads' start date on); otherwise it renders nothing.
 */
const props = defineProps<{
  activity: Activity
}>()

const { t } = useI18n()
const query = useActivityLoad(() => props.activity)

const tile = computed(() => {
  const data = query.data.value
  if (!data || data.load === null) {
    return null
  }
  // Like Intervals' "Load 0 (11)": a strength session's HR load is shown, not counted.
  const unit =
    data.source === 'pace' || data.source === 'hr'
      ? t(`trainingLoad.source.${data.source}`)
      : data.hrLoad !== null
        ? t('trainingLoad.hrLoad', { value: data.hrLoad })
        : ''
  return { value: data.load, unit }
})
</script>

<template>
  <MetricPill
    v-if="tile"
    :label="t('trainingLoad.label')"
    :value="tile.value"
    :unit="tile.unit"
    data-testid="activity-training-load"
  />
</template>
