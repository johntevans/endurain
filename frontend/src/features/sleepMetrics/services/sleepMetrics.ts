// Homelab fork: nightly metric API (backend homelab/eight_sleep/router.py).
import { apiFetch } from '@/services/http'

import type {
  NightlyMetricEntry,
  NightlyMetricKind,
  NightlyMetricPage,
  NightlyMetricParams,
} from '@/features/sleepMetrics/types'

import { NIGHTLY_METRICS } from '@/features/sleepMetrics/metrics'

type Dto = Record<string, unknown>

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

/** Maps one metric's API record to the shared view model. */
export function mapNightlyMetric(kind: NightlyMetricKind, dto: Dto): NightlyMetricEntry {
  const { fields } = NIGHTLY_METRICS[kind]
  return {
    date: String(dto.date),
    value: Number(dto[fields.value]),
    avg7d: numberOrNull(dto[fields.avg7d]),
    baseline: numberOrNull(dto[fields.baseline]),
    rangeLow: numberOrNull(dto[fields.rangeLow]),
    rangeHigh: numberOrNull(dto[fields.rangeHigh]),
    source: String(dto.source),
  }
}

/**
 * Fetches the signed-in user's nights for one metric, newest first.
 *
 * @param kind - The metric.
 * @param params - Time window, plus a page when listing (omit it for the chart).
 * @param signal - Optional abort signal.
 * @returns The page (or the whole window) and the total in the window.
 * @throws {HttpError} When the request fails.
 */
export async function fetchNightlyMetric(
  kind: NightlyMetricKind,
  params: NightlyMetricParams,
  signal?: AbortSignal,
): Promise<NightlyMetricPage> {
  const query = new URLSearchParams({ interval: params.interval })
  if (params.page !== undefined && params.numRecords !== undefined) {
    query.set('page_number', String(params.page))
    query.set('num_records', String(params.numRecords))
  }
  const dto = await apiFetch<{ total: number; records: Dto[] }>(
    `${NIGHTLY_METRICS[kind].path}?${query.toString()}`,
    { signal },
  )
  return {
    total: dto.total,
    records: (dto.records ?? []).map((record) => mapNightlyMetric(kind, record)),
  }
}

/**
 * Fetches the most recent night of one metric.
 *
 * @returns The night, or `null` when there is none.
 * @throws {HttpError} When the request fails.
 */
export async function fetchLatestNightlyMetric(
  kind: NightlyMetricKind,
  signal?: AbortSignal,
): Promise<NightlyMetricEntry | null> {
  const dto = await apiFetch<Dto | null>(`${NIGHTLY_METRICS[kind].path}/latest`, { signal })
  return dto ? mapNightlyMetric(kind, dto) : null
}
