<script setup lang="ts">
/**
 * Homelab fork: one of the fitness page's numbers, in the metric-pill style
 * but with any colour (Intervals colours Form by its zone).
 */
defineProps<{
  label: string
  value: string
  /** Colour of the number; the text colour when omitted. */
  color?: string
}>()
</script>

<template>
  <div class="flex min-w-[100px] flex-col gap-1">
    <p class="text-caption">{{ label }}</p>
    <p class="text-metric font-medium leading-tight" :style="color ? { color } : undefined">
      {{ value }}
    </p>
    <!-- e.g. the Form zone's name -->
    <slot />
  </div>
</template>
