// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
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
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import type { LegacyHealthStatus } from '@/types/health'

const logger = createLogger('useProbeBackedHealth')

/**
 * Maps a backend probe status string to the legacy per-module health vocab.
 * Mirrors the backend's `_PROBE_TO_LEGACY` dict so the two sides stay in sync.
 *
 * @example
 * probeStatusToLegacy('ok')          // → 'healthy'
 * probeStatusToLegacy('degraded')    // → 'unavailable'
 */
export function probeStatusToLegacy(status: ProbeResponse['status']): LegacyHealthStatus {
  return status === 'ok' ? 'healthy' : 'unavailable'
}

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
 * The returned function ALWAYS resolves to `R` and never throws: on a fetch
 * error (or any failure) it returns `options.buildUnavailable(...)` rather
 * than `null`, so consumers never need a null branch (#10119).
 */
export function useProbeBackedHealth<R>(
  options: ProbeBackedHealthOptions<R>,
): () => Promise<R> {
  const api = useApiClient()
  const errorMessage = options.errorMessage ?? `Failed to check ${options.probeName} service health`

  return async (): Promise<R> => {
    try {
      const payload = await api.get<any>(`${getApiBase()}/system/health`)
      const probe = await findProbeByName<ProbeResponse>(payload?.probes, options.probeName)
      if (!probe) {
        return options.buildUnavailable(`${options.probeName} probe not registered`)
      }
      const data = probe.data ?? {}
      if (probe.status === 'ok') {
        return options.buildHealthy(probe, data)
      }
      return options.buildUnavailable(probe.detail ?? 'Service unavailable')
    } catch (error: unknown) {
      logger.error(errorMessage, error)
      return options.buildUnavailable('Service unavailable')
    }
  }
}
