// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useSpecializedAnalysis (facade)
 *
 * Aggregates five focused composables for backward compatibility:
 * - useApiEndpointAnalysis: coverage scanning, endpoint groups
 * - useConfigDuplicates: duplicate detection
 * - useEnvironmentAnalysis: env scanning, AI filtering
 * - useOwnershipAnalysis: code ownership mapping
 * - useCrossLanguageAnalysis: summary, details, full scan
 *
 * Extracted from useCodeIntelAnalysis (Issue #2260).
 * Decomposed into sub-composables (Issue #2372).
 */

import { useApiEndpointAnalysis } from './useApiEndpointAnalysis'
import { useConfigDuplicates } from './useConfigDuplicates'
import { useEnvironmentAnalysis } from './useEnvironmentAnalysis'
import { useOwnershipAnalysis } from './useOwnershipAnalysis'
import { useCrossLanguageAnalysis } from './useCrossLanguageAnalysis'
import type { UseCodeIntelAnalysisDeps } from './codeIntelTypes'

export function useSpecializedAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const apiEndpoints = useApiEndpointAnalysis(deps)
  const configDuplicates = useConfigDuplicates(deps)
  const environment = useEnvironmentAnalysis(deps)
  const ownership = useOwnershipAnalysis(deps)
  const crossLanguage = useCrossLanguageAnalysis(deps)

  return {
    ...apiEndpoints,
    ...configDuplicates,
    ...environment,
    ...ownership,
    ...crossLanguage,
  }
}
