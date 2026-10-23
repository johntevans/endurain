<script setup lang="ts">
// Homelab fork: one night's HRV in the list.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { SleepHrvEntry } from '@/features/sleepHrv/types'

import { formatHealthEntryDate } from '@/features/health/utils/healthFormat'
import { formatHrv, formatHrvRange, hrvStatus } from '@/features/sleepHrv/utils/sleepHrv'

const props = defineProps<{
  /** The night to render. */
  entry: SleepHrvEntry
}>()

const { t, locale } = useI18n()

const dateLabel = computed(() => formatHealthEntryDate(props.entry.date, locale.value))
const status = computed(() => hrvStatus(props.entry))
const detail = computed(() => {
  const parts: string[] = []
  if (props.entry.avg7dMs !== null) {
    parts.push(t('sleepHrv.list.average', { value: formatHrv(props.entry.avg7dMs) }))
  }
  const range = formatHrvRange(props.entry.rangeLowMs, props.entry.rangeHighMs)
  if (range) parts.push(t('sleepHrv.list.range', { value: range }))
  return parts.join(' · ')
})
</script>

<template>
  <div class="px-4 py-3">
    <div class="flex items-center justify-between gap-3">
      <p class="text-item-title">{{ formatHrv(entry.hrvMs) }}</p>
      <span
        v-if="status && status !== 'within'"
        class="rounded-full border border-border px-2 py-0.5 text-hint"
      >
        {{ t(`sleepHrv.status.${status}`) }}
      </span>
    </div>
    <p class="text-hint">
      {{ dateLabel }}<template v-if="detail"> · {{ detail }}</template>
    </p>
  </div>
</template>
