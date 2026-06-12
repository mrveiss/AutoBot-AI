// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Vue Composable for Code Pattern Analysis API
 *
 * Issue #208: Provides reactive state and API integration for
 * code pattern detection and optimization features.
 *
 * Author: mrveiss
 */

import { ref, computed, onUnmounted } from 'vue'
import { usePollingJob } from '@/composables/usePollingJob'
import { useExpansion } from '@/composables/useExpansion'
import appConfig from '@/config/AppConfig.js'
import { getConfig, getApiBase } from '@/config/ssot-config'
import apiClient from '@/utils/ApiClient'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'
import { extractErrorMessage } from '@/utils/errorExtract'
import { useBackgroundTask } from '@/composables/useBackgroundTask'
import { useLoadingState } from '@/composables/useLoadingState'

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

/** Generic pattern record from backend modularization/other analysis */
export interface GenericPattern {
  pattern_type: string
  severity: string
  description: string
  locations?: CodeLocation[]
  suggestion?: string
  confidence?: number
  [key: string]: unknown
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
  modularization_suggestions: GenericPattern[]
  other_patterns: GenericPattern[]
}

export interface PatternStorageStats {
  total_patterns: number
  pattern_type_distribution: Record<string, number>
  collection_name: string
}

export interface PartialResults {
  regex?: RegexOpportunity[]
  complexity?: ComplexityHotspot[]
  modularization?: GenericPattern[]
  other_patterns?: GenericPattern[]
  files_processed?: number
  total_files?: number
}

export interface AnalysisTaskStatus {
  task_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress?: number
  current_step?: string
  result?: PatternAnalysisReport
  error?: string
  reason?: string  // orphaned, timeout, manual (#1250)
  partial_results?: PartialResults
}

/** Task list entry returned by the tasks endpoint */
export interface AnalysisTaskEntry {
  task_id: string
  status: string
  progress?: number
  created_at?: string
  [key: string]: unknown
}

/**
 * Composable for Code Pattern Analysis
 */
export function usePatternAnalysis() {
  // Background task for pattern summary (#1332)
  const summaryTask = useBackgroundTask(
    `${getApiBase()}/analytics/codebase/patterns/summary`,
    `${getApiBase()}/analytics/codebase/patterns/summary/tasks/clear-stuck`
  )

  // Reactive state
  const { isLoading: loading, wrap } = useLoadingState()
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
  // #9724: while an analysis is running, partial_results stream
  // GenericPattern rows into this list; the final payload replaces them
  // with fully-typed RefactoringSuggestion entries.
  const refactoringSuggestions = ref<(RefactoringSuggestion | GenericPattern)[]>([])
  const storageStats = ref<PatternStorageStats | null>(null)

  // AbortControllers — replaced (aborting previous) before each new fetch
  // _actionController removed: GET/POST helpers now use apiClient (no manual abort needed)
  let _analyzeController: AbortController | null = null
  let _pollController: AbortController | null = null

  // UI state
  type Section = 'duplicates' | 'regex' | 'complexity' | 'refactoring'
  const { isExpanded: isSectionExpanded, toggle: toggleSection } = useExpansion<Section>()

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

  // API base URL helper (used by analyzePatterns and pollTaskStatus)
  const getBackendUrl = async (): Promise<string> => {
    try {
      return await appConfig.getServiceUrl('backend')
    } catch {
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
    wasInterrupted.value = false

    _analyzeController?.abort()
    _analyzeController = new AbortController()
    const _analyzeSignal = _analyzeController.signal

    try {
      const backendUrl = await getBackendUrl()
      let response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/analyze`, { // fetchWithAuth retained: AbortController signal + response.status === 409 — exempt (#6256)
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          enable_regex_detection: enableRegex,
          enable_complexity_analysis: enableComplexity,
          enable_duplicate_detection: enableDuplicates,
          similarity_threshold: similarityThreshold,
          run_in_background: runInBackground
        }),
        signal: _analyzeSignal,
      })

      // Issue #647: Handle 409 Conflict by clearing stuck tasks and retrying
      if (response.status === 409) {
        logger.info('Another analysis is running, attempting to clear stuck tasks...')

        // Try to clear stuck tasks with force=true
        const clearResponse = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/tasks/clear-stuck?force=true`, { // fetchWithAuth retained: AbortController signal — exempt (#6256)
          method: 'POST',
          signal: _analyzeSignal,
        })

        if (clearResponse.ok) {
          const clearResult = await clearResponse.json()
          logger.info('Cleared stuck tasks:', clearResult)

          // Retry the analysis
          response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/patterns/analyze`, { // fetchWithAuth retained: AbortController signal + response.status === 409 — exempt (#6256)
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              path,
              enable_regex_detection: enableRegex,
              enable_complexity_analysis: enableComplexity,
              enable_duplicate_detection: enableDuplicates,
              similarity_threshold: similarityThreshold,
              run_in_background: runInBackground
            }),
            signal: _analyzeSignal,
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
        // Poll until task completes — caller awaits this
        const pollResult = await pollTaskStatus(data.task_id)

        // Auto-retry once if orphaned: clear stuck tasks and start fresh
        if (pollResult === 'orphaned') {
          logger.info('Pattern task orphaned, clearing stuck tasks and retrying…')
          wasInterrupted.value = false
          error.value = null

          await fetchWithAuth( // fetchWithAuth retained: AbortController signal — exempt (#6256)
            `${backendUrl}/api/analytics/codebase/patterns/tasks/clear-stuck?force=true`,
            { method: 'POST', signal: _analyzeSignal },
          )
          const retryResp = await fetchWithAuth( // fetchWithAuth retained: AbortController signal + response.status check — exempt (#6256)
            `${backendUrl}/api/analytics/codebase/patterns/analyze`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                path,
                enable_regex_detection: enableRegex,
                enable_complexity_analysis: enableComplexity,
                enable_duplicate_detection: enableDuplicates,
                similarity_threshold: similarityThreshold,
                run_in_background: true,
              }),
              signal: _analyzeSignal,
            },
          )
          if (retryResp.ok) {
            const retryData = await retryResp.json()
            if (retryData.task_id) {
              currentTaskId.value = retryData.task_id
              taskStatus.value = { task_id: retryData.task_id, status: 'pending' }
              await pollTaskStatus(retryData.task_id)
            }
          }
        }

        return !error.value
      } else if (data.status === 'success' && data.report) {
        analysisReport.value = data.report
        duplicatePatterns.value = data.report.duplicate_patterns || []
        regexOpportunities.value = data.report.regex_opportunities || []
        complexityHotspots.value = data.report.complexity_hotspots || []
        analyzing.value = false
        return true
      }

      throw new Error('Unexpected response format')
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') { analyzing.value = false; return false }
      error.value = extractErrorMessage(e, 'Analysis failed')
      logger.error('Pattern analysis failed:', e)
      analyzing.value = false
      return false
    }
  }

  /**
   * Poll for background task status using usePollingJob for resilience.
   * Returns a Promise that resolves when the task completes or fails.
   * Transient fetch errors are retried — a single network glitch
   * does not kill the polling loop (up to MAX_CONSECUTIVE_ERRORS).
   */
  const pollTaskStatus = (
    taskId: string,
  ): Promise<'completed' | 'failed' | 'orphaned' | 'error'> => {
    const POLL_INTERVAL_MS = 2000
    const MAX_CONSECUTIVE_ERRORS = 5

    // Track consecutive errors inside the fetcher closure (resets on success)
    let consecutiveErrors = 0
    let resolved = false

    return new Promise<'completed' | 'failed' | 'orphaned' | 'error'>((resolve) => {
      const settle = (result: 'completed' | 'failed' | 'orphaned' | 'error') => {
        if (!resolved) { resolved = true; resolve(result) }
      }

      // The fetcher returns a sentinel object that isComplete can inspect
      type PollResult = { done: boolean; outcome: 'completed' | 'failed' | 'orphaned' | 'error' | 'running' }

      const poller = usePollingJob<PollResult>(
        async () => {
          try {
            const backendUrl = await getBackendUrl()
            _pollController?.abort()
            _pollController = new AbortController()
            const response = await fetchWithAuth( // fetchWithAuth retained: AbortController signal + partial-results streaming — exempt (#6256)
              `${backendUrl}/api/analytics/codebase/patterns/status/${taskId}`,
              { signal: _pollController.signal },
            )
            if (!response.ok) {
              throw new Error(`Status check failed: ${response.statusText}`)
            }
            const data: AnalysisTaskStatus = await response.json()
            consecutiveErrors = 0 // Reset on successful fetch
            taskStatus.value = data

            // Apply partial results while analysis is running
            if (data.partial_results && data.status === 'running') {
              const pr = data.partial_results
              if (pr.regex?.length) regexOpportunities.value = pr.regex
              if (pr.complexity?.length) complexityHotspots.value = pr.complexity
              if (pr.modularization?.length || pr.other_patterns?.length) {
                refactoringSuggestions.value = [
                  ...(pr.modularization || []),
                  ...(pr.other_patterns || []),
                ]
              }
              const partialTotal =
                (pr.regex?.length || 0) +
                (pr.complexity?.length || 0) +
                (pr.modularization?.length || 0) +
                (pr.other_patterns?.length || 0)
              if (partialTotal > 0) {
                analysisReport.value = {
                  analysis_summary: {
                    scan_path: '',
                    timestamp: new Date().toISOString(),
                    files_analyzed: pr.files_processed || 0,
                    lines_analyzed: 0,
                    duration_seconds: 0,
                    total_patterns_found: partialTotal,
                    potential_loc_reduction: 0,
                    complexity_score: 'N/A',
                  },
                  pattern_counts: {},
                  severity_distribution: {},
                  duplicate_patterns: [],
                  regex_opportunities: pr.regex || [],
                  complexity_hotspots: pr.complexity || [],
                  modularization_suggestions: pr.modularization || [],
                  other_patterns: pr.other_patterns || [],
                }
              }
            }

            if (data.status === 'completed' && data.result) {
              analysisReport.value = data.result
              duplicatePatterns.value = data.result.duplicate_patterns || []
              regexOpportunities.value = data.result.regex_opportunities || []
              complexityHotspots.value = data.result.complexity_hotspots || []
              analyzing.value = false
              return { done: true, outcome: 'completed' }
            }

            if (data.status === 'failed') {
              const isOrphaned = data.reason === 'orphaned' || data.error?.includes('orphaned')
              if (isOrphaned) {
                wasInterrupted.value = true
                error.value = 'Previous analysis was interrupted by a server restart.'
              } else {
                error.value = data.error || 'Analysis failed'
              }
              analyzing.value = false
              return { done: true, outcome: isOrphaned ? 'orphaned' : 'failed' }
            }

            return { done: false, outcome: 'running' }
          } catch (e: unknown) {
            if (e instanceof DOMException && e.name === 'AbortError') {
              analyzing.value = false
              return { done: true, outcome: 'error' }
            }
            consecutiveErrors++
            const msg = extractErrorMessage(e, 'Unknown poll error')
            logger.warn(
              `Task status poll error (${consecutiveErrors}/${MAX_CONSECUTIVE_ERRORS}): ${msg}`
            )
            if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
              error.value = `Lost connection to backend after ${MAX_CONSECUTIVE_ERRORS} retries`
              analyzing.value = false
              return { done: true, outcome: 'error' }
            }
            // Transient error — keep polling
            return { done: false, outcome: 'running' }
          }
        },
        {
          intervalMs: POLL_INTERVAL_MS,
          maxAttempts: 600, // 20 minutes max — terminal status settles much earlier
          isComplete: (r) => r.done,
          onDone: (r) => settle(r.outcome as 'completed' | 'failed' | 'orphaned' | 'error'),
        }
      )

      poller.start(taskId)
    })
  }

  /**
   * Get quick pattern summary from cache (Issue #208 optimization)
   * Uses cached data from ChromaDB instead of re-analyzing
   */
  const getCachedSummary = async (): Promise<boolean> => {
    try {
      const data = await apiClient.get<Record<string, unknown>>(
        '/api/analytics/codebase/patterns/cached-summary',
      )
      if (data.has_cached_data && (data.total_patterns as number) > 0) {
        // Update report from cached data
        analysisReport.value = {
          analysis_summary: {
            scan_path: '',
            timestamp: new Date().toISOString(),
            files_analyzed: (data.files_analyzed as number) || 0,
            lines_analyzed: 0,
            duration_seconds: 0,
            total_patterns_found: (data.total_patterns as number) || 0,
            potential_loc_reduction: (data.potential_loc_reduction as number) || 0,
            complexity_score: 'N/A'
          },
          pattern_counts: (data.pattern_type_distribution as Record<string, number>) || {},
          severity_distribution: (data.severity_distribution as Record<string, number>) || {},
          duplicate_patterns: [],
          regex_opportunities: [],
          complexity_hotspots: [],
          modularization_suggestions: [],
          other_patterns: []
        }
        return true
      }
      return false
    } catch (e: unknown) {
      logger.debug('Cached summary not available:', extractErrorMessage(e, 'unknown'))
      return false
    }
  }

  /**
   * Get quick pattern summary
   * First tries cached data, falls back to full analysis if no cache
   */
  const getSummary = async (path?: string): Promise<void> => {
    error.value = null
    await wrap(async () => {
      // First try to get cached summary (fast path)
      const hasCached = await getCachedSummary()
      if (hasCached) {
        return
      }

      // Fall back to background task analysis (#1332)
      // The sync GET /patterns/summary runs analysis inline and times out
      // on large codebases. Use POST /patterns/summary/analyze instead.
      const query = path ? { path } : undefined
      const success = await summaryTask.start(undefined, query)

      if (!success) {
        throw new Error(summaryTask.error.value || 'Summary analysis failed')
      }

      const data = summaryTask.result.value
      if (data) {
        analysisReport.value = {
          analysis_summary: {
            scan_path: path || '',
            timestamp: new Date().toISOString(),
            files_analyzed: 0,
            lines_analyzed: 0,
            duration_seconds: 0,
            total_patterns_found: (data.total_patterns as number) || 0,
            potential_loc_reduction: (data.potential_loc_reduction as number) || 0,
            complexity_score: (data.complexity_score as string) || 'N/A'
          },
          pattern_counts: {},
          severity_distribution: {},
          duplicate_patterns: [],
          regex_opportunities: [],
          complexity_hotspots: [],
          modularization_suggestions: [],
          other_patterns: []
        }
      }
    }).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Summary fetch failed')
      logger.error('Pattern summary fetch failed:', e)
    })
  }

  /**
   * Get duplicate patterns
   */
  const getDuplicates = async (
    path?: string,
    minSimilarity: number = 0.8,
    limit: number = 50
  ): Promise<void> => {
    error.value = null
    await wrap(async () => {
      const params = new URLSearchParams({
        min_similarity: minSimilarity.toString(),
        limit: limit.toString()
      })
      if (path) params.append('path', path)

      const data = await apiClient.get<{ status: string; duplicates?: DuplicatePattern[] }>(
        `/api/analytics/codebase/patterns/duplicates?${params}`,
      )
      if (data.status === 'success') {
        duplicatePatterns.value = data.duplicates || []
      }
    }).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Duplicates fetch failed')
      logger.error('Duplicate patterns fetch failed:', e)
    })
  }

  /**
   * Get regex optimization opportunities
   */
  const getRegexOpportunities = async (
    path?: string,
    limit: number = 50
  ): Promise<void> => {
    error.value = null
    await wrap(async () => {
      const params = new URLSearchParams({ limit: limit.toString() })
      if (path) params.append('path', path)

      const data = await apiClient.get<{ status: string; opportunities?: RegexOpportunity[] }>(
        `/api/analytics/codebase/patterns/regex-opportunities?${params}`,
      )
      if (data.status === 'success') {
        regexOpportunities.value = data.opportunities || []
      }
    }).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Regex opportunities fetch failed')
      logger.error('Regex opportunities fetch failed:', e)
    })
  }

  /**
   * Get complexity hotspots
   */
  const getComplexityHotspots = async (
    path?: string,
    minComplexity: number = 10,
    limit: number = 50
  ): Promise<void> => {
    error.value = null
    await wrap(async () => {
      const params = new URLSearchParams({
        min_complexity: minComplexity.toString(),
        limit: limit.toString()
      })
      if (path) params.append('path', path)

      const data = await apiClient.get<{ status: string; hotspots?: ComplexityHotspot[] }>(
        `/api/analytics/codebase/patterns/complexity-hotspots?${params}`,
      )
      if (data.status === 'success') {
        complexityHotspots.value = data.hotspots || []
      }
    }).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Complexity hotspots fetch failed')
      logger.error('Complexity hotspots fetch failed:', e)
    })
  }

  /**
   * Get refactoring suggestions
   */
  const getRefactoringSuggestions = async (
    path?: string,
    maxSuggestions: number = 20
  ): Promise<void> => {
    error.value = null
    await wrap(async () => {
      const params = new URLSearchParams({ max_suggestions: maxSuggestions.toString() })
      if (path) params.append('path', path)

      const data = await apiClient.get<{ status: string; suggestions?: RefactoringSuggestion[] }>(
        `/api/analytics/codebase/patterns/refactoring-suggestions?${params}`,
      )
      if (data.status === 'success') {
        refactoringSuggestions.value = data.suggestions || []
      }
    }).catch((e: unknown) => {
      error.value = extractErrorMessage(e, 'Refactoring suggestions fetch failed')
      logger.error('Refactoring suggestions fetch failed:', e)
    })
  }

  /**
   * Get pattern storage stats
   */
  const getStorageStats = async (): Promise<void> => {
    await wrap(async () => {
      const data = await apiClient.get<{ status: string; stats?: PatternStorageStats }>(
        '/api/analytics/codebase/patterns/storage/stats',
      )
      if (data.status === 'success') {
        storageStats.value = data.stats ?? null
      }
    }).catch((e: unknown) => {
      logger.error('Storage stats fetch failed:', e)
    })
  }

  /**
   * Clear pattern storage
   */
  const clearStorage = async (): Promise<boolean> => {
    return wrap(async () => {
      const data = await apiClient.delete<{ status: string }>(
        '/api/analytics/codebase/patterns/storage/clear',
      )
      if (data.status === 'success') {
        storageStats.value = null
        return true
      }
      return false
    }).catch((e: unknown) => {
      logger.error('Clear storage failed:', e)
      return false
    })
  }

  /**
   * Get markdown report
   */
  const getReport = async (path?: string): Promise<string | null> => {
    return wrap(async () => {
      const params = path ? `?path=${encodeURIComponent(path)}` : ''
      const data = await apiClient.get<{ status: string; report?: string }>(
        `/api/analytics/codebase/patterns/report${params}`,
      )
      if (data.status === 'success') {
        return data.report ?? null
      }
      return null
    }).catch((e: unknown) => {
      logger.error('Report fetch failed:', e)
      return null
    })
  }

  /**
   * Reset all state
   */
  onUnmounted(() => {
    _analyzeController?.abort()
    _pollController?.abort()
  })

  const reset = (): void => {
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
    error.value = null
    return wrap(async () => {
      // Load summary and stats in parallel from cache
      const [hasCachedSummary] = await Promise.all([
        getCachedSummary(),
        getStorageStats()
      ])

      return hasCachedSummary
    }).catch((e: unknown) => {
      logger.error('Failed to load cached data:', e)
      return false
    })
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
      const result = await apiClient.post<{ cleared_count: number; message: string }>(
        `/api/analytics/codebase/patterns/tasks/clear-stuck?force=${force}`,
      )
      logger.info('Cleared stuck tasks:', result)
      return { cleared: result.cleared_count, message: result.message }
    } catch (e: unknown) {
      logger.error('Failed to clear stuck tasks:', e)
      throw e
    }
  }

  /**
   * List all analysis tasks
   * Issue #647: View task status for debugging
   */
  const listTasks = async (): Promise<{ total: number; running: number; tasks: AnalysisTaskEntry[] }> => {
    try {
      return await apiClient.get<{ total: number; running: number; tasks: AnalysisTaskEntry[] }>(
        '/api/analytics/codebase/patterns/tasks',
      )
    } catch (e: unknown) {
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
    isSectionExpanded,
    toggleSection,

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
