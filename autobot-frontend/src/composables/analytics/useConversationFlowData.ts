// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useConversationFlowData
 *
 * Encapsulates all API data fetching for ConversationFlowDashboard.
 * Extracted from ConversationFlowDashboard.vue — Issue #6071.
 * Migrated from fetchWithAuth to useFetchEndpoint — Issue #6071.
 */

import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useConversationFlowData')

export interface IntentPattern {
  intent_id: string
  intent_name: string
  pattern_regex: string
  occurrences: number
  success_rate: number
  avg_turns_to_resolve: number
  sample_queries: string[]
}

export interface ConversationFlow {
  flow_id: string
  path: string[]
  frequency: number
  avg_duration_seconds: number
  completion_rate: number
  drop_off_point: string | null
}

export interface FlowBottleneck {
  bottleneck_id: string
  location: string
  description: string
  impact_score: number
  affected_conversations: number
  suggested_improvements: string[]
}

export interface ConversationMetrics {
  total_conversations: number
  total_messages: number
  avg_messages_per_conversation: number
  avg_conversation_duration_seconds: number
  user_satisfaction_estimate: number
  resolution_rate: number
  escalation_rate: number
}

export interface AnalysisResult {
  metrics: ConversationMetrics
  intent_patterns: IntentPattern[]
  common_flows: ConversationFlow[]
  bottlenecks: FlowBottleneck[]
  hourly_distribution: Record<string, number>
  analysis_period: string
  conversations_analyzed: number
}

export function useConversationFlowData() {
  const endpoint = useFetchEndpoint<AnalysisResult, AnalysisResult>({
    path: '/api/conversation-flow/analyze',
    label: 'conversation-flow/analyze',
    pickData: (raw) => raw ?? null,
    onError: (message, err) => {
      logger.error('Failed to analyze conversations:', err)
    },
  })

  const runAnalysis = async (hours: number): Promise<void> => {
    await endpoint.load({ hours: String(hours) })
  }

  return {
    isLoading: endpoint.loading,
    analysisResult: endpoint.data,
    runAnalysis,
  }
}
