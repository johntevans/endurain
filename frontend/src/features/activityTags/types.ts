/**
 * Homelab fork: activity tags (Race, Workout, Long Run, NSM Short/Medium/Long).
 *
 * Wire shapes from the generated OpenAPI schema; the backend lives in
 * `backend/app/homelab/activity_tags` and stores tags in the fork-owned
 * `homelab` schema.
 */
import type { Schemas } from '@/types'

/** A stable tag key, as stored and sent over the wire. */
export type ActivityTagKey = Schemas['ActivityTagKey']

/** One activity's tags, as returned by the batch endpoints. */
export type ActivityTagsReadDto = Schemas['ActivityTagsRead']

/** Body of the owner-only "replace tags" request. */
export type ActivityTagsUpdateDto = Schemas['ActivityTagsUpdate']
