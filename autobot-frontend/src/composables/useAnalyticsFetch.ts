// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * @deprecated
 * `useAnalyticsFetch` was removed in #5208/#5235 and fully superseded by
 * `useFetchEndpoint` (originally shipped as `analytics/useAnalyticsEndpoint`
 * in #5112, then rehomed in #5154).
 *
 * This file is a thin re-export alias kept only for editor-tooling discoverability.
 * No runtime callers remain — all five former callers were migrated in #5208.
 *
 * **Migrate any new usage to the canonical import:**
 * ```ts
 * import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
 * ```
 *
 * Issue #5172.
 */

export {
  useFetchEndpoint as useAnalyticsFetch,
  type UseFetchEndpointOptions as UseAnalyticsFetchOptions,
  type UseFetchEndpointDeps as UseAnalyticsFetchDeps,
  type UseFetchEndpointReturn as UseAnalyticsFetchReturn,
  type FetchEndpointMethod,
} from '@/composables/api/useFetchEndpoint'
