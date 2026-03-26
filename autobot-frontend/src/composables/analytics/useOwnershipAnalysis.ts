// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useOwnershipAnalysis
 *
 * Code ownership mapping and knowledge gap analysis.
 * Extracted from useSpecializedAnalysis (Issue #2372).
 */

import { ref } from 'vue'
import { useAnalyticsFetch } from '@/composables/useAnalyticsFetch'
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

export function useOwnershipAnalysis(
  deps: UseCodeIntelAnalysisDeps,
) {
  const { rootPath, sourceIdQuery } = deps

  const {
    data: ownershipAnalysis,
    loading: loadingOwnership,
    error: ownershipError,
    load: _loadOwnership,
  } = useAnalyticsFetch<OwnershipAnalysisResult>(
    '/api/analytics/codebase/ownership/analysis',
    (r) => {
      if (r.status === 'success') {
        return {
          status: r.status as string,
          analysis_time_seconds:
            (r.analysis_time_seconds as number) || 0,
          summary: (r.summary as OwnershipSummary) || {
            total_files: 0,
            total_directories: 0,
            total_contributors: 0,
            knowledge_gaps_count: 0,
            critical_gaps: 0,
            high_risk_gaps: 0,
          },
          file_ownership:
            (r.file_ownership as FileOwnership[]) || [],
          directory_ownership:
            (r.directory_ownership as DirectoryOwnership[]) || [],
          expertise_scores:
            (r.expertise_scores as ExpertiseScore[]) || [],
          knowledge_gaps:
            (r.knowledge_gaps as KnowledgeGap[]) || [],
          metrics: (r.metrics as OwnershipMetrics) || {
            total_lines_analyzed: 0,
            total_files_analyzed: 0,
            overall_bus_factor: 1,
            bus_factor_distribution: {},
            knowledge_risk_distribution: {},
            top_contributors: [],
            ownership_concentration: 0,
            team_coverage: 0,
          },
        }
      }
      if (r.status === 'error') return undefined
      return undefined
    },
  )

  const ownershipViewMode = ref<
    'overview' | 'files' | 'contributors' | 'gaps'
  >('overview')

  const loadOwnershipAnalysis = async () => {
    if (!rootPath.value) return
    await _loadOwnership({
      path: rootPath.value,
      ...sourceIdQuery.value,
    })
  }

  return {
    ownershipAnalysis,
    loadingOwnership,
    ownershipError,
    ownershipViewMode,
    loadOwnershipAnalysis,
  }
}
