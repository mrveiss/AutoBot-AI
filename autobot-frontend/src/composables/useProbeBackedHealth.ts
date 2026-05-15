/**
 * Probe-backed health composable (#7247 — DRY identical getHealth templates).
 *
 * Generalizes the recurring pattern from `useBatchProcessing.getHealth` and
 * `useOperationsApi.getHealth`: fetch `/api/system/health`, find a named
 * probe in the payload, fall back to `'unavailable'` if missing or
 * non-`ok`, otherwise build a typed health response from `probe.data`.
 *
 * Usage:
 * ```ts
 * import { useProbeBackedHealth } from '@/composables/useProbeBackedHealth'
 *
 * const getHealth = useProbeBackedHealth<BatchHealthResponse>({
 *   probeName: 'batch_jobs',
 *   buildHealthy: (probe, data) => ({
 *     status: 'healthy',
 *     redis_connected: Boolean(data.redis_connected),
 *     message: probe.detail,
 *     // …other batch-specific fields
 *   }),
 *   buildUnavailable: (message) => ({
 *     status: 'unavailable',
 *     redis_connected: false,
 *     message,
 *     // …same shape as buildHealthy
 *   }),
 *   errorMessage: 'Failed to check batch service health',
 * })
 * ```
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { findProbeByName, type ProbeResponse } from '@/composables/useHealthProbeRegistry'
import { useApiWithState } from '@/composables/useApi'
import { getApiBase } from '@/config/ssot-config'

export interface ProbeBackedHealthOptions<R> {
  /** Probe name to look up in `/api/system/health` payload (e.g. `'batch_jobs'`). */
  probeName: string

  /** Build a healthy-shape response from the probe entry + its `data` object. */
  buildHealthy: (probe: ProbeResponse, data: Record<string, unknown>) => R

  /** Build an unavailable-shape response with the given message. */
  buildUnavailable: (message: string) => R

  /** Error toast message when the underlying fetch fails. */
  errorMessage?: string
}

/**
 * Returns a `getHealth()` async function that wraps the
 * `/api/system/health` + probe-name-lookup + status-mapping template.
 *
 * The returned function is null-on-fetch-error (consistent with existing
 * consumers using `withErrorHandling`'s `silent: true` mode); it never
 * throws to the caller.
 */
export function useProbeBackedHealth<R>(
  options: ProbeBackedHealthOptions<R>,
): () => Promise<R | null> {
  const { api, withErrorHandling } = useApiWithState()
  const errorMessage = options.errorMessage ?? `Failed to check ${options.probeName} service health`

  return async (): Promise<R | null> => {
    return withErrorHandling(
      async () => {
        const response = (await api.get<any>(`${getApiBase()}/system/health`)) as Response
        const payload = await response.json()
        const probe = await findProbeByName<ProbeResponse>(payload?.probes, options.probeName)
        if (!probe) {
          return options.buildUnavailable(`${options.probeName} probe not registered`)
        }
        const data = probe.data ?? {}
        if (probe.status === 'ok') {
          return options.buildHealthy(probe, data)
        }
        return options.buildUnavailable(probe.detail ?? 'Service unavailable')
      },
      {
        errorMessage,
        fallbackValue: options.buildUnavailable('Service unavailable'),
        silent: true,
      },
    )
  }
}
