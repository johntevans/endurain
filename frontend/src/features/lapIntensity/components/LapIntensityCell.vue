<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RotateCcw } from '@lucide/vue'

import type { LapIntensity, LapIntensityKey } from '@/features/lapIntensity/types'

import { Select } from '@/components/ui/select'
import { LAP_INTENSITY_KEYS } from '@/features/lapIntensity/types'

/**
 * Homelab fork: the owner's intensity picker for one lap of the laps table.
 * Marks a lap whose file had no intensity (`default`) and one the owner
 * changed (`edited`, with a button back to the recorded value).
 */
const props = defineProps<{
  entry: LapIntensity
  saving: boolean
}>()

const emit = defineEmits<{
  change: [intensity: LapIntensityKey | null]
}>()

const { t, te } = useI18n()

function label(value: string): string {
  const key = `lapIntensity.values.${value}`
  return te(key) ? t(key) : value
}

// A recorded value outside FIT's list still shows as itself.
const options = computed<string[]>(() =>
  (LAP_INTENSITY_KEYS as readonly string[]).includes(props.entry.intensity)
    ? [...LAP_INTENSITY_KEYS]
    : [props.entry.intensity, ...LAP_INTENSITY_KEYS],
)

const value = computed<string>({
  get: () => props.entry.intensity,
  set: (picked) => emit('change', picked as LapIntensityKey),
})

const hint = computed(() => {
  switch (props.entry.source) {
    case 'default':
      return t('lapIntensity.hint.default')
    case 'override':
      return props.entry.recorded
        ? t('lapIntensity.hint.override', { recorded: label(props.entry.recorded) })
        : t('lapIntensity.hint.overrideDefault')
    default:
      return t('lapIntensity.hint.recorded')
  }
})
</script>

<template>
  <span class="flex items-center gap-1.5" :title="hint">
    <Select
      v-model="value"
      class="h-7 w-auto rounded-md px-1.5 py-0 text-meta"
      :aria-label="t('lapIntensity.label')"
      :disabled="saving"
      data-testid="lap-intensity-select"
    >
      <option v-for="option in options" :key="option" :value="option">{{ label(option) }}</option>
    </Select>
    <span
      v-if="entry.source === 'default'"
      class="text-micro text-muted-foreground"
      data-testid="lap-intensity-default"
      >{{ t('lapIntensity.source.default') }}</span
    >
    <button
      v-else-if="entry.source === 'override'"
      type="button"
      class="flex items-center gap-1 text-micro text-brand hover:underline disabled:opacity-50"
      :aria-label="t('lapIntensity.reset')"
      :disabled="saving"
      data-testid="lap-intensity-reset"
      @click="emit('change', null)"
    >
      {{ t('lapIntensity.source.override') }}
      <RotateCcw class="size-3" aria-hidden="true" />
    </button>
  </span>
</template>
