// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, type Ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { extractApiErrorMessage } from '@/utils/errorExtract'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'
import { getApiBase } from '@/config/ssot-config'
import { usePollingJob } from '@/composables/usePollingJob'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useAutoResearch')

// --- Types ---

export interface ExperimentResult {
  val_bpb: number | null
  train_loss: number | null
  val_loss: number | null
  steps_completed: number
  tokens_per_second: number | null
  wall_time_seconds: number
  error_message: string | null
}

export interface Experiment {
  id: string
  hypothesis: string
  description: string
  state: string
  hyperparams: Record<string, unknown>
  result: ExperimentResult | null
  baseline_val_bpb: number | null
  tags: string[]
  created_at: number
  started_at: number | null
  completed_at: number | null
}

export interface ExperimentStats {
  total_experiments: number
  completed: number
  failed: number
  kept: number
  discarded: number
  best_val_bpb: number | null
  baseline_val_bpb: number | null
  avg_wall_time: number
  total_wall_time: number
  improvement_trend: number[]
}

export interface PromptVariant {
  id: string
  prompt_text: string
  output: string
  scores: Record<string, number>
  final_score: number
  round_number: number
  created_at: number
}

export interface OptimizationSession {
  id: string
  status: string
  rounds_completed: number
  max_rounds: number
  best_variant: PromptVariant | null
  baseline_score: number
  all_variants: PromptVariant[]
}

export interface ApprovalRequest {
  session_id: string
  experiment_id: string
  details: Record<string, unknown>
  requested_at: number
  status: string
}

export interface ExperimentInsight {
  id: string
  statement: string
  confidence: number
  supporting_experiments: string[]
  related_hyperparams: string[]
  synthesized_at: number
  session_id: string | null
}

// --- Composable ---

export function useAutoResearch() {
  const api = useApiClient()

  const experiments: Ref<Experiment[]> = ref([])
  const stats: Ref<ExperimentStats | null> = ref(null)
  const { isLoading: loading, wrap } = useLoadingState()
  const error: Ref<string | null> = ref(null)

  const optimizerStatus: Ref<OptimizationSession | null> = ref(null)
  const variants: Ref<PromptVariant[]> = ref([])

  const pendingApprovals: Ref<ApprovalRequest[]> = ref([])

  const insights: Ref<ExperimentInsight[]> = ref([])

  // --- Experiments ---

  async function fetchExperiments(params?: {
    limit?: number
    offset?: number
    state?: string
  }): Promise<void> {
    error.value = null
    await wrap(async () => {
      try {
        const query = new URLSearchParams()
        if (params?.limit != null) query.set('limit', String(params.limit))
        if (params?.offset != null) query.set('offset', String(params.offset))
        if (params?.state) query.set('state', params.state)
        const response = await api.get<any>(`${getApiBase()}/autoresearch/experiments?${query}`)
        experiments.value = response.experiments ?? []
      } catch (err) {
        const msg = extractApiErrorMessage(err, 'Failed to fetch experiments')
        logger.error('fetchExperiments failed:', err)
        error.value = msg
        showSubtleErrorNotification('AutoResearch', msg, 'warning')
      }
    })
  }

  async function fetchStats(): Promise<void> {
    try {
      const response = await api.get<any>(`${getApiBase()}/autoresearch/experiments/stats`)
      stats.value = response
    } catch (err) {
      const msg = extractApiErrorMessage(err, 'Failed to fetch experiment stats')
      logger.error('fetchStats failed:', err)
      error.value = msg
      showSubtleErrorNotification('AutoResearch', msg, 'warning')
    }
  }

  // --- Prompt Optimizer ---

  async function fetchOptimizerStatus(): Promise<void> {
    try {
      const response = await api.get<any>(`${getApiBase()}/autoresearch/prompt-optimizer/status`)
      optimizerStatus.value = response.session ?? null
    } catch (err) {
      const msg = extractApiErrorMessage(err, 'Failed to fetch optimizer status')
      logger.error('fetchOptimizerStatus failed:', err)
      error.value = msg
      showSubtleErrorNotification('AutoResearch', msg, 'warning')
    }
  }

  async function startOptimization(
    agentName: string,
    maxRounds: number = 3,
  ): Promise<void> {
    await api.post<any>(`${getApiBase()}/autoresearch/prompt-optimizer/start`, {
      agent_name: agentName,
      max_rounds: maxRounds,
    })
    await fetchOptimizerStatus()
  }

  async function cancelOptimization(): Promise<void> {
    await api.post<any>(`${getApiBase()}/autoresearch/prompt-optimizer/cancel`)
    await fetchOptimizerStatus()
  }

  async function fetchVariants(sessionId: string): Promise<void> {
    const response = await api.get<any>(
      `${getApiBase()}/autoresearch/prompt-optimizer/variants/${sessionId}`,
    )
    variants.value = response.variants ?? []
  }

  async function scoreVariant(
    variantId: string,
    sessionId: string,
    score: number,
    comment: string = '',
  ): Promise<void> {
    await api.post<any>(
      `${getApiBase()}/autoresearch/prompt-optimizer/variants/${variantId}/score?session_id=${sessionId}`,
      { score, comment },
    )
  }

  // --- Approvals ---

  async function fetchPendingApprovals(): Promise<void> {
    const response = await api.get<any>(`${getApiBase()}/autoresearch/approvals/pending`)
    pendingApprovals.value = response.approvals ?? []
  }

  async function approveExperiment(
    sessionId: string,
    experimentId: string,
  ): Promise<void> {
    await api.post<any>(
      `${getApiBase()}/autoresearch/approvals/${sessionId}/${experimentId}`,
      { decision: 'approved' },
    )
    await fetchPendingApprovals()
  }

  async function rejectExperiment(
    sessionId: string,
    experimentId: string,
  ): Promise<void> {
    await api.post<any>(
      `${getApiBase()}/autoresearch/approvals/${sessionId}/${experimentId}`,
      { decision: 'rejected' },
    )
    await fetchPendingApprovals()
  }

  // --- Insights ---

  async function fetchInsights(minConfidence: number = 0): Promise<void> {
    const response = await api.get<any>(
      `${getApiBase()}/autoresearch/insights?min_confidence=${minConfidence}`,
    )
    insights.value = response.insights ?? []
  }

  async function searchInsights(query: string): Promise<void> {
    const response = await api.get<any>(
      `${getApiBase()}/autoresearch/insights/search?q=${encodeURIComponent(query)}`,
    )
    insights.value = response.insights ?? []
  }

  // --- Polling ---

  let _stopAutoResearchPoller: (() => void) | null = null

  function startPolling(intervalMs: number = 10000): void {
    if (_stopAutoResearchPoller) _stopAutoResearchPoller()
    const poller = usePollingJob<void>(
      async () => {
        await Promise.all([
          fetchExperiments(),
          fetchStats(),
          fetchOptimizerStatus(),
          fetchPendingApprovals(),
        ])
      },
      { intervalMs }
    )
    _stopAutoResearchPoller = poller.stop
    poller.start('')
  }

  function stopPolling(): void {
    if (_stopAutoResearchPoller) _stopAutoResearchPoller()
    _stopAutoResearchPoller = null
  }

  return {
    experiments,
    stats,
    loading,
    error,
    fetchExperiments,
    fetchStats,
    optimizerStatus,
    startOptimization,
    cancelOptimization,
    variants,
    fetchVariants,
    scoreVariant,
    pendingApprovals,
    fetchPendingApprovals,
    approveExperiment,
    rejectExperiment,
    insights,
    fetchInsights,
    searchInsights,
    startPolling,
    stopPolling,
  }
}
