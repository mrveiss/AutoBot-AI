// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useConfigDuplicates
 *
 * Configuration duplicate detection analysis.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 */

import { useAnalyticsFetch } from '@/composables/useAnalyticsFetch'
import type {
  UseCodeIntelAnalysisDeps,
  ConfigDuplicatesResult,
} from './codeIntelTypes'

export function useConfigDuplicates(
  deps: UseCodeIntelAnalysisDeps,
) {
  const { sourceIdQuery } = deps

  const {
    data: configDuplicatesAnalysis,
    loading: loadingConfigDuplicates,
    error: configDuplicatesError,
    load: _loadConfigDuplicates,
  } = useAnalyticsFetch<ConfigDuplicatesResult>(
    '/api/analytics/codebase/config-duplicates',
    (r) => {
      if (r.status === 'success') {
        return {
          duplicates_found: (r.duplicates_found as number) || 0,
          duplicates:
            (r.duplicates as ConfigDuplicatesResult['duplicates']) ||
            [],
          report: (r.report as string) || '',
        }
      }
      return undefined
    },
  )

  const loadConfigDuplicates = () =>
    _loadConfigDuplicates(sourceIdQuery.value)

  return {
    configDuplicatesAnalysis,
    loadingConfigDuplicates,
    configDuplicatesError,
    loadConfigDuplicates,
  }
}
