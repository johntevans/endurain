<script setup lang="ts" generic="T extends string | number">
import type { HTMLAttributes } from 'vue'
import { ChevronDown } from '@lucide/vue'

import { Select } from '@/components/ui/select'
import { cn } from '@/lib/utils'

/**
 * Homelab fork: a native select that matches the training log's pulldowns.
 * Safari draws a select with its own control, which ignores the field's
 * padding and comes out shorter than the menu buttons beside it; with
 * `appearance-none` it takes the field's size, and the chevron is drawn here.
 */
const props = defineProps<{ id: string; class?: HTMLAttributes['class'] }>()

const model = defineModel<T>({ required: true })
</script>

<template>
  <div :class="cn('relative', props.class)">
    <Select :id="id" v-model="model" class="w-full appearance-none pr-9">
      <slot />
    </Select>
    <ChevronDown
      class="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
      aria-hidden="true"
    />
  </div>
</template>
