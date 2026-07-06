// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Code Intelligence Composable
 * Issue #899 - Code Intelligence Tools
 */

import { ref, computed, onMounted, getCurrentInstance } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('useCodeIntelligence')

// ===== Type Definitions =====

export interface CodeAnalysisRequest {
  code: string
  language?: string
  filename?: string
  include_suggestions?: boolean
}

export interface CodeAnalysisResult {
  id: string
  code: string
  language: string
  filename?: string
  metrics: CodeMetrics
  quality_score: number
  issues: CodeIssue[]
  suggestions: CodeSuggestion[]
  timestamp: string
}

export interface CodeMetrics {
  lines_of_code: number
  cyclomatic_complexity: number
  maintainability_index: number
  code_duplication_percent: number
  comment_ratio: number
  function_count: number
  class_count: number
}

export interface CodeIssue {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  category: 'security' | 'quality' | 'style' | 'performance' | 'documentation'
  message: string
  line_number?: number
  column?: number
  suggestion?: string
}

export interface CodeSuggestion {
  id: string
  type: 'refactoring' | 'optimization' | 'security' | 'style' | 'documentation'
  priority: 'high' | 'medium' | 'low'
  title: string
  description: string
  before?: string
  after?: string
  impact: string
}

export interface QualityScore {
  overall_score: number
  metrics: {
    complexity: number
    maintainability: number
    documentation: number
    testing: number
    security: number
  }
  grade: 'A+' | 'A' | 'B' | 'C' | 'D' | 'F'
  trend: 'improving' | 'stable' | 'declining'
}

export interface CodeHealthScore {
  health_score: number
  total_files: number
  issues_count: {
    critical: number
    high: number
    medium: number
    low: number
  }
  coverage_percent: number
  technical_debt_hours: number
  timestamp: string
}

export interface AnalysisTrend {
  date: string
  quality_score: number
  health_score: number
  issues_count: number
}

export interface ComparisonResult {
  file1: string
  file2: string
  similarity_percent: number
  differences: {
    added_lines: number
    removed_lines: number
    modified_lines: number
  }
  quality_change: number
}

export interface SecurityScoreCached {
  status: 'success' | 'no_data'
  from_cache?: boolean
  completed_at?: string
  security_score?: number
  grade?: string
  risk_level?: string
  status_message?: string
  total_findings?: number
  critical_issues?: number
  high_issues?: number
  files_analyzed?: number
  severity_breakdown?: Record<string, number>
  owasp_breakdown?: Record<string, number>
}

export interface UseCodeIntelligenceOptions {
  autoFetch?: boolean
}

// ===== Composable Implementation =====

export function useCodeIntelligence(options: UseCodeIntelligenceOptions = {}) {
  const { autoFetch = false } = options

  // State
  const currentAnalysis = ref<CodeAnalysisResult | null>(null)
  const analysisHistory = ref<CodeAnalysisResult[]>([])
  const qualityScore = ref<QualityScore | null>(null)
  const healthScore = ref<CodeHealthScore | null>(null)
  const suggestions = ref<CodeSuggestion[]>([])
  const trends = ref<AnalysisTrend[]>([])
  const securityScoreCached = ref<SecurityScoreCached | null>(null)
  const isLoading = ref(false)
  // Counter-based concurrency: isLoading clears only when all concurrent analysis
  // operations finish. useLoadingState.wrap() does not support this — it clears
  // loading per-call, not per-set. Skip migrating this composable (#5880).
  const loadingCount = ref(0)
  const errors = ref<string[]>([])
  const error = computed<string | null>(() =>
    errors.value.length > 0 ? errors.value.join('; ') : null,
  )

  // ===== API Methods =====

  /** Increment loading counter and set isLoading flag. */
  function startLoading(): void {
    loadingCount.value++
    isLoading.value = true
  }

  /** Decrement loading counter and clear isLoading when all done. */
  function stopLoading(): void {
    loadingCount.value = Math.max(0, loadingCount.value - 1)
    if (loadingCount.value === 0) {
      isLoading.value = false
    }
  }

  async function analyzeCode(request: CodeAnalysisRequest): Promise<CodeAnalysisResult | null> {
    startLoading()
    try {
      const data = await ApiClient.post<CodeAnalysisResult>(`${getApiBase()}/code-intelligence/analyze`, request)
      currentAnalysis.value = data
      logger.debug('Code analysis complete:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to analyze code'
      logger.error('Code analysis failed:', err)
      errors.value = [...errors.value, message]
      return null
    } finally {
      stopLoading()
    }
  }

  async function getAnalysis(analysisId: string): Promise<CodeAnalysisResult | null> {
    startLoading()
    try {
      const data = await ApiClient.get<CodeAnalysisResult>(`${getApiBase()}/code-intelligence/analysis/${analysisId}`)
      currentAnalysis.value = data
      logger.debug('Fetched analysis:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch analysis'
      logger.error('Failed to fetch analysis:', err)
      errors.value = [...errors.value, message]
      return null
    } finally {
      stopLoading()
    }
  }

  async function getQualityScore(code: string, language?: string): Promise<QualityScore | null> {
    startLoading()
    try {
      const data = await ApiClient.post<QualityScore>(`${getApiBase()}/code-intelligence/quality-score`, { code, language })
      qualityScore.value = data
      logger.debug('Quality score:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to get quality score'
      logger.error('Failed to get quality score:', err)
      errors.value = [...errors.value, message]
      return null
    } finally {
      stopLoading()
    }
  }

  async function getSuggestions(code: string, language?: string): Promise<void> {
    startLoading()
    try {
      const data = await ApiClient.post<{ suggestions?: CodeSuggestion[] }>(`${getApiBase()}/code-intelligence/suggestions`, { code, language })
      suggestions.value = data.suggestions || []
      logger.debug('Fetched suggestions:', suggestions.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch suggestions'
      logger.error('Failed to fetch suggestions:', err)
      errors.value = [...errors.value, message]
    } finally {
      stopLoading()
    }
  }

  async function getHealthScore(path?: string): Promise<void> {
    startLoading()
    try {
      const url = path
        ? `${getApiBase()}/code-intelligence/health-score?path=${encodeURIComponent(path)}`
        : `${getApiBase()}/code-intelligence/health-score`
      const data = await ApiClient.get<CodeHealthScore>(url)
      healthScore.value = data
      logger.debug('Health score:', healthScore.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch health score'
      logger.error('Failed to fetch health score:', err)
      errors.value = [...errors.value, message]
    } finally {
      stopLoading()
    }
  }

  async function getSecurityScoreCached(): Promise<SecurityScoreCached | null> {
    startLoading()
    try {
      const data = await ApiClient.get<SecurityScoreCached>(`${getApiBase()}/code-intelligence/security/score/cached`)
      securityScoreCached.value = data
      logger.debug('Cached security score:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch cached security score'
      logger.error('Failed to fetch cached security score:', err)
      errors.value = [...errors.value, message]
      return null
    } finally {
      stopLoading()
    }
  }

  async function getTrends(days: number = 30): Promise<void> {
    startLoading()
    try {
      const data = await ApiClient.get<{ trends?: AnalysisTrend[] }>(`${getApiBase()}/code-intelligence/trends?days=${days}`)
      trends.value = data.trends || []
      logger.debug('Fetched trends:', trends.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch trends'
      logger.error('Failed to fetch trends:', err)
      errors.value = [...errors.value, message]
    } finally {
      stopLoading()
    }
  }

  async function compareCode(file1: string, file2: string): Promise<ComparisonResult | null> {
    startLoading()
    try {
      const data = await ApiClient.post<ComparisonResult>(`${getApiBase()}/code-intelligence/compare`, { file1, file2 })
      logger.debug('Comparison result:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to compare code'
      logger.error('Failed to compare code:', err)
      errors.value = [...errors.value, message]
      return null
    } finally {
      stopLoading()
    }
  }

  async function getAnalysisHistory(limit: number = 50): Promise<void> {
    startLoading()
    try {
      const data = await ApiClient.get<{ analyses?: CodeAnalysisResult[] }>(`${getApiBase()}/code-intelligence/history?limit=${limit}`)
      analysisHistory.value = data.analyses || []
      logger.debug('Fetched analysis history:', analysisHistory.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch history'
      logger.error('Failed to fetch history:', err)
      errors.value = [...errors.value, message]
    } finally {
      stopLoading()
    }
  }

  async function deleteAnalysis(analysisId: string): Promise<boolean> {
    startLoading()
    try {
      await ApiClient.delete<unknown>(`${getApiBase()}/code-intelligence/analysis/${analysisId}`)
      analysisHistory.value = analysisHistory.value.filter(a => a.id !== analysisId)
      logger.debug('Deleted analysis:', analysisId)
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete analysis'
      logger.error('Failed to delete analysis:', err)
      errors.value = [...errors.value, message]
      return false
    } finally {
      stopLoading()
    }
  }

  async function batchAnalyze(files: Array<{ code: string; filename: string; language?: string }>): Promise<CodeAnalysisResult[]> {
    startLoading()
    try {
      const data = await ApiClient.post<{ results?: CodeAnalysisResult[] }>(`${getApiBase()}/code-intelligence/batch-analyze`, { files })
      logger.debug('Batch analysis complete:', data.results?.length)
      return data.results || []
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to batch analyze'
      logger.error('Failed to batch analyze:', err)
      errors.value = [...errors.value, message]
      return []
    } finally {
      stopLoading()
    }
  }

  /** Clear all accumulated errors. */
  function clearErrors(): void {
    errors.value = []
  }

  // ===== Lifecycle =====

  if (getCurrentInstance()) {
    onMounted(() => {
      if (autoFetch) {
        clearErrors()
        Promise.all([
          getSecurityScoreCached(),
          getAnalysisHistory(),
        ])
      }
    })
  }

  return {
    // State
    currentAnalysis,
    analysisHistory,
    qualityScore,
    healthScore,
    securityScoreCached,
    suggestions,
    trends,
    isLoading,
    error,
    errors,

    // Methods
    analyzeCode,
    getAnalysis,
    getQualityScore,
    getSuggestions,
    getHealthScore,
    getSecurityScoreCached,
    getTrends,
    compareCode,
    getAnalysisHistory,
    deleteAnalysis,
    batchAnalyze,
    clearErrors,
  }
}

export default useCodeIntelligence
