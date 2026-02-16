// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Code Intelligence Composable
 * Issue #899 - Code Intelligence Tools
 */

import { ref, onMounted } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

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
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // ===== API Methods =====

  async function analyzeCode(request: CodeAnalysisRequest): Promise<CodeAnalysisResult | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/code-intelligence/analyze', request)
      currentAnalysis.value = data
      logger.debug('Code analysis complete:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to analyze code'
      logger.error('Code analysis failed:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function getAnalysis(analysisId: string): Promise<CodeAnalysisResult | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get(`/api/code-intelligence/analysis/${analysisId}`)
      currentAnalysis.value = data
      logger.debug('Fetched analysis:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch analysis'
      logger.error('Failed to fetch analysis:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function getQualityScore(code: string, language?: string): Promise<QualityScore | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/code-intelligence/quality-score', { code, language })
      qualityScore.value = data
      logger.debug('Quality score:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to get quality score'
      logger.error('Failed to get quality score:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function getSuggestions(code: string, language?: string): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/code-intelligence/suggestions', { code, language })
      suggestions.value = data.suggestions || []
      logger.debug('Fetched suggestions:', suggestions.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch suggestions'
      logger.error('Failed to fetch suggestions:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function getHealthScore(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get('/api/code-intelligence/health-score')
      healthScore.value = data
      logger.debug('Health score:', healthScore.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch health score'
      logger.error('Failed to fetch health score:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function getTrends(days: number = 30): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get(`/api/code-intelligence/trends?days=${days}`)
      trends.value = data.trends || []
      logger.debug('Fetched trends:', trends.value)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch trends'
      logger.error('Failed to fetch trends:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function compareCode(file1: string, file2: string): Promise<ComparisonResult | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/code-intelligence/compare', { file1, file2 })
      logger.debug('Comparison result:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to compare code'
      logger.error('Failed to compare code:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function getAnalysisHistory(limit: number = 50): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.get(`/api/code-intelligence/history?limit=${limit}`)
      analysisHistory.value = data.analyses || []
      logger.debug('Fetched analysis history:', analysisHistory.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch history'
      logger.error('Failed to fetch history:', err)
      error.value = message
    } finally {
      isLoading.value = false
    }
  }

  async function deleteAnalysis(analysisId: string): Promise<boolean> {
    isLoading.value = true
    error.value = null
    try {
      await ApiClient.delete(`/api/code-intelligence/analysis/${analysisId}`)
      analysisHistory.value = analysisHistory.value.filter(a => a.id !== analysisId)
      logger.debug('Deleted analysis:', analysisId)
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete analysis'
      logger.error('Failed to delete analysis:', err)
      error.value = message
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function batchAnalyze(files: Array<{ code: string; filename: string; language?: string }>): Promise<CodeAnalysisResult[]> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/code-intelligence/batch-analyze', { files })
      logger.debug('Batch analysis complete:', data.results?.length)
      return data.results || []
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to batch analyze'
      logger.error('Failed to batch analyze:', err)
      error.value = message
      return []
    } finally {
      isLoading.value = false
    }
  }

  // ===== Lifecycle =====

  onMounted(() => {
    if (autoFetch) {
      Promise.all([getHealthScore(), getAnalysisHistory()])
    }
  })

  return {
    // State
    currentAnalysis,
    analysisHistory,
    qualityScore,
    healthScore,
    suggestions,
    trends,
    isLoading,
    error,

    // Methods
    analyzeCode,
    getAnalysis,
    getQualityScore,
    getSuggestions,
    getHealthScore,
    getTrends,
    compareCode,
    getAnalysisHistory,
    deleteAnalysis,
    batchAnalyze,
  }
}

export default useCodeIntelligence
