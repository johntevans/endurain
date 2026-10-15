import type { ActivityTagKey } from '@/features/activityTags/types'

import type { BadgeVariants } from '@/components/ui/badge'

/**
 * The fixed tag set in display order (Race, Workout, Long Run), with each
 * tag's label key and badge style. The backend accepts exactly these keys.
 */
export const ACTIVITY_TAGS = [
  { key: 'race', labelKey: 'activityTags.labels.race', variant: 'warning' },
  { key: 'workout', labelKey: 'activityTags.labels.workout', variant: 'info' },
  { key: 'long_run', labelKey: 'activityTags.labels.longRun', variant: 'secondary' },
] as const satisfies ReadonlyArray<{
  key: ActivityTagKey
  labelKey: string
  variant: BadgeVariants['variant']
}>

/** Narrows an arbitrary value to a known tag key. */
export function isActivityTagKey(value: unknown): value is ActivityTagKey {
  return ACTIVITY_TAGS.some((tag) => tag.key === value)
}

/**
 * De-duplicates tags, drops unknown ones and puts them in display order.
 *
 * @param tags - Tags in any order, possibly repeated.
 * @returns Known tags, unique, in {@link ACTIVITY_TAGS} order.
 */
export function sortActivityTags(tags: readonly unknown[]): ActivityTagKey[] {
  return ACTIVITY_TAGS.map((tag) => tag.key).filter((key) => tags.includes(key))
}

/** Whether two tag lists hold the same tags, regardless of order. */
export function sameActivityTags(
  a: readonly ActivityTagKey[],
  b: readonly ActivityTagKey[],
): boolean {
  const left = sortActivityTags(a)
  const right = sortActivityTags(b)
  return left.length === right.length && left.every((tag, index) => tag === right[index])
}

/**
 * Parses the activities list's `tags` URL query param (`race,long_run`).
 * Unknown keys are ignored, so a stale or hand-edited URL never errors.
 *
 * @param value - Raw route query value.
 * @returns The valid tags, in display order.
 */
export function parseActivityTagsQuery(value: unknown): ActivityTagKey[] {
  if (typeof value !== 'string' || value === '') {
    return []
  }
  return sortActivityTags(value.split(','))
}

/** Formats tags for the `tags` URL query param (inverse of the parser). */
export function formatActivityTagsQuery(tags: readonly ActivityTagKey[]): string {
  return sortActivityTags(tags).join(',')
}
