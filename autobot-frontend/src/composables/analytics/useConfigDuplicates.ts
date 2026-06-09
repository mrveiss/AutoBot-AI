// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useConfigDuplicates
 *
 * Configuration duplicate detection analysis.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 * Migrated from useAnalyticsFetch to useFetchEndpoint (Issue #5208 POC).
 */

import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import type {
  UseCodeIntelAnalysisDeps,
  ConfigDuplicatesResult,
} from './codeIntelTypes'

interface ConfigDuplicatesRaw {
  status: string
  duplicates_found?: number
  duplicates?: ConfigDuplicatesResult['duplicates']
  report?: string
}

export function useConfigDuplicates(deps: UseCodeIntelAnalysisDeps) {
  const { withSourceId } = deps

  const endpoint = useFetchEndpoint<ConfigDuplicatesRaw, ConfigDuplicatesResult>(
    {
      path: '/api/analytics/codebase/config-duplicates',
      scopeToSource: true,
      pickData: (r) =>
        r.status === 'success'
          ? {
              duplicates_found: r.duplicates_found ?? 0,
              duplicates: r.duplicates ?? [],
              report: r.report ?? '',
            }
          : null,
    },
    { withSourceId },
  )

  return {
    configDuplicatesAnalysis: endpoint.data,
    loadingConfigDuplicates: endpoint.loading,
    configDuplicatesError: endpoint.error,
    loadConfigDuplicates: endpoint.load,
  }
}
