// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  Experiment,
  ExperimentStats,
  OptimizationSession,
  ApprovalRequest,
  ExperimentInsight,
} from '@/composables/useAutoResearch'

export const useAutoResearchStore = defineStore('autoResearch', () => {
  const experiments = ref<Experiment[]>([])
  const stats = ref<ExperimentStats | null>(null)
  const optimizerSession = ref<OptimizationSession | null>(null)
  const pendingApprovals = ref<ApprovalRequest[]>([])
  const insights = ref<ExperimentInsight[]>([])
  const isPolling = ref(false)
  const lastFetchedAt = ref<number | null>(null)

  function setExperiments(data: Experiment[]) {
    experiments.value = data
    lastFetchedAt.value = Date.now()
  }

  function setStats(data: ExperimentStats) {
    stats.value = data
  }

  function setOptimizerSession(session: OptimizationSession | null) {
    optimizerSession.value = session
  }

  function setPendingApprovals(approvals: ApprovalRequest[]) {
    pendingApprovals.value = approvals
  }

  function setInsights(data: ExperimentInsight[]) {
    insights.value = data
  }

  function setPolling(polling: boolean) {
    isPolling.value = polling
  }

  return {
    experiments,
    stats,
    optimizerSession,
    pendingApprovals,
    insights,
    isPolling,
    lastFetchedAt,
    setExperiments,
    setStats,
    setOptimizerSession,
    setPendingApprovals,
    setInsights,
    setPolling,
  }
})
