// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Health-probe registry composable (#7008 wire-in for #7003 / #6917 phase 1).
 *
 * Lazily fetches the canonical list of registered probe names from
 * `GET /api/system/health/probes` and caches it. Provides a name-validated
 * lookup helper so that typos in `probes.find(p => p.name === '…')` call
 * sites surface as a loud warning instead of silently falling through to
 * the 'unavailable' fallback.
 *
 * Cache invalidation:
 * - First `findProbeByName()` call triggers a fetch.
 * - `refreshRegistry()` forces a refetch (call when the backend reconnects;
 *   probe names can change between deploys per #7008 acceptance).
 * - Fetch failures don't poison the cache: the next call retries.
 *
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useHealthProbeRegistry')

/**
 * Shape of a single probe entry in the `/api/system/health` response payload.
 *
 * Exported (#7248) so consumers don't have to redeclare the inline literal
 * `{ name: string; status?: string; data?: Record<string, unknown>; detail?: string }`
 * type at every probe-lookup site. Extends-friendly: callers needing extra
 * fields can declare `interface ExtendedProbe extends ProbeResponse { … }`.
 */
export interface ProbeResponse {
  name: string
  status?: 'ok' | 'degraded' | 'unavailable' | string
  data?: Record<string, unknown>
  detail?: string
}

let _cache: Set<string> | null = null
let _inflight: Promise<Set<string> | null> | null = null
const _warnedNames = new Set<string>()

async function fetchRegistry(): Promise<Set<string> | null> {
  try {
    const r = await fetch(`${getApiBase()}/system/health/probes`)
    if (!r.ok) {
      logger.warn(`probe registry fetch returned ${r.status}; lookups will skip name validation until next call`)
      return null
    }
    const body: unknown = await r.json()
    if (!Array.isArray(body) || !body.every((n) => typeof n === 'string')) {
      logger.warn('probe registry endpoint returned non-string-array — skipping validation', { body })
      return null
    }
    return new Set(body as string[])
  } catch (err) {
    logger.error('probe registry fetch threw', err)
    return null
  }
}

/** Get the cached probe-name registry, fetching on first call. */
export async function getProbeRegistry(): Promise<Set<string> | null> {
  if (_cache) return _cache
  if (_inflight) return _inflight
  _inflight = fetchRegistry().then((s) => {
    if (s) _cache = s
    _inflight = null
    return s
  })
  return _inflight
}

/** Force a refetch — call this when the backend reconnects after being unreachable. */
export async function refreshProbeRegistry(): Promise<Set<string> | null> {
  _cache = null
  _inflight = null
  _warnedNames.clear()
  return getProbeRegistry()
}

/**
 * Find a probe by name in a `/api/system/health` payload, validating the
 * name against the canonical registry. A typo on the caller side surfaces
 * as a one-shot logger.warn instead of silently returning undefined.
 */
export async function findProbeByName<T extends ProbeResponse = ProbeResponse>(
  probes: T[] | null | undefined,
  name: string,
): Promise<T | undefined> {
  const registry = await getProbeRegistry()
  if (registry && !registry.has(name) && !_warnedNames.has(name)) {
    _warnedNames.add(name)
    logger.warn(
      `probe name '${name}' is not in the canonical registry — likely a typo or stale call site. ` +
        `Known probes: ${[...registry].sort().join(', ')}`,
    )
  }
  return (probes ?? []).find((p) => p.name === name)
}

/** Test-only: reset module-level state. */
export function _resetProbeRegistryForTesting(): void {
  _cache = null
  _inflight = null
  _warnedNames.clear()
}
