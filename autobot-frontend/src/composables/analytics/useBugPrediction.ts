// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useBugPrediction
 *
 * Bug prediction analysis, risk filtering, and risk factor helpers.
 * Extracted from useCodeIntelAnalysis (Issue #2260).
 */

import { ref, computed } from 'vue'
import { useExpansion } from '@/composables/useExpansion'
import apiClient from '@/utils/ApiClient'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import type {
  UseCodeIntelAnalysisDeps,
  BugPredictionFile,
  BugPredictionResult,
  TopRiskFactor,
} from './codeIntelTypes'
import { getApiBase } from '@/config/ssot-config'

export function useBugPrediction(deps: UseCodeIntelAnalysisDeps) {
  const { t } = deps

  // --- Background task ---

  const bugPredictionTask = useBackgroundTask(
    `${getApiBase()}/analytics/bug-prediction`,
  )

  const bugPredictionAnalysis = computed<BugPredictionResult | null>(
    () => {
      const r = bugPredictionTask.result.value
      if (!r || r.status === 'no_data') return null
      return {
        timestamp:
          (r.timestamp as string) || new Date().toISOString(),
        total_files: (r.total_files as number) || 0,
        analyzed_files: (r.analyzed_files as number) || 0,
        high_risk_count: (r.high_risk_count as number) || 0,
        files: (r.files as BugPredictionFile[]) || [],
      }
    },
  )

  const loadingBugPrediction = bugPredictionTask.running
  const bugPredictionError = bugPredictionTask.error

  // --- UI state ---

  const bugRiskFilter = ref<'all' | 'high' | 'medium' | 'low'>('all')
  const BUG_RISK_PAGE_SIZE = 50
  const bugRiskVisibleCount = ref(BUG_RISK_PAGE_SIZE)
  const bugRiskExpansion = useExpansion<string>()
  const expandedBugRiskFiles = bugRiskExpansion.expanded

  // --- Loaders ---

  const loadBugPrediction = () => bugPredictionTask.start()

  const loadCachedBugPrediction = async () => {
    try {
      const data = await apiClient.get<Record<string, unknown>>(
        '/api/analytics/bug-prediction/cached',
      )
      if (data.status === 'success' && data.files) {
        bugPredictionTask.result.value = data
      }
    } catch {
      // Cached data not available — silently ignore
    }
  }

  // --- Risk helpers ---

  function getAtRiskFilesCount(): number {
    if (!bugPredictionAnalysis.value) return 0
    return bugPredictionAnalysis.value.files.filter(
      (f) => f.risk_score >= 40,
    ).length
  }

  function toggleBugRiskFilter(
    filter: 'high' | 'medium' | 'low',
  ): void {
    bugRiskFilter.value =
      bugRiskFilter.value === filter ? 'all' : filter
    bugRiskVisibleCount.value = BUG_RISK_PAGE_SIZE
  }

  function toggleBugRiskFileExpand(filePath: string): void {
    bugRiskExpansion.toggle(filePath)
  }

  function getFilteredBugRiskFiles(): BugPredictionFile[] {
    if (!bugPredictionAnalysis.value) return []
    const files = bugPredictionAnalysis.value.files
    let filtered: BugPredictionFile[]
    switch (bugRiskFilter.value) {
      case 'high':
        filtered = files.filter((f) => f.risk_score >= 60)
        break
      case 'medium':
        filtered = files.filter(
          (f) => f.risk_score >= 40 && f.risk_score < 60,
        )
        break
      case 'low':
        filtered = files.filter((f) => f.risk_score < 40)
        break
      case 'all':
      default:
        filtered = [...files]
        break
    }
    return filtered.sort((a, b) => b.risk_score - a.risk_score)
  }

  function getTopRiskFactors(): TopRiskFactor[] {
    if (!bugPredictionAnalysis.value) return []
    const factorCounts: Record<string, number> = {
      complexity: 0,
      change_frequency: 0,
      file_size: 0,
      bug_history: 0,
      test_coverage: 0,
    }
    for (const file of bugPredictionAnalysis.value.files) {
      if (!file.factors) continue
      if (file.factors.complexity >= 80) factorCounts.complexity++
      if (file.factors.change_frequency >= 80)
        factorCounts.change_frequency++
      if (file.factors.file_size >= 70) factorCounts.file_size++
      if (file.factors.bug_history > 0) factorCounts.bug_history++
      if (file.factors.test_coverage === 50)
        factorCounts.test_coverage++
    }
    const factors: TopRiskFactor[] = Object.entries(factorCounts)
      .filter(([, count]) => count > 0)
      .map(([name, count]) => ({
        name,
        count,
        severity: _getSeverityForFactor(name, count),
      }))
      .sort((a, b) => b.count - a.count)
    return factors.slice(0, 4)
  }

  function _getSeverityForFactor(
    factor: string,
    count: number,
  ): 'critical' | 'high' | 'medium' | 'low' {
    if (factor === 'bug_history' && count > 0) return 'critical'
    if (count > 50) return 'high'
    if (count > 20) return 'medium'
    return 'low'
  }

  function getRiskFactorIcon(factor: string): string {
    const icons: Record<string, string> = {
      complexity: 'fas fa-project-diagram',
      change_frequency: 'fas fa-history',
      file_size: 'fas fa-file-alt',
      bug_history: 'fas fa-bug',
      test_coverage: 'fas fa-vial',
      dependency_count: 'fas fa-sitemap',
    }
    return icons[factor] || 'fas fa-exclamation-circle'
  }

  function getRiskFactorDescription(factor: string): string {
    const descriptions: Record<string, string> = {
      complexity: t(
        'analytics.codebase.bugPrediction.factors.complexity',
      ),
      change_frequency: t(
        'analytics.codebase.bugPrediction.factors.changeFrequency',
      ),
      file_size: t(
        'analytics.codebase.bugPrediction.factors.fileSize',
      ),
      bug_history: t(
        'analytics.codebase.bugPrediction.factors.bugHistory',
      ),
      test_coverage: t(
        'analytics.codebase.bugPrediction.factors.testCoverage',
      ),
      dependency_count: t(
        'analytics.codebase.bugPrediction.factors.dependencyCount',
      ),
    }
    return (
      descriptions[factor] ||
      t('analytics.codebase.bugPrediction.factors.default')
    )
  }

  function getFactorBarClass(value: number): string {
    if (value >= 80) return 'bar-critical'
    if (value >= 50) return 'bar-warning'
    return 'bar-ok'
  }

  return {
    bugPredictionTask,
    bugPredictionAnalysis,
    loadingBugPrediction,
    bugPredictionError,
    bugRiskFilter,
    bugRiskVisibleCount,
    expandedBugRiskFiles,
    loadBugPrediction,
    loadCachedBugPrediction,
    getAtRiskFilesCount,
    toggleBugRiskFilter,
    toggleBugRiskFileExpand,
    getFilteredBugRiskFiles,
    getTopRiskFactors,
    getRiskFactorIcon,
    getRiskFactorDescription,
    getFactorBarClass,
  }
}
