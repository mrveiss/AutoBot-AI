// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useOwnershipAnalysis
 *
 * Code ownership mapping and knowledge gap analysis.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 * Migrated from useAnalyticsFetch to useFetchEndpoint (Issue #5208).
 */

import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import type {
  UseCodeIntelAnalysisDeps,
  OwnershipAnalysisResult,
  OwnershipSummary,
  FileOwnership,
  DirectoryOwnership,
  ExpertiseScore,
  KnowledgeGap,
  OwnershipMetrics,
} from './codeIntelTypes'

interface OwnershipRaw {
  status: string
  analysis_time_seconds?: number
  summary?: OwnershipSummary
  file_ownership?: FileOwnership[]
  directory_ownership?: DirectoryOwnership[]
  expertise_scores?: ExpertiseScore[]
  knowledge_gaps?: KnowledgeGap[]
  metrics?: OwnershipMetrics
}

const EMPTY_SUMMARY: OwnershipSummary = {
  total_files: 0,
  total_directories: 0,
  total_contributors: 0,
  knowledge_gaps_count: 0,
  critical_gaps: 0,
  high_risk_gaps: 0,
}

const EMPTY_METRICS: OwnershipMetrics = {
  total_lines_analyzed: 0,
  total_files_analyzed: 0,
  overall_bus_factor: 1,
  bus_factor_distribution: {},
  knowledge_risk_distribution: {},
  top_contributors: [],
  ownership_concentration: 0,
  team_coverage: 0,
}

export function useOwnershipAnalysis(deps: UseCodeIntelAnalysisDeps) {
  const { rootPath, withSourceId } = deps

  const endpoint = useFetchEndpoint<OwnershipRaw, OwnershipAnalysisResult>(
    {
      path: '/api/analytics/codebase/ownership/analysis',
      scopeToSource: true,
      pickData: (r) =>
        r.status === 'success'
          ? {
              status: r.status,
              analysis_time_seconds: r.analysis_time_seconds ?? 0,
              summary: r.summary ?? EMPTY_SUMMARY,
              file_ownership: r.file_ownership ?? [],
              directory_ownership: r.directory_ownership ?? [],
              expertise_scores: r.expertise_scores ?? [],
              knowledge_gaps: r.knowledge_gaps ?? [],
              metrics: r.metrics ?? EMPTY_METRICS,
            }
          : null,
    },
    { withSourceId },
  )

  const loadOwnershipAnalysis = async () => {
    if (!rootPath.value) return
    await endpoint.load({ path: rootPath.value })
  }

  return {
    ownershipAnalysis: endpoint.data,
    loadingOwnership: endpoint.loading,
    ownershipError: endpoint.error,
    loadOwnershipAnalysis,
  }
}
