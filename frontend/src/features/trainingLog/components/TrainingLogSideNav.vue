<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { TrainingLogWeek } from '@/features/trainingLog/types'

import { cn } from '@/lib/utils'
import { useTrainingLogWindowQuery } from '@/features/trainingLog/composables/useTrainingLog'
import { formatClock, weeksWindow, yearMonths } from '@/features/trainingLog/utils/trainingLog'

/**
 * Homelab fork: the training log's year/month index. The year being viewed
 * opens to its months, each listing its races; everything jumps the log.
 */
const props = defineProps<{
  years: ReadonlyArray<{ year: number; weeks: readonly TrainingLogWeek[] }>
  activeYear: number | null
  /** `YYYY-MM` of the week at the top of the viewport. */
  activeMonth: string | null
}>()

const emit = defineEmits<{
  /** Jump to a year, a month (`YYYY-MM`) or the week holding a date. */
  jump: [target: { year: number; month?: string; date?: string }]
}>()

const { t, locale } = useI18n()

const active = computed(() => props.years.find((entry) => entry.year === props.activeYear) ?? null)

// Reads the open year's activities from the cache the log filled; it never
// fetches on its own (the year is on screen, so the log already has).
const activeQuery = useTrainingLogWindowQuery(
  () => (active.value ? weeksWindow(active.value.weeks) : null),
  false,
)

const months = computed(() => {
  if (!active.value) {
    return []
  }
  const races = (activeQuery.data.value ?? []).filter((activity) => activity.tags.includes('race'))
  const monthName = new Intl.DateTimeFormat(locale.value, { month: 'short', timeZone: 'UTC' })
  return yearMonths(active.value.weeks).map((month) => ({
    month,
    label: monthName.format(new Date(`${month}-01T00:00:00Z`)),
    races: races
      .filter((race) => race.localDate.startsWith(month))
      .sort((a, b) => b.startTime.localeCompare(a.startTime))
      .map((race) => ({
        id: race.id,
        date: race.localDate,
        label: `${race.name} (${formatClock(race.elapsedTime || race.movingTime)})`,
      })),
  }))
})
</script>

<template>
  <nav class="flex flex-col gap-1 text-sm" :aria-label="t('trainingLog.sideNav')">
    <template v-for="entry in years" :key="entry.year">
      <button
        type="button"
        :class="
          cn(
            'w-fit rounded-sm px-2 py-1 text-left text-muted-foreground hover:text-foreground',
            entry.year === activeYear && 'font-semibold text-foreground',
          )
        "
        :aria-current="entry.year === activeYear ? 'true' : undefined"
        @click="emit('jump', { year: entry.year })"
      >
        {{ entry.year }}
      </button>
      <ul v-if="entry.year === activeYear" class="mb-2 flex flex-col">
        <li v-for="item in months" :key="item.month" class="flex flex-col">
          <button
            type="button"
            :class="
              cn(
                'border-l-2 border-transparent py-1 pl-4 text-left text-[15px] text-foreground/80 hover:text-foreground',
                item.month === activeMonth && 'border-foreground font-medium text-foreground',
              )
            "
            :aria-current="item.month === activeMonth ? 'true' : undefined"
            @click="emit('jump', { year: entry.year, month: item.month })"
          >
            {{ item.label }}
          </button>
          <button
            v-for="race in item.races"
            :key="race.id"
            type="button"
            class="flex items-baseline gap-1.5 py-0.5 pl-4 text-left text-[13px] text-muted-foreground hover:text-foreground"
            :title="race.label"
            @click="emit('jump', { year: entry.year, date: race.date })"
          >
            <span class="tl-mark tl-style-race size-2 shrink-0" aria-hidden="true" />
            <span class="truncate">{{ race.label }}</span>
          </button>
        </li>
      </ul>
    </template>
  </nav>
</template>
