<script setup lang="ts" generic="T extends string">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { Check, ChevronDown } from '@lucide/vue'
import { DropdownMenuCheckboxItem, DropdownMenuItemIndicator } from 'reka-ui'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { cn } from '@/lib/utils'

/**
 * Homelab fork: a training-log filter pulldown with a checkbox per option.
 * Ticking options keeps the menu open; "All" at the top clears them. The
 * selection is kept in option order, so the URL it ends up in is stable.
 */
const props = defineProps<{
  /** On the wrapper: reka gives the trigger button an id of its own. */
  id: string
  /** The trigger's accessible name (the filter's name, e.g. "Sport"). */
  label: string
  options: ReadonlyArray<{ value: T; label: string }>
  /** The label of the "everything" entry, and the button text when nothing is ticked. */
  allLabel: string
  /** The button text when more than two options are ticked. */
  countLabel: (count: number) => string
  class?: HTMLAttributes['class']
}>()

/** The ticked options; empty means all. */
const model = defineModel<readonly T[]>({ required: true })

const selected = computed(() => new Set(model.value))

const summary = computed(() => {
  if (model.value.length === 0) {
    return props.allLabel
  }
  const labels = props.options
    .filter((option) => selected.value.has(option.value))
    .map((option) => option.label)
  return labels.length === model.value.length && labels.length <= 2
    ? labels.join(', ')
    : props.countLabel(model.value.length)
})

function toggle(value: T, checked: boolean): void {
  const next = new Set(selected.value)
  if (checked) {
    next.add(value)
  } else {
    next.delete(value)
  }
  model.value = props.options.map((option) => option.value).filter((option) => next.has(option))
}

const itemClass =
  'group relative flex cursor-pointer items-center gap-2 rounded-sm py-1.5 pr-2 pl-8 text-sm text-muted-foreground outline-none transition-colors select-none hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground data-[state=checked]:text-foreground'
const boxClass =
  'absolute left-2 flex size-4 items-center justify-center rounded-[4px] border border-input bg-background text-primary-foreground group-data-[state=checked]:border-primary group-data-[state=checked]:bg-primary'
</script>

<template>
  <div :id="id" :class="props.class">
    <DropdownMenu :modal="false">
      <DropdownMenuTrigger
        :class="
          cn(
            inputFieldClass,
            'flex w-full items-center justify-between gap-2 text-left data-[state=open]:border-ring',
          )
        "
        :aria-label="`${label}: ${summary}`"
        :title="summary"
      >
        <span class="truncate">{{ summary }}</span>
        <ChevronDown class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        class="max-h-[min(24rem,var(--reka-dropdown-menu-content-available-height))] min-w-(--reka-dropdown-menu-trigger-width) overflow-y-auto"
      >
        <DropdownMenuCheckboxItem
          :model-value="model.length === 0"
          :class="itemClass"
          data-option="all"
          @select.prevent
          @update:model-value="model = []"
        >
          <span :class="boxClass">
            <DropdownMenuItemIndicator><Check class="size-3" /></DropdownMenuItemIndicator>
          </span>
          {{ allLabel }}
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        <DropdownMenuCheckboxItem
          v-for="option in options"
          :key="option.value"
          :model-value="selected.has(option.value)"
          :class="itemClass"
          :data-option="option.value"
          @select.prevent
          @update:model-value="(checked) => toggle(option.value, checked === true)"
        >
          <span :class="boxClass">
            <DropdownMenuItemIndicator><Check class="size-3" /></DropdownMenuItemIndicator>
          </span>
          {{ option.label }}
        </DropdownMenuCheckboxItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>
