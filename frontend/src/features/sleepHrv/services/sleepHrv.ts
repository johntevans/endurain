// Homelab fork: nightly HRV API (backend homelab/eight_sleep/router.py).
import { apiFetch } from '@/services/http'

import type {
  SleepHrvDto,
  SleepHrvEntry,
  SleepHrvListDto,
  SleepHrvPage,
  SleepHrvParams,
} from '@/features/sleepHrv/types'

/** Maps a night's DTO to the view model. */
export function mapSleepHrv(dto: SleepHrvDto): SleepHrvEntry {
  return {
    date: dto.date,
    hrvMs: dto.hrv_ms,
    avg7dMs: dto.avg_7d_ms ?? null,
    baselineMs: dto.baseline_ms ?? null,
    rangeLowMs: dto.range_low_ms ?? null,
    rangeHighMs: dto.range_high_ms ?? null,
    source: dto.source,
  }
}

/**
 * Fetches the signed-in user's nightly HRV, newest first.
 *
 * @param params - Time window, plus a page when listing (omit it for the chart).
 * @param signal - Optional abort signal.
 * @returns The page (or the whole window) and the total in the window.
 * @throws {HttpError} When the request fails.
 */
export async function fetchSleepHrv(
  params: SleepHrvParams,
  signal?: AbortSignal,
): Promise<SleepHrvPage> {
  const query = new URLSearchParams({ interval: params.interval })
  if (params.page !== undefined && params.numRecords !== undefined) {
    query.set('page_number', String(params.page))
    query.set('num_records', String(params.numRecords))
  }
  const dto = await apiFetch<SleepHrvListDto>(`/homelab/sleep_hrv?${query.toString()}`, { signal })
  return { total: dto.total, records: (dto.records ?? []).map(mapSleepHrv) }
}

/**
 * Fetches the most recent night with HRV.
 *
 * @param signal - Optional abort signal.
 * @returns The night, or `null` when there is none.
 * @throws {HttpError} When the request fails.
 */
export async function fetchLatestSleepHrv(signal?: AbortSignal): Promise<SleepHrvEntry | null> {
  const dto = await apiFetch<SleepHrvDto | null>('/homelab/sleep_hrv/latest', { signal })
  return dto ? mapSleepHrv(dto) : null
}
