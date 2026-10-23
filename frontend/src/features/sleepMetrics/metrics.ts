// Homelab fork: what differs between the nightly metrics. Everything else (the
// page, chart, list and queries) is shared, so HRV and heart rate look alike.
import { Activity, HeartPulse } from '@lucide/vue'
import type { LucideIcon } from '@lucide/vue'

import type { NightlyMetricKind } from '@/features/sleepMetrics/types'

/** Field names of one metric's API record, in `NightlyMetricEntry` order. */
export interface NightlyMetricFields {
  value: string
  avg7d: string
  baseline: string
  rangeLow: string
  rangeHigh: string
}

export interface NightlyMetric {
  /** API path under `/api/v1`. */
  path: string
  fields: NightlyMetricFields
  /** Unit suffix; values are shown whole, as the Eight Sleep app shows them. */
  unit: string
  /** i18n subtree under `sleepMetrics.` for the metric's own strings. */
  i18nKey: 'hrv' | 'heartRate'
  icon: LucideIcon
}

export const NIGHTLY_METRICS: Record<NightlyMetricKind, NightlyMetric> = {
  hrv: {
    path: '/homelab/sleep_hrv',
    fields: {
      value: 'hrv_ms',
      avg7d: 'avg_7d_ms',
      baseline: 'baseline_ms',
      rangeLow: 'range_low_ms',
      rangeHigh: 'range_high_ms',
    },
    unit: 'ms',
    i18nKey: 'hrv',
    icon: Activity,
  },
  heartRate: {
    path: '/homelab/sleep_heart_rate',
    fields: {
      value: 'hr_bpm',
      avg7d: 'avg_7d_bpm',
      baseline: 'baseline_bpm',
      rangeLow: 'range_low_bpm',
      rangeHigh: 'range_high_bpm',
    },
    unit: 'bpm',
    i18nKey: 'heartRate',
    icon: HeartPulse,
  },
}
