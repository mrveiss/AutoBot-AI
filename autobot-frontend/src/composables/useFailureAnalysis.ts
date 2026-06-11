// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Failure Analysis API Composable
 *
 * Issue #9892: Wire causal-inference engine diagnostics to the frontend.
 *
 * Exposes POST/GET /api/diagnostics/analyze-failure.
 */

import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('FailureAnalysis')

// ---------------------------------------------------------------------------
// Types — derived from CausalAnalysisReport.to_dict()
// ---------------------------------------------------------------------------

export interface CausalEventItem {
  event_id: string
  event_type: string
  name: string
  description: string
  timestamp: string
  confidence: number
  depth: number
  participants: string[]
}

export interface InterventionItem {
  name: string
  description: string
  mechanism: string
  predicted_success_rate: number
  cost_level: string
  risk_level: string
  recommendation_type: string
  impact_rank: number
  confidence: number
  evidence: string[]
}

export interface CausalAnalysisData {
  task_id: string
  error_description: string
  severity: string
  root_cause: CausalEventItem | null
  causal_chain: CausalEventItem[]
  confounders: CausalEventItem[]
  confounding_strength: number
  interventions: InterventionItem[]
  recommendations: string[]
  confidence: number
  chain_depth: number
  timestamp: string
  analysis_status: string
  analysis_duration_ms: number
  error_message: string | null
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useFailureAnalysis() {
  const api = useApiClient()
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)
  const result = ref<CausalAnalysisData | null>(null)

  /**
   * Submit a failure for causal-inference analysis (POST).
   */
  async function analyzeFailure(taskId: string, errorDescription?: string): Promise<CausalAnalysisData | null> {
    error.value = null
    return wrap(async () => {
      try {
        const response = await api.post<{ data: CausalAnalysisData }>(
          `${getApiBase()}/diagnostics/analyze-failure`,
          { task_id: taskId, error_description: errorDescription ?? null }
        )
        result.value = response.data
        return result.value
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failure analysis request failed'
        logger.error('analyzeFailure failed', err)
        error.value = msg
        return null
      }
    })
  }

  function clearResult() {
    result.value = null
    error.value = null
  }

  return {
    loading,
    error,
    result,
    analyzeFailure,
    clearResult,
  }
}
