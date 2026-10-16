<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { CalendarRange } from '@lucide/vue'

import type {
  SportFamily,
  SportFilter,
  SportOption,
  TagFilter,
  TrainingLogMetric,
  TrainingLogWeek,
} from '@/features/trainingLog/types'
import type { ActivityTagKey } from '@/features/activityTags/types'

import '@/features/trainingLog/trainingLog.css'
import TrainingLogLegend from '@/features/trainingLog/components/TrainingLogLegend.vue'
import TrainingLogMultiSelect from '@/features/trainingLog/components/TrainingLogMultiSelect.vue'
import TrainingLogSideNav from '@/features/trainingLog/components/TrainingLogSideNav.vue'
import TrainingLogYear from '@/features/trainingLog/components/TrainingLogYear.vue'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useRouteQueryReplacement } from '@/composables/useRouteQuery'
import { useUserActivityTypeMapQuery } from '@/features/activities/composables/useActivities'
import { useTrainingLogRangeQuery } from '@/features/trainingLog/composables/useTrainingLog'
import { ACTIVITY_TAGS } from '@/features/activityTags/utils/activityTags'
import { presentActivityType } from '@/features/activities/utils/activityType'
import {
  buildTrainingLogYears,
  filterFamilies,
  localTodayIso,
  monthWeekIndex,
  parseMetric,
  parseSportFilter,
  parseTagFilter,
  sportFamily,
  sportFilterOptions,
  weekMonth,
  weekOf,
} from '@/features/trainingLog/utils/trainingLog'

/**
 * Homelab fork: the training log. Every week since the first activity, newest
 * first, one circle per activity sized by time, distance or elevation, with
 * the week's total on the left and a year/month index on the right, after
 * Strava's Training Log.
 */
const { t, locale } = useI18n()
const route = useRoute()
const { data: currentUser } = useCurrentUser()

const units = computed(() => currentUser.value?.units ?? 'metric')
const firstDayOfWeek = computed(() => currentUser.value?.firstDayOfWeek ?? 'monday')
const today = localTodayIso()

// --- Filters (mirrored into the URL so a refresh or a shared link keeps them).
// Sport and tag are lists (`?sport=run,type-1001&tag=workout,long_run`); an
// empty list means all.
const sport = ref<SportFilter>(parseSportFilter(route.query.sport))
const metric = ref<TrainingLogMetric>(parseMetric(route.query.metric))
const tag = ref<TagFilter>(parseTagFilter(route.query.tag))

useRouteQueryReplacement(
  computed(() => ({
    sport: sport.value.length === 0 ? undefined : sport.value.join(','),
    metric: metric.value === 'time' ? undefined : metric.value,
    tag: tag.value.length === 0 ? undefined : tag.value.join(','),
  })),
)

const typeMapQuery = useUserActivityTypeMapQuery()
const typeCodes = computed(() => [...(typeMapQuery.data.value?.keys() ?? [])])
const sportOptions = computed<Array<{ value: SportOption; label: string }>>(() =>
  sportFilterOptions(typeCodes.value).map((option) => ({
    value: option.value,
    label: option.labelKey
      ? t(option.labelKey)
      : t(presentActivityType(option.activityType ?? 0).labelKey),
  })),
)
const tagOptions = computed<Array<{ value: ActivityTagKey; label: string }>>(() =>
  ACTIVITY_TAGS.map((option) => ({ value: option.key, label: t(option.labelKey) })),
)

const METRIC_OPTIONS: ReadonlyArray<{ value: TrainingLogMetric; labelKey: string }> = [
  { value: 'time', labelKey: 'trainingLog.metrics.time' },
  { value: 'distance', labelKey: 'trainingLog.metrics.distance' },
  { value: 'elevation', labelKey: 'trainingLog.metrics.elevation' },
]

// Distances read in swim units only when swimming is all that is shown.
const selectedFamilies = computed(() => filterFamilies(sport.value))
const swim = computed(
  () => selectedFamilies.value.length === 1 && selectedFamilies.value[0] === 'swim',
)
const legendFamilies = computed<SportFamily[]>(() => {
  if (selectedFamilies.value.length > 0) {
    return selectedFamilies.value
  }
  const present = new Set(typeCodes.value.map(sportFamily))
  return (['run', 'ride', 'swim', 'walk', 'other'] as const).filter((family) => present.has(family))
})
const legendStyleFamily = computed<SportFamily>(() => legendFamilies.value[0] ?? 'run')
const showLongRun = computed(
  () => selectedFamilies.value.length === 0 || selectedFamilies.value.includes('run'),
)

// --- Years and weeks
const rangeQuery = useTrainingLogRangeQuery()
const firstDate = computed(() => rangeQuery.data.value?.firstDate ?? null)
const years = computed(() => {
  const first = firstDate.value
  if (!first) {
    return []
  }
  const last = rangeQuery.data.value?.lastDate
  return buildTrainingLogYears(first, last && last > today ? last : today, firstDayOfWeek.value)
})

const weekdayLabels = computed(() => {
  const week = weekOf(today, firstDayOfWeek.value)
  const short = new Intl.DateTimeFormat(locale.value, { weekday: 'short', timeZone: 'UTC' })
  const narrow = new Intl.DateTimeFormat(locale.value, { weekday: 'narrow', timeZone: 'UTC' })
  return week.days.map((day) => {
    const date = new Date(`${day}T00:00:00Z`)
    return { day, short: short.format(date), narrow: narrow.format(date) }
  })
})

// --- Scroll position: which year/month is at the top, and jumping to one.
// Rows have a fixed height, so a week's position is arithmetic on its year's
// rows container, whether or not that year has loaded yet.
const logEl = ref<HTMLElement | null>(null)
const weekdayHeaderEl = ref<HTMLElement | null>(null)
const activeYear = ref<number | null>(null)
const activeMonth = ref<string | null>(null)

/** Viewport y below the sticky navbar and weekday header. */
function stickyBottom(): number {
  const header = weekdayHeaderEl.value
  if (!header) {
    return 0
  }
  return (Number.parseFloat(getComputedStyle(header).top) || 0) + header.offsetHeight
}

function rowsOf(year: number): HTMLElement | null {
  return logEl.value?.querySelector<HTMLElement>(`[data-tl-year="${year}"] [data-tl-rows]`) ?? null
}

function updateActive(): void {
  const anchor = stickyBottom() + 8
  for (const entry of years.value) {
    const rows = rowsOf(entry.year)
    if (!rows || entry.weeks.length === 0) {
      continue
    }
    const rect = rows.getBoundingClientRect()
    if (rect.bottom > anchor) {
      const rowHeight = rect.height / entry.weeks.length
      const index = Math.min(
        Math.max(Math.floor((anchor - rect.top) / rowHeight), 0),
        entry.weeks.length - 1,
      )
      activeYear.value = entry.year
      activeMonth.value = weekMonth(entry.weeks[index] as TrainingLogWeek)
      return
    }
  }
  const last = years.value[years.value.length - 1]
  const oldestWeek = last?.weeks[last.weeks.length - 1]
  activeYear.value = last?.year ?? null
  activeMonth.value = oldestWeek ? weekMonth(oldestWeek) : null
}

let frame = 0
function onScroll(): void {
  if (frame === 0) {
    frame = requestAnimationFrame(() => {
      frame = 0
      updateActive()
    })
  }
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll, { passive: true })
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
  cancelAnimationFrame(frame)
})
watch(years, () => requestAnimationFrame(updateActive), { flush: 'post' })

/** Scrolls so a week (or, for index 0, its year heading) sits under the header. */
function scrollToWeek(year: number, index: number): void {
  const rows = rowsOf(year)
  const entry = years.value.find((item) => item.year === year)
  if (!rows || !entry) {
    return
  }
  const target = index <= 0 ? (rows.parentElement ?? rows) : rows
  const offset = index <= 0 ? 0 : (rows.getBoundingClientRect().height / entry.weeks.length) * index
  const top = target.getBoundingClientRect().top + window.scrollY + offset - stickyBottom()
  window.scrollTo({ top: Math.max(top, 0) })
}

function jump(target: { year: number; month?: string; date?: string }): void {
  if (target.date) {
    const date = target.date
    for (const entry of years.value) {
      const index = entry.weeks.findIndex(
        (week) => week.start <= date && date <= (week.days[6] ?? ''),
      )
      if (index >= 0) {
        scrollToWeek(entry.year, index)
        return
      }
    }
    return
  }
  const entry = years.value.find((item) => item.year === target.year)
  if (!entry) {
    return
  }
  const index = target.month ? monthWeekIndex(entry.weeks, target.month) : 0
  scrollToWeek(entry.year, Math.max(index, 0))
}

// Mobile has no side nav: a year picker instead.
const yearPicker = computed<number>({
  get: () => activeYear.value ?? years.value[0]?.year ?? 0,
  set: (year) => jump({ year }),
})
</script>

<template>
  <section class="flex flex-col gap-4">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('trainingLog.title') }}</h1>
    </header>

    <!-- Filters and legend -->
    <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <div>
          <TrainingLogMultiSelect
            id="training-log-sport"
            :label="t('trainingLog.filters.sport')"
            v-model="sport"
            :options="sportOptions"
            :all-label="t('trainingLog.filters.allSports')"
            :count-label="(count) => t('trainingLog.filters.sportCount', { count })"
            class="w-full sm:w-48"
          />
        </div>
        <div>
          <Label for="training-log-metric" class="sr-only">{{
            t('trainingLog.filters.metric')
          }}</Label>
          <Select id="training-log-metric" v-model="metric" class="w-full sm:w-36">
            <option v-for="option in METRIC_OPTIONS" :key="option.value" :value="option.value">
              {{ t(option.labelKey) }}
            </option>
          </Select>
        </div>
        <div>
          <TrainingLogMultiSelect
            id="training-log-tag"
            :label="t('trainingLog.filters.tag')"
            v-model="tag"
            :options="tagOptions"
            :all-label="t('trainingLog.filters.allTags')"
            :count-label="(count) => t('trainingLog.filters.tagCount', { count })"
            class="w-full sm:w-48"
          />
        </div>
        <div v-if="years.length > 1" class="lg:hidden">
          <Label for="training-log-year" class="sr-only">{{ t('trainingLog.filters.year') }}</Label>
          <Select id="training-log-year" v-model="yearPicker" class="w-full sm:w-28">
            <option v-for="entry in years" :key="entry.year" :value="entry.year">
              {{ entry.year }}
            </option>
          </Select>
        </div>
      </div>
      <TrainingLogLegend
        :families="legendFamilies"
        :style-family="legendStyleFamily"
        :show-long-run="showLongRun"
      />
    </div>

    <div v-if="rangeQuery.isPending.value" class="flex flex-col gap-3">
      <Skeleton v-for="index in 4" :key="index" class="h-32 w-full" />
    </div>
    <ErrorState
      v-else-if="rangeQuery.isError.value"
      :title="t('trainingLog.error.title')"
      :description="t('trainingLog.error.description')"
      @retry="rangeQuery.refetch()"
    />
    <EmptyState
      v-else-if="years.length === 0"
      :title="t('trainingLog.empty.title')"
      :description="t('trainingLog.empty.description')"
    >
      <template #icon>
        <CalendarRange class="size-8" aria-hidden="true" />
      </template>
    </EmptyState>

    <div
      v-else
      class="grid grid-cols-1 gap-6 [--tl-circle-zone:2.75rem] [--tl-circle:2.4rem] [--tl-row-h:6.25rem] [--tl-year-h:3.25rem] sm:[--tl-circle-zone:5.5rem] sm:[--tl-circle:4.5rem] sm:[--tl-row-h:11.5rem] lg:grid-cols-[minmax(0,1fr)_13rem] lg:[--tl-circle-zone:6.5rem] lg:[--tl-circle:5.5rem] lg:[--tl-row-h:12.5rem]"
    >
      <div ref="logEl" class="min-w-0">
        <div
          ref="weekdayHeaderEl"
          class="sticky top-[calc(env(safe-area-inset-top)+3.5rem)] z-20 grid grid-cols-7 border-b border-border bg-background py-2 sm:grid-cols-[8.5rem_repeat(7,minmax(0,1fr))] lg:grid-cols-[10rem_repeat(7,minmax(0,1fr))]"
          aria-hidden="true"
        >
          <span class="hidden sm:block" />
          <span
            v-for="label in weekdayLabels"
            :key="label.day"
            class="text-center text-meta text-muted-foreground"
          >
            <span class="sm:hidden">{{ label.narrow }}</span>
            <span class="hidden sm:inline">{{ label.short }}</span>
          </span>
        </div>
        <TrainingLogYear
          v-for="entry in years"
          :key="entry.year"
          :year="entry.year"
          :weeks="entry.weeks"
          :sport="sport"
          :tag="tag"
          :metric="metric"
          :units="units"
          :swim="swim"
          :today="today"
          :first-date="firstDate ?? today"
        />
      </div>
      <aside class="hidden lg:block">
        <div
          class="sticky top-[calc(env(safe-area-inset-top)+3.5rem+1rem)] max-h-[calc(100svh-6rem)] overflow-y-auto"
        >
          <TrainingLogSideNav
            :years="years"
            :active-year="activeYear"
            :active-month="activeMonth"
            @jump="jump"
          />
        </div>
      </aside>
    </div>
  </section>
</template>
