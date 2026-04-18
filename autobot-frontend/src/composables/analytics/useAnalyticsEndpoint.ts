// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Analytics-domain alias for `useFetchEndpoint` (#5153 scope C rehome).
 *
 * Preserves existing analytics semantics:
 *   - `deps.withSourceId` is REQUIRED (not optional).
 *   - `scopeToSource` defaults to **true** — forgetting to scope a
 *     source-namespaced endpoint was the #5111 bug class and the whole
 *     point of introducing the composable originally (#5112).
 *
 * Callers that want to opt out (e.g. `/api/unified/report`) pass
 * `scopeToSource: false` explicitly — same spelling as before.
 *
 * @deprecated New code should import `useFetchEndpoint` from
 *   `@/composables/api/useFetchEndpoint` directly and pass
 *   `scopeToSource: true` (plus the analytics `withSourceId`) when
 *   source scoping is needed. This alias is kept for one release cycle
 *   to avoid churning the 14+ existing analytics call-sites.
 *
 * Original issues: #5111 (bug class), #5112 (introduced),
 * #5137 (merged), #5154 (audit), #5153 (wave-2 umbrella), #5164 (POC).
 */

import {
  useFetchEndpoint,
  type UseFetchEndpointOptions,
  type UseFetchEndpointReturn,
  type FetchEndpointMethod,
} from '../api/useFetchEndpoint'

export type AnalyticsEndpointMethod = FetchEndpointMethod

export type UseAnalyticsEndpointOptions<TRaw, TOut> =
  UseFetchEndpointOptions<TRaw, TOut>

export interface UseAnalyticsEndpointDeps {
  /** Required in the analytics alias (ensures #5111-class bugs are
      prevented by construction). */
  withSourceId: (url: string) => string
}

export type UseAnalyticsEndpointReturn<TOut> = UseFetchEndpointReturn<TOut>

export function useAnalyticsEndpoint<TRaw, TOut>(
  opts: UseFetchEndpointOptions<TRaw, TOut>,
  deps: UseAnalyticsEndpointDeps,
): UseFetchEndpointReturn<TOut> {
  // Default scopeToSource=true for analytics callers; opts.scopeToSource
  // (including explicit false) overrides — `loadUnifiedReport` relies on this.
  return useFetchEndpoint<TRaw, TOut>(
    { scopeToSource: true, ...opts },
    deps,
  )
}
