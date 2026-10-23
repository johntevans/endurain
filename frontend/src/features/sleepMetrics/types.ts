// Homelab fork: nightly metrics from Eight Sleep (backend homelab/eight_sleep).

import type { HealthInterval } from '@/features/health/types'

/** The per-night metrics the fork stores, one table and endpoint each. */
export type NightlyMetricKind = 'hrv' | 'heartRate'

/**
 * One night: Eight Sleep's own figures, so they match its app. The value and
 * every derived figure share the metric's unit (ms for HRV, bpm for heart rate).
 */
export interface NightlyMetricEntry {
  /** Wake-up date, `YYYY-MM-DD` (the same date as that night's sleep record). */
  date: string
  /** The night's value. */
  value: number
  /** 7-day average including this night. */
  avg7d: number | null
  /** Long-run average. */
  baseline: number | null
  /** Lower edge of the usual range. */
  rangeLow: number | null
  /** Upper edge of the usual range. */
  rangeHigh: number | null
  source: string
}

export interface NightlyMetricPage {
  total: number
  records: NightlyMetricEntry[]
}

/** Query parameters; omit paging to get the whole window (for the chart). */
export interface NightlyMetricParams {
  interval: HealthInterval
  page?: number
  numRecords?: number
}

/** Where a night sits against its usual range. */
export type NightlyMetricStatus = 'below' | 'within' | 'above'
