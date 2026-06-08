// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useSourcesListEndpoint (#5276)
 *
 * Shared `GET /api/analytics/codebase/sources` fetcher. Extracted from
 * the identical definitions in `CodebaseAnalyticsLanding.vue` and
 * `useSourceRegistry.ts` — same endpoint, same response shape, same
 * `onSuccess` handler.
 *
 * Returns the reactive `sources` ref + the `useFetchEndpoint` handle
 * so each caller can own loading/error presentation (Landing shows a
 * page-level spinner; useSourceRegistry is silent on failure).
 */

import { ref } from 'vue'
import type { Ref } from 'vue'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import type { CodeSource } from '@/types/analytics'

export interface UseSourcesListEndpointReturn {
  sources: Ref<CodeSource[]>
  loadSources: () => Promise<void>
  loading: Ref<boolean>
  error: Ref<string | null>
}

export function useSourcesListEndpoint(): UseSourcesListEndpointReturn {
  const sources = ref<CodeSource[]>([])

  const endpoint = useFetchEndpoint<
    { sources?: CodeSource[] },
    CodeSource[]
  >({
    path: '/api/analytics/codebase/sources',
    label: 'Sources list',
    pickData: (r) => r.sources ?? [],
    onSuccess: (list) => {
      sources.value = list
    },
  })

  async function loadSources() {
    await endpoint.load()
  }

  return {
    sources,
    loadSources,
    loading: endpoint.loading,
    error: endpoint.error,
  }
}
