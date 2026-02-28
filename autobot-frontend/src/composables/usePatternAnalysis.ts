/**
 * Vue Composable for Code Pattern Analysis API
 *
 * Issue #208: Provides reactive state and API integration for
 * code pattern detection and optimization features.
 *
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 */

import { ref, reactive, computed } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { getConfig } from '@/config/ssot-config'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('usePatternAnalysis')

// Type definitions for Pattern Analysis
export interface CodeLocation {
  file_path: string
  start_line: number
  end_line: number
  function_name?: string
  class_name?: string
  line_count: number
}

export interface DuplicatePattern {
  pattern_type: string
  severity: string
  description: string
  locations: CodeLocation[]
  suggestion: string
  confidence: number
  similarity_score: number
  canonical_code: string
  code_reduction_potential: number
}

export interface RegexOpportunity {
  pattern_type: string
  severity: string
  description: string
  locations: CodeLocation[]
  suggestion: string
  confidence: number
  current_code: string
  suggested_regex: string
  performance_gain: string
  operations_replaced: string[]
}

export interface ComplexityHotspot {
  pattern_type: string
  severity: string
  description: string
  locations: CodeLocation[]
  suggestion: string
  confidence: number
  cyclomatic_complexity: number
  maintainability_index: number
  cognitive_complexity: number
  nesting_depth: number
  simplification_suggestions: string[]
}

export interface RefactoringSuggestion {
  title: string
  description: string
  pattern_type: string
  severity: string
  affected_locations: CodeLocation[]
  refactoring_type: string
  suggested_name: string
  code_template: string
  estimated_loc_reduction: number
  estimated_complexity_reduction: number
  estimated_effort: string
  confidence: number
  benefits: string[]
}

export interface PatternAnalysisReport {
  analysis_summary: {
    scan_path: string
    timestamp: string
    files_analyzed: number
    lines_analyzed: number
    duration_seconds: number
    total_patterns_found: number
    potential_loc_reduction: number
    complexity_score: string
  }
  pattern_counts: Record<string, number>
  severity_distribution: Record<string, number>
  duplicate_patterns: DuplicatePattern[]
  regex_opportunities: RegexOpportunity[]
  complexity_hotspots: ComplexityHotspot[]
  modularization_suggestions: any[]
  other_patterns: any[]
}

export interface PatternStorageStats {
  total_patterns: number
  pattern_type_distribution: Record<string, number>
  collection_name: string
}

export interface AnalysisTaskStatus {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress?: number
  current_step?: string
  result?: PatternAnalysisReport
  error?: string
  reason?: string  // orphaned, timeout, manual (#1250)
}

/**
 * Composable for Code Pattern Analysis
 */
export function usePatternAnalysis() {
  // Reactive state
  const loading = ref(false)
  const analyzing = ref(false)
  const error = ref<string | null>(null)
  const wasInterrupted = ref(false)  // #1250: orphaned task detection
  const currentTaskId = ref<string | null>(null)
  const taskStatus = ref<AnalysisTaskStatus | null>(null)

  // Analysis results
  const analysisReport = ref<PatternAnalysisReport | null>(null)
  const duplicatePatterns = ref<DuplicatePattern[]>([])
  const regexOpportunities = ref<RegexOpportunity[]>([])
  const complexityHotspots = ref<ComplexityHotspot[]>([])
  const refactoringSuggestions = ref<RefactoringSuggestion[]>([])
  const storageStats = ref<PatternStorageStats | null>(null)

  // UI state
  const expandedSections = reactive({
    duplicates: false,
    regex: false,
    complexity: false,
    refactoring: false
  })

  // Computed properties
  const totalPatterns = computed(() => {
    return (analysisReport.value?.analysis_summary?.total_patterns_found || 0)
  })

  const severityCounts = computed(() => {
    return analysisReport.value?.severity_distribution || {}
  })

  const hasResults = computed(() => {
    return analysisReport.value !== null
  })

  // API base URL helper
  const getBackendUrl = async (): Promise<string> => {
    try {
      return await appConfig.getServiceUrl('backend')
    } catch (_e) {
      logger.warn('AppConfig failed, using SSOT config backend URL')
      return getConfig().backendUrl
    }
  }

  // API Methods

  /**
   * Run full pattern analysis on a directory
   */
  const analyzePatterns = async (
    path: string,
    options: {
      enableRegex?: boolean
      enableComplexity?: boolean
      enableDuplicates?: boolean
      similarityThreshold?: number
      runInBackground?: boolean
    } = {}
  ): Promise<boolean> => {
    const {
      enableRegex = true,
      enableComplexity = true,
      enableDuplicates = true,
      similarityThreshold = 0.8,
      runInBackground = true
    } = options

    analyzing.value = true
    error.value = null

    try {
      const backendUrl = await getBackendUrl()
      let response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          enable_regex_detection: enableRegex,
          enable_complexity_analysis: enableComplexity,
          enable_duplicate_detection: enableDuplicates,
          similarity_threshold: similarityThreshold,
          run_in_background: runInBackground
        })
      })

      // Issue #647: Handle 409 Conflict by clearing stuck tasks and retrying
      if (response.status === 409) {
        logger.info('Another analysis is running, attempting to clear stuck tasks...')

        // Try to clear stuck tasks with force=true
        const clearResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/tasks/clear-stuck?force=true`, {
          method: 'POST'
        })

        if (clearResponse.ok) {
          const clearResult = await clearResponse.json()
          logger.info('Cleared stuck tasks:', clearResult)

          // Retry the analysis
          response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              path,
              enable_regex_detection: enableRegex,
              enable_complexity_analysis: enableComplexity,
              enable_duplicate_detection: enableDuplicates,
              similarity_threshold: similarityThreshold,
              run_in_background: runInBackground
            })
          })
        }
      }

      if (!response.ok) {
        const errorDetail = response.status === 409
          ? 'Another analysis is still running. Please wait for it to complete.'
          : `Analysis failed: ${response.statusText}`
        throw new Error(errorDetail)
      }

      const data = await response.json()

      if (runInBackground && data.task_id) {
        currentTaskId.value = data.task_id
        taskStatus.value = {
          task_id: data.task_id,
          status: 'pending'
        }
        // Start polling for status
        pollTaskStatus(data.task_id)
        return true
      } else if (data.status === 'success' && data.report) {
        analysisReport.value = data.report
        duplicatePatterns.value = data.report.duplicate_patterns || []
        regexOpportunities.value = data.report.regex_opportunities || []
        complexityHotspots.value = data.report.complexity_hotspots || []
        analyzing.value = false
        return true
      }

      throw new Error('Unexpected response format')
    } catch (e: any) {
      error.value = e.message || 'Analysis failed'
      logger.error('Pattern analysis failed:', e)
      analyzing.value = false
      return false
    }
  }

  /**
   * Poll for background task status
   */
  const pollTaskStatus = async (taskId: string): Promise<void> => {
    const pollInterval = 2000 // 2 seconds
    const maxAttempts = 150 // 5 minutes max

    let attempts = 0

    const poll = async (): Promise<void> => {
      if (attempts >= maxAttempts) {
        error.value = 'Analysis timed out'
        analyzing.value = false
        return
      }

      try {
        const backendUrl = await getBackendUrl()
        const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/status/${taskId}`)

        if (!response.ok) {
          throw new Error(`Status check failed: ${response.statusText}`)
        }

        const data = await response.json()
        taskStatus.value = data

        if (data.status === 'completed' && data.result) {
          analysisReport.value = data.result
          duplicatePatterns.value = data.result.duplicate_patterns || []
          regexOpportunities.value = data.result.regex_opportunities || []
          complexityHotspots.value = data.result.complexity_hotspots || []
          analyzing.value = false
          return
        } else if (data.status === 'failed') {
          // #1250: Detect orphaned tasks and show friendly message
          const isOrphaned = data.reason === 'orphaned'
            || data.error?.includes('orphaned')
          if (isOrphaned) {
            wasInterrupted.value = true
            error.value = 'Previous analysis was interrupted by a server restart.'
          } else {
            error.value = data.error || 'Analysis failed'
          }
          analyzing.value = false
          return
        }

        // Continue polling
        attempts++
        setTimeout(poll, pollInterval)
      } catch (e: any) {
        error.value = e.message || 'Status check failed'
        logger.error('Task status poll failed:', e)
        analyzing.value = false
      }
    }

    await poll()
  }

  /**
   * Get quick pattern summary from cache (Issue #208 optimization)
   * Uses cached data from ChromaDB instead of re-analyzing
   */
  const getCachedSummary = async (): Promise<boolean> => {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/cached-summary`)

      if (!response.ok) {
        return false
      }

      const data = await response.json()
      if (data.has_cached_data && data.total_patterns > 0) {
        // Update report from cached data
        analysisReport.value = {
          analysis_summary: {
            scan_path: '',
            timestamp: new Date().toISOString(),
            files_analyzed: data.files_analyzed || 0,
            lines_analyzed: 0,
            duration_seconds: 0,
            total_patterns_found: data.total_patterns || 0,
            potential_loc_reduction: data.potential_loc_reduction || 0,
            complexity_score: 'N/A'
          },
          pattern_counts: data.pattern_type_distribution || {},
          severity_distribution: data.severity_distribution || {},
          duplicate_patterns: [],
          regex_opportunities: [],
          complexity_hotspots: [],
          modularization_suggestions: [],
          other_patterns: []
        }
        return true
      }
      return false
    } catch (e: any) {
      logger.debug('Cached summary not available:', e.message)
      return false
    }
  }

  /**
   * Get quick pattern summary
   * First tries cached data, falls back to full analysis if no cache
   */
  const getSummary = async (path?: string): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      // First try to get cached summary (fast path)
      const hasCached = await getCachedSummary()
      if (hasCached) {
        loading.value = false
        return
      }

      // Fall back to full summary if no cached data
      const backendUrl = await getBackendUrl()
      const url = path
        ? `${backendUrl}/api/analytics/codebase/patterns/summary?path=${encodeURIComponent(path)}`
        : `${backendUrl}/api/analytics/codebase/patterns/summary`

      const response = await fetchWithAuth(url)

      if (!response.ok) {
        throw new Error(`Summary fetch failed: ${response.statusText}`)
      }

      const data = await response.json()
      if (data.status === 'success') {
        // Update counts from summary
        if (data.summary) {
          analysisReport.value = {
            analysis_summary: {
              scan_path: path || '',
              timestamp: new Date().toISOString(),
              files_analyzed: 0,
              lines_analyzed: 0,
              duration_seconds: 0,
              total_patterns_found: data.summary.total_patterns || 0,
              potential_loc_reduction: data.summary.loc_reduction_potential || 0,
              complexity_score: data.summary.complexity_score || 'N/A'
            },
            pattern_counts: data.summary.pattern_counts || {},
            severity_distribution: data.summary.severity_distribution || {},
            duplicate_patterns: [],
            regex_opportunities: [],
            complexity_hotspots: [],
            modularization_suggestions: [],
            other_patterns: []
          }
        }
      }
    } catch (e: any) {
      error.value = e.message || 'Summary fetch failed'
      logger.error('Pattern summary fetch failed:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Get duplicate patterns
   */
  const getDuplicates = async (
    path?: string,
    minSimilarity: number = 0.8,
    limit: number = 50
  ): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const backendUrl = await getBackendUrl()
      const params = new URLSearchParams({
        min_similarity: minSimilarity.toString(),
        limit: limit.toString()
      })
      if (path) params.append('path', path)

      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/duplicates?${params}`)

      if (!response.ok) {
        throw new Error(`Duplicates fetch failed: ${response.statusText}`)
      }

      const data = await response.json()
      if (data.status === 'success') {
        duplicatePatterns.value = data.duplicates || []
      }
    } catch (e: any) {
      error.value = e.message || 'Duplicates fetch failed'
      logger.error('Duplicate patterns fetch failed:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Get regex optimization opportunities
   */
  const getRegexOpportunities = async (
    path?: string,
    limit: number = 50
  ): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const backendUrl = await getBackendUrl()
      const params = new URLSearchParams({ limit: limit.toString() })
      if (path) params.append('path', path)

      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/regex-opportunities?${params}`)

      if (!response.ok) {
        throw new Error(`Regex opportunities fetch failed: ${response.statusText}`)
      }

      const data = await response.json()
      if (data.status === 'success') {
        regexOpportunities.value = data.opportunities || []
      }
    } catch (e: any) {
      error.value = e.message || 'Regex opportunities fetch failed'
      logger.error('Regex opportunities fetch failed:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Get complexity hotspots
   */
  const getComplexityHotspots = async (
    path?: string,
    minComplexity: number = 10,
    limit: number = 50
  ): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const backendUrl = await getBackendUrl()
      const params = new URLSearchParams({
        min_complexity: minComplexity.toString(),
        limit: limit.toString()
      })
      if (path) params.append('path', path)

      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/complexity-hotspots?${params}`)

      if (!response.ok) {
        throw new Error(`Complexity hotspots fetch failed: ${response.statusText}`)
      }

      const data = await response.json()
      if (data.status === 'success') {
        complexityHotspots.value = data.hotspots || []
      }
    } catch (e: any) {
      error.value = e.message || 'Complexity hotspots fetch failed'
      logger.error('Complexity hotspots fetch failed:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Get refactoring suggestions
   */
  const getRefactoringSuggestions = async (
    path?: string,
    maxSuggestions: number = 20
  ): Promise<void> => {
    loading.value = true
    error.value = null

    try {
      const backendUrl = await getBackendUrl()
      const params = new URLSearchParams({ max_suggestions: maxSuggestions.toString() })
      if (path) params.append('path', path)

      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/refactoring-suggestions?${params}`)

      if (!response.ok) {
        throw new Error(`Refactoring suggestions fetch failed: ${response.statusText}`)
      }

      const data = await response.json()
      if (data.status === 'success') {
        refactoringSuggestions.value = data.suggestions || []
      }
    } catch (e: any) {
      error.value = e.message || 'Refactoring suggestions fetch failed'
      logger.error('Refactoring suggestions fetch failed:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Get pattern storage stats
   */
  const getStorageStats = async (): Promise<void> => {
    loading.value = true

    try {
      const backendUrl = await getBackendUrl()
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/storage/stats`)

      if (!response.ok) {
        throw new Error(`Storage stats fetch failed: ${response.statusText}`)
      }

      const data = await response.json()
      if (data.status === 'success') {
        storageStats.value = data.stats
      }
    } catch (e: any) {
      logger.error('Storage stats fetch failed:', e)
    } finally {
      loading.value = false
    }
  }

  /**
   * Clear pattern storage
   */
  const clearStorage = async (): Promise<boolean> => {
    loading.value = true

    try {
      const backendUrl = await getBackendUrl()
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/storage/clear`, {
        method: 'DELETE'
      })

      if (!response.ok) {
        throw new Error(`Clear storage failed: ${response.statusText}`)
      }

      const data = await response.json()
      if (data.status === 'success') {
        storageStats.value = null
        return true
      }
      return false
    } catch (e: any) {
      logger.error('Clear storage failed:', e)
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Get markdown report
   */
  const getReport = async (path?: string): Promise<string | null> => {
    loading.value = true

    try {
      const backendUrl = await getBackendUrl()
      const params = path ? `?path=${encodeURIComponent(path)}` : ''
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/report${params}`)

      if (!response.ok) {
        throw new Error(`Report fetch failed: ${response.statusText}`)
      }

      const data = await response.json()
      if (data.status === 'success') {
        return data.report
      }
      return null
    } catch (e: any) {
      logger.error('Report fetch failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Reset all state
   */
  const reset = (): void => {
    loading.value = false
    analyzing.value = false
    error.value = null
    wasInterrupted.value = false
    currentTaskId.value = null
    taskStatus.value = null
    analysisReport.value = null
    duplicatePatterns.value = []
    regexOpportunities.value = []
    complexityHotspots.value = []
    refactoringSuggestions.value = []
    storageStats.value = null
  }

  /**
   * Fast initial load - only loads summary and stats from cache
   * Issue #208: Optimized loading for already indexed data
   */
  const loadCachedData = async (): Promise<boolean> => {
    loading.value = true
    error.value = null

    try {
      // Load summary and stats in parallel from cache
      const [hasCachedSummary] = await Promise.all([
        getCachedSummary(),
        getStorageStats()
      ])

      return hasCachedSummary
    } catch (e: any) {
      logger.error('Failed to load cached data:', e)
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Load all data for a path
   */
  const loadAllData = async (path: string): Promise<void> => {
    await Promise.all([
      getSummary(path),
      getDuplicates(path),
      getRegexOpportunities(path),
      getComplexityHotspots(path),
      getRefactoringSuggestions(path),
      getStorageStats()
    ])
  }

  /**
   * Clear stuck analysis tasks
   * Issue #647: Manual recovery for stuck tasks
   */
  const clearStuckTasks = async (force: boolean = false): Promise<{ cleared: number; message: string }> => {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetchWithAuth(
        `${backendUrl}/api/analytics/codebase/patterns/tasks/clear-stuck?force=${force}`,
        { method: 'POST' }
      )

      if (!response.ok) {
        throw new Error(`Failed to clear tasks: ${response.statusText}`)
      }

      const result = await response.json()
      logger.info('Cleared stuck tasks:', result)
      return { cleared: result.cleared_count, message: result.message }
    } catch (e: any) {
      logger.error('Failed to clear stuck tasks:', e)
      throw e
    }
  }

  /**
   * List all analysis tasks
   * Issue #647: View task status for debugging
   */
  const listTasks = async (): Promise<{ total: number; running: number; tasks: any[] }> => {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/tasks`)

      if (!response.ok) {
        throw new Error(`Failed to list tasks: ${response.statusText}`)
      }

      return await response.json()
    } catch (e: any) {
      logger.error('Failed to list tasks:', e)
      throw e
    }
  }

  return {
    // State
    loading,
    analyzing,
    error,
    wasInterrupted,
    currentTaskId,
    taskStatus,
    analysisReport,
    duplicatePatterns,
    regexOpportunities,
    complexityHotspots,
    refactoringSuggestions,
    storageStats,
    expandedSections,

    // Computed
    totalPatterns,
    severityCounts,
    hasResults,

    // Methods
    analyzePatterns,
    getSummary,
    getCachedSummary,
    getDuplicates,
    getRegexOpportunities,
    getComplexityHotspots,
    getRefactoringSuggestions,
    getStorageStats,
    clearStorage,
    getReport,
    reset,
    loadAllData,
    loadCachedData,
    clearStuckTasks,
    listTasks
  }
}

export default usePatternAnalysis
