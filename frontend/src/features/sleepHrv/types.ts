// Homelab fork: nightly HRV from Eight Sleep (backend homelab/eight_sleep).

import type { HealthInterval } from '@/features/health/types'

/** One night as `GET /homelab/sleep_hrv` returns it. All values in ms. */
export interface SleepHrvDto {
  date: string
  hrv_ms: number
  avg_7d_ms: number | null
  baseline_ms: number | null
  range_low_ms: number | null
  range_high_ms: number | null
  source: string
}

/** A page of nights, newest first. */
export interface SleepHrvListDto {
  total: number
  records: SleepHrvDto[]
}

/** One night's HRV: Eight Sleep's own figures, so they match its app. */
export interface SleepHrvEntry {
  /** Wake-up date, `YYYY-MM-DD` (the same date as that night's sleep record). */
  date: string
  /** The night's HRV (RMSSD), ms. */
  hrvMs: number
  /** 7-day average including this night, ms. */
  avg7dMs: number | null
  /** Long-run average, ms. */
  baselineMs: number | null
  /** Lower edge of the usual range, ms. */
  rangeLowMs: number | null
  /** Upper edge of the usual range, ms. */
  rangeHighMs: number | null
  source: string
}

export interface SleepHrvPage {
  total: number
  records: SleepHrvEntry[]
}

/** Query parameters; omit paging to get the whole window (for the chart). */
export interface SleepHrvParams {
  interval: HealthInterval
  page?: number
  numRecords?: number
}

/** Where a night sits against its usual range. */
export type SleepHrvStatus = 'below' | 'within' | 'above'
